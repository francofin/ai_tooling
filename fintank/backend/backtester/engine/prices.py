"""Price panel loader and the availability/eligibility masks of §5.

This is the one module under engine/ that touches infrastructure. All of it
funnels through `_fetch_symbol_series`, which every test monkeypatches, so the
numerical core stays testable without S3, FMP or Redis.
"""
from __future__ import annotations

import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import requests
from django.conf import settings
from django.core.cache import cache

from utils.StockCalculations import GetData, index_mappers

from .config import PriceDataUnavailable

data_getter = GetData()

CACHE_KEY = 'prices:panel:{symbol}:v1'
CACHE_TIMEOUT = 86_400
PRICE_COLUMNS = ['date', 'adjClose']  # 'date' is the parquet index -- see §4


@dataclass
class PricePanel:
    """Dates × symbols adjClose, plus everything needed to reason about spans."""
    prices: pd.DataFrame
    first_valid: dict
    last_valid: dict
    provenance: dict
    missing: dict = field(default_factory=dict)

    @property
    def symbols(self) -> list:
        return list(self.prices.columns)

    def returns(self) -> pd.DataFrame:
        """Simple returns on adjClose, NaN filled with 0.

        Aligned to the price index rather than dropped, so the simulation loop
        can address returns and dates by the same position. Zero rather than NaN
        outside a symbol's span: the availability mask is what excludes an asset
        from the portfolio, and a stray NaN return would otherwise propagate
        through wᵀr and null out the whole day.
        """
        return self.prices.pct_change().fillna(0.0)

    def availability(self) -> pd.DataFrame:
        index = self.prices.index
        return pd.DataFrame(
            {symbol: (index >= self.first_valid[symbol]) & (index <= self.last_valid[symbol])
             for symbol in self.prices.columns},
            index=index,
        )

    def eligibility(self, min_history_days: int) -> pd.DataFrame:
        """available AND at least `min_history_days` of the symbol's own history.

        Counting the symbol's own trading days -- rather than calendar days --
        is what guarantees the covariance in §6 is estimated over a complete
        rectangular block.
        """
        available = self.availability()
        min_history_days = max(int(min_history_days), 1)
        return pd.DataFrame(
            {symbol: available[symbol] & (available[symbol].cumsum() >= min_history_days)
             for symbol in available.columns},
            index=available.index,
        )


def _series_from_frame(frame: pd.DataFrame) -> pd.Series:
    frame = frame[['date', 'adjClose']].copy()
    frame['date'] = pd.to_datetime(frame['date'])
    series = (frame.dropna(subset=['date'])
                   .set_index('date')['adjClose']
                   .astype(float)
                   .sort_index())
    return series[~series.index.duplicated(keep='last')]


def _fetch_from_fmp(symbol: str) -> pd.Series:
    url = (f"https://financialmodelingprep.com/api/v3/historical-price-full/"
           f"{symbol}?serietype=line&apikey={settings.FMP_API}")
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    rows = (response.json() or {}).get('historical') or []
    if not rows:
        raise FileNotFoundError(f"FMP returned no history for {symbol}")
    frame = pd.DataFrame(rows)
    # The line series calls the column 'close'; the parquets call it 'adjClose'.
    if 'adjClose' not in frame.columns:
        frame['adjClose'] = frame['close']
    return _series_from_frame(frame)


def _fetch_symbol_series(symbol: str):
    """The single I/O seam. Returns (series, provenance).

    Tests monkeypatch exactly this function, which is why the Redis layer and
    the concurrency live outside it.
    """
    try:
        frame = data_getter.load_stock_prices(symbol, columns=PRICE_COLUMNS)
        return _series_from_frame(frame), 's3'
    except (FileNotFoundError, OSError, KeyError):
        return _fetch_from_fmp(symbol), 'fmp'


