"""Assembly and storage of the backtest result payload.

Full result JSON goes to Redis (fast path for the polling UI) and S3 (durable),
never to Postgres -- the BacktestRun row keeps only the request and a headline
summary (§11).
"""
from __future__ import annotations

import gzip
import json

import numpy as np
import pandas as pd
from django.core.cache import cache

from utils.StockCalculations import GetData

from .engine.backtest import drawdown_series
from .engine.config import optimizer_config
from .engine.diagnostics import build_diagnostics
from .engine.frontier import sample_frontier
from .engine.metrics import compute_metrics

data_getter = GetData()

CACHE_KEY = 'backtest:{task_id}:v1'
CACHE_TIMEOUT = 72 * 3600
S3_BUCKET = 'thetradingfloor'
S3_PREFIX = 'backtest_results'
FRONTIER_SAMPLES = 2000

SUMMARY_KEYS = ('cagr', 'annualized_volatility', 'sharpe', 'max_drawdown',
                'ending_balance', 'total_gain', 'years', 'money_weighted_return')


def _series(values):
    """Numeric sequence -> JSON-safe list. NaN and inf become None, because DRF
    rejects NaN at render time (same reasoning as CorePerformanceTools)."""
    out = []
    for value in np.asarray(values, dtype=float).tolist():
        out.append(None if (value != value or value in (float('inf'), float('-inf')))
                   else round(value, 8))
    return out


def _aligned_benchmark(benchmark: pd.Series, dates) -> tuple:
    """Benchmark growth of 1 over exactly the portfolio's dates."""
    if benchmark is None or len(benchmark) == 0:
        return [], [], None
    index = pd.DatetimeIndex(pd.to_datetime(list(dates)))
    series = benchmark.reindex(index.union(benchmark.index)).ffill().reindex(index)
    series = series.dropna()
    if series.empty:
        return [], [], None
    returns = series.pct_change().fillna(0.0).to_numpy()
    growth = np.cumprod(1.0 + returns)
    # Pad back to full length if the benchmark starts late.
    if len(growth) < len(index):
        pad = np.full(len(index) - len(growth), np.nan)
        growth = np.concatenate([pad, growth])
        returns = np.concatenate([pad, returns])
    return _series(growth), _series(drawdown_series(np.nan_to_num(growth, nan=1.0))), returns


def build_payload(result, request, panel, benchmark) -> dict:
    """Fill the BacktestResult slots left empty by the engine, and flatten the
    whole thing into one JSON-safe dict."""
    returns_frame = panel.returns()
    benchmark_index, benchmark_drawdown, benchmark_returns = _aligned_benchmark(
        benchmark, result.dates)

    metrics = compute_metrics(result, request, returns_frame=returns_frame,
                              benchmark_returns=benchmark_returns)

    benchmark_metrics = None
    if benchmark_returns is not None and len(benchmark_index):
        benchmark_metrics = _benchmark_metrics(benchmark_index, benchmark_returns,
                                               request, result.dates)

    diagnostics = build_diagnostics(result, request, metrics,
                                    benchmark_returns=benchmark_returns)

    window = returns_frame.loc[returns_frame.index.astype(str).isin(result.dates)]
    frontier = None
    if window.shape[0] > 10 and window.shape[1] >= 1:
        frontier = sample_frontier(
            window.to_numpy(), list(window.columns), optimizer_config(request),
            portfolio_weights=result.weights_over_time.iloc[-1].to_numpy(),
            samples=FRONTIER_SAMPLES)

    result.benchmark_index = benchmark_index
    result.benchmark_drawdown = benchmark_drawdown
    result.metrics = metrics
    result.benchmark_metrics = benchmark_metrics
    result.diagnostics = diagnostics
    result.frontier = frontier

    from .engine.config import normalized_payload

    return {
        'dates': list(result.dates),
        'nav': _series(result.nav),
        'index': _series(result.index),
        'drawdown': _series(result.drawdown),
        'returns': _series(result.returns),
        'weights_over_time': {symbol: _series(result.weights_over_time[symbol])
                              for symbol in result.weights_over_time.columns},
        'effective_asset_count': [int(v) for v in result.effective_asset_count],
        'rebalance_events': result.rebalance_events,
        'composition_events': result.composition_events,
        'benchmark_index': benchmark_index,
        'benchmark_drawdown': benchmark_drawdown,
        'benchmark_symbol': request.benchmark_symbol,
        'metrics': metrics,
        'benchmark_metrics': benchmark_metrics,
        'diagnostics': diagnostics,
        'frontier': frontier,
        'symbols': list(result.symbols),
        'effective_start': result.effective_start,
        'effective_end': result.effective_end,
        'truncation_cause': result.truncation_cause,
        'missing_symbols': panel.missing,
        'provenance': panel.provenance,
        'request': normalized_payload(request),
    }


def _benchmark_metrics(benchmark_index, benchmark_returns, request, dates) -> dict:
    """The same statistics for the benchmark, so the table has two columns.

    A lightweight stand-in result object is enough: compute_metrics reads only
    index, returns, nav, dates, rebalance_events, cash_flows and
    weights_over_time.
    """
    from types import SimpleNamespace

    values = np.asarray([v if v is not None else np.nan for v in benchmark_index],
                        dtype=float)
    values = np.nan_to_num(values, nan=1.0)
    returns = np.nan_to_num(np.asarray(benchmark_returns, dtype=float), nan=0.0)
    stand_in = SimpleNamespace(
        dates=list(dates),
        index=values,
        returns=returns,
        nav=values * float(request.initial_amount),
        drawdown=drawdown_series(values),
        weights_over_time=pd.DataFrame({request.benchmark_symbol: 1.0},
                                       index=pd.to_datetime(list(dates))),
        effective_asset_count=np.ones(len(dates)),
        rebalance_events=[],
        composition_events=[],
        cash_flows=[(dates[0], -float(request.initial_amount)),
                    (dates[-1], float(values[-1] * request.initial_amount))],
        symbols=[request.benchmark_symbol],
        effective_start=dates[0],
        effective_end=dates[-1],
        truncation_cause=None,
        fallback_dates=[],
    )
    return compute_metrics(stand_in, request)


def summarize(metrics: dict) -> dict:
    return {key: metrics.get(key) for key in SUMMARY_KEYS}


def _write_to_s3(key: str, payload: dict) -> None:
    with data_getter.fs.open(f"s3://{S3_BUCKET}/{key}", 'wb') as handle:
        handle.write(json.dumps(payload).encode('utf-8'))


def _read_from_s3(key: str) -> dict:
    with data_getter.fs.open(f"s3://{S3_BUCKET}/{key}", 'rb') as handle:
        return json.loads(handle.read())


def store_payload(user_id, task_id, payload: dict) -> str:
    cache.set(CACHE_KEY.format(task_id=task_id),
              gzip.compress(json.dumps(payload).encode('utf-8')),
              timeout=CACHE_TIMEOUT)
    key = f"{S3_PREFIX}/{user_id}/{task_id}.json"
    try:
        _write_to_s3(key, payload)
    except Exception:
        # Redis already has it and the UI reads from there; a durable-write
        # failure must not fail a completed run.
        return ''
    return key


def load_payload(run) -> dict | None:
    compressed = cache.get(CACHE_KEY.format(task_id=run.task_id))
    if compressed:
        try:
            return json.loads(gzip.decompress(compressed))
        except Exception:
            cache.delete(CACHE_KEY.format(task_id=run.task_id))
    if not run.result_key:
        return None
    try:
        return _read_from_s3(run.result_key)
    except Exception:
        return None