def _load_symbol_cached(symbol: str):
    key = CACHE_KEY.format(symbol=symbol)
    compressed = cache.get(key)
    if compressed:
        try:
            rows = json.loads(gzip.decompress(compressed))
            series = pd.Series({pd.Timestamp(d): v for d, v in rows}, dtype=float)
            return series.sort_index(), 'cache'
        except Exception:
            # A corrupt or stale-format entry is not worth failing a run over.
            cache.delete(key)

    series, provenance = _fetch_symbol_series(symbol)
    rows = [[d.strftime('%Y-%m-%d'), None if v != v else float(v)]
            for d, v in series.items()]
    cache.set(key, gzip.compress(json.dumps(rows).encode('utf-8')), timeout=CACHE_TIMEOUT)
    return series, provenance


def load_price_panel(symbols, start=None, end=None) -> PricePanel:
    """Build the dates × symbols adjClose panel for `symbols`.

    Symbols load concurrently -- these are I/O bound, so the worker count is
    about hiding S3 latency. A symbol nobody can serve is recorded in `.missing`
    rather than sinking the run; only an entirely empty panel raises.
    """
    symbols = [str(s).strip().upper() for s in symbols]
    workers = max(1, min(getattr(settings, 'BACKTEST_MAX_WORKERS', 8), len(symbols)))

    series_by_symbol, provenance, missing = {}, {}, {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_load_symbol_cached, symbol): symbol for symbol in symbols}
        for future, symbol in futures.items():
            try:
                series, source = future.result()
            except Exception as error:
                missing[symbol] = f"{type(error).__name__}: {error}"
                continue
            series = series.dropna()
            if series.empty:
                missing[symbol] = 'No price history available.'
                continue
            series_by_symbol[symbol] = series
            provenance[symbol] = source

    if not series_by_symbol:
        raise PriceDataUnavailable(
            'None of the requested symbols have price history.', reasons=missing)

    ordered = [s for s in symbols if s in series_by_symbol]
    panel = pd.DataFrame({s: series_by_symbol[s] for s in ordered}).sort_index()

    first_valid = {s: panel[s].first_valid_index() for s in ordered}
    last_valid = {s: panel[s].last_valid_index() for s in ordered}

    # Forward fill within each symbol's own span only: never before its first
    # trade, never after its last. That is what makes the mask meaningful (§4).
    for symbol in ordered:
        span = (panel.index >= first_valid[symbol]) & (panel.index <= last_valid[symbol])
        panel.loc[span, symbol] = panel.loc[span, symbol].ffill()

    if start is not None:
        panel = panel[panel.index >= pd.Timestamp(start)]
    if end is not None:
        panel = panel[panel.index <= pd.Timestamp(end)]

    # Re-derive after trimming: a window that starts after a symbol's inception
    # must report the trimmed first date, not the original one.
    first_valid = {s: panel[s].first_valid_index() for s in ordered}
    last_valid = {s: panel[s].last_valid_index() for s in ordered}
    for symbol in ordered:
        if first_valid[symbol] is None:
            missing[symbol] = 'No price history inside the requested window.'

    keep = [s for s in ordered if first_valid[s] is not None]
    if not keep:
        raise PriceDataUnavailable(
            'No requested symbol has price history inside the requested window.',
            reasons=missing)

    panel = panel[keep]
    return PricePanel(
        prices=panel,
        first_valid={s: first_valid[s] for s in keep},
        last_valid={s: last_valid[s] for s in keep},
        provenance={s: provenance[s] for s in keep},
        missing=missing,
    )


def load_benchmark_series(symbol: str, start=None, end=None):
    """Benchmarks resolve through the index tree when the symbol is a known
    index key, otherwise through the same per-symbol path, so SPY and VTI work
    unchanged (§4)."""
    key = str(symbol).strip()
    if key in index_mappers or key.lower() in index_mappers:
        index_key = key if key in index_mappers else key.lower()
        frame = data_getter.load_index_parquet(index_key, columns=PRICE_COLUMNS)
        series, provenance = _series_from_frame(frame), 's3'
    else:
        series, provenance = _load_symbol_cached(key.upper())

    series = series.dropna().sort_index()
    if start is not None:
        series = series[series.index >= pd.Timestamp(start)]
    if end is not None:
        series = series[series.index <= pd.Timestamp(end)]
    return series, provenance
