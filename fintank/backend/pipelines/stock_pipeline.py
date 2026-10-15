"""StockDataPipeline — the Fintank market-data ETL as one class.

Every function from `stock_data_getter_v2.ipynb`'s definition cells, moved
behind one object so a notebook only has to *call* things. Static reference
data (index tickers, field mappings, FRED series, …) lives in
`pipeline_config.py`.

    from pipelines.stock_pipeline import StockDataPipeline
    p = StockDataPipeline()
    p.status()                                  # what's on disk, how stale
    p.fetch_stock_prices(from_date="1999-01-01")
    p.build_price_parquets()
    p.upload_stock_prices()

Methods are named by stage so the flow reads off the method list:

    refresh_*   quarterly universe refresh   (live API, changes membership)
    fetch_*     pull from FMP/FRED → JSON    (live API, the expensive stage)
    build_*     JSON → parquet               (local only, no API calls)
    upload_*    parquet → S3                 (live AWS)
    status      inspect what's on disk       (local, read-only)

Name changes from the notebook (behaviour is unchanged in every case):

    get_index_constituents                          → refresh_constituents
    save_or_update_constituent_prices               → fetch_stock_prices
    save_or_update_etf_prices                       → fetch_etf_prices
    save_or_update_constituent_profiles             → fetch_profiles
    save_or_update_etf_profiles                     → fetch_etf_profiles
    save_or_update_constituent_financial_statements → fetch_financial_statements
    save_or_update_constituent_ratios               → fetch_ratios
    save_or_update_current_constituent_ratios       → fetch_ttm_ratios
    save_or_update_sector_and_subsector_dataframe   → fetch_sector_history
    get_index_price_history                         → fetch_index_prices
    save_or_update_fred_series                      → fetch_fred_series
    get_sector_returns                              → get_sector_snapshot
    create_stock_price_dataframe                    → build_price_parquets
    create_fundamentals_dataframes                  → build_fundamentals_parquets
    create_factor_metrics_dataframes                → build_factor_metrics
    create_index_contr_to_var                       → build_contr_to_var
    create_econ_dataframes                          → build_econ_parquets
    create_relative_performance_dataframes          → build_relative_performance
    upload_index_files                              → upload_index_prices
    upload_stock_prices_files                       → upload_stock_prices
    upload_constituent_data                         → upload_fundamentals
    upload_constituent_lists                        → upload_constituents
    upload_factor_metrics_files                     → upload_factor_metrics
    upload_contr_to_var_files                       → upload_contr_to_var
    upload_econ_files                               → upload_econ

Two deliberate changes from the notebook, both flagged where they occur:

  1. ONE shared rate limiter per pipeline instance, instead of a fresh one
     per function. The notebook reset the counter at the start of every
     fetcher, so running two back to back could put ~590 calls in a minute
     against a 295/min budget. See RateLimiter.
  2. Paths resolve against `self.root` (this file's directory by default)
     rather than the process working directory, so a notebook in another
     folder still finds the data. S3 keys are unchanged — they are computed
     as the path relative to root, which is what the notebook's "./" prefix
     stripping produced.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import time
import warnings

import boto3
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(MODULE_DIR)
# Local data stays beside the notebooks; on AWS, PIPELINE_DATA_ROOT is /data.
DEFAULT_DATA_ROOT = os.path.join(BACKEND_DIR, "class_files")
DEFAULT_BUCKET = "thetradingfloor"
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from pipelines import pipeline_config as cfg  # noqa: E402
from pipelines.factor_windows import WINDOWS, window_return_and_std  # noqa: E402
from pipelines.results import StageResult, redact  # noqa: E402

warnings.filterwarnings("ignore")

V3_BASE = "https://financialmodelingprep.com/api/v3"
STABLE_BASE = "https://financialmodelingprep.com/stable"
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
START_DATE = "1999-01-01"

# Columns that come from FMP rather than being computed by the metric
# calculators — what we keep from an existing file before recomputing.
RAW_PRICE_COLS = ["open", "high", "low", "close", "adjClose", "volume", "label"]

# Columns read from the monthly parquets by build_relative_performance.
REL_PERF_COLS = ["adjClose", "3_month_returns", "1_yr_returns", "3_yr_returns"]

FACTOR_NUMERIC_COLS = (
    list(WINDOWS) + ["ytd"]
    + [f"{label}STD" for label in list(WINDOWS) + ["YTD"]]
    + ["beta"] + list(cfg.FACTOR_FIELD_SOURCES)
)

# Named FACTOR_METRICS_COLUMNS, not FACTOR_COLUMNS: factor_tools.py on the
# backend uses that name for a different thing (response key → column).
FACTOR_METRICS_COLUMNS = (["symbol", "name", "sector", "as_of"]
                          + list(WINDOWS) + ["ytd"]
                          + ["1MSTD", "3MSTD", "6MSTD", "YTDSTD"]
                          + ["beta"] + list(cfg.FACTOR_FIELD_SOURCES))

# The 8 window columns nulled for stale rows: every return and its paired
# stdev, nothing else. Ratios/beta/sector/name/as_of stay put, so the row
# survives for everything except return-ranked charts.
FACTOR_WINDOW_COLUMNS = (["1M", "3M", "6M", "ytd"]
                         + ["1MSTD", "3MSTD", "6MSTD", "YTDSTD"])


class RateLimiter:
    """Counts FMP calls and sleeps when the per-minute budget is spent.

    One of these is shared by every fetcher on a pipeline instance. The
    notebook created a fresh limiter inside each fetcher, which reset the
    count to zero at every function boundary — so `fetch_stock_prices()`
    ending at 200 calls followed immediately by `fetch_etf_prices()` could
    put ~495 calls into one minute against a 295 budget.
    """

    def __init__(self, max_calls=295, pause=60):
        self.max_calls, self.pause, self.count = max_calls, pause, 0

    def tick(self, n=1):
        self.count += n
        if self.count >= self.max_calls:
            print(f"\nSleeping {self.pause}s to respect API limit...")
            time.sleep(self.pause)
            self.count = 0


class StockDataPipeline:
    """Fetch → transform → upload for the Fintank market-data lake.

    root:     folder holding stock_data_json/, stock_data/, index_data/,
              econ_data/. Defaults to $PIPELINE_DATA_ROOT, else
              backend/class_files/.
    env_path: .env with FMP_API / AWS_* / FRED_API. Defaults to backend/.env.
    """

    def __init__(self, root=None, env_path=None, max_calls=295, pause=60):
        self.root = os.path.abspath(
            root or os.getenv("PIPELINE_DATA_ROOT") or DEFAULT_DATA_ROOT)
        load_dotenv(env_path or os.path.join(BACKEND_DIR, ".env"))

        self.fmp_api = os.getenv("FMP_API")
        self.fred_api = os.getenv("FRED_API")
        self.aws_key = os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.bucket = os.getenv("AWS_BUCKET_NAME") or DEFAULT_BUCKET
        assert self.fmp_api, "FMP_API missing — check backend/.env"

        self.limiter = RateLimiter(max_calls=max_calls, pause=pause)
        self._s3 = None

    def __repr__(self):
        creds = " ".join(
            f"{name}={'set' if value else 'MISSING'}"
            for name, value in [("FMP", self.fmp_api), ("AWS", self.aws_key),
                                ("FRED", self.fred_api)])
        return (f"StockDataPipeline(root={self.root!r})\n"
                f"  credentials: {creds}\n"
                f"  bucket:      {self.bucket or 'MISSING'}\n"
                f"  throttle:    {self.limiter.max_calls} calls / "
                f"{self.limiter.pause}s pause")

    # ─────────────────────────────────────────────────────────────────────
    # Paths. Local layout mirrors the S3 key layout: a file written to
    # {root}/stock_data/... uploads to s3://{bucket}/stock_data/... unchanged.
    #
    # Layout is FLAT per constituent list: stock_prices/sp500/,
    # stock_prices/etfs/ … — no us/canada/intl nesting (the v1 notebook
    # nested {universe}/{sub_universe}, which made reads depth-dependent).
    # ─────────────────────────────────────────────────────────────────────
    @property
    def json_root(self):
        return os.path.join(self.root, "stock_data_json")

    @property
    def parquet_root(self):
        return os.path.join(self.root, "stock_data")

    @property
    def index_root(self):
        return os.path.join(self.root, "index_data")

    @property
    def econ_dir(self):
        """Parquet staging for macro data == its S3 prefix."""
        return os.path.join(self.root, "econ_data")

    @property
    def index_prices_dir(self):
        """This pipeline's incremental index parquets: {daily,monthly}/."""
        return os.path.join(self.index_root, "index_prices_v2")

    @property
    def contr_to_var_dir(self):
        return os.path.join(self.index_root, "contr_to_var")

    @property
    def factor_metrics_dir(self):
        return os.path.join(self.parquet_root, "factor_metrics")

    @property
    def revenue_segments_dir(self):
        """Per-symbol revenue segmentation JSON.

        Lives under stock_data/ (not stock_data_json/) because for this one
        dataset the fetched JSON *is* the upload artifact — there is no
        transform stage and no parquet, so there is no second copy to keep.
        Putting it here holds the pipeline's invariant that a local path is
        its S3 key verbatim, which is what lets upload_revenue_segments()
        call upload_folder() with no prefix override.
        """
        return os.path.join(self.parquet_root, "revenue_segments")

    @property
    def econ_json_dir(self):
        return os.path.join(self.json_root, "econ_data")

    def json_dir(self, data_type, sub_universe):
        """Flat folder for a stock-level data type, e.g.
        json_dir('stock_prices', 'sp500') → .../stock_data_json/stock_prices/sp500/"""
        return os.path.join(self.json_root, data_type, sub_universe) + os.sep

    def constituents_path(self, const_key):
        """Membership JSON for one constituent list. Every fetcher reads this
        to know which symbols to pull."""
        return os.path.join(self.index_root, "constituents",
                            f"{const_key}_constituents.json")

    def price_parquet_dir(self, frequency, sub_universe):
        """Per-symbol price metric parquets, e.g.
        price_parquet_dir('daily', 'sp500') → .../stock_data/stock_prices/daily/sp500"""
        return os.path.join(self.parquet_root, "stock_prices", frequency,
                            sub_universe)

    @staticmethod
    def sub_universe_for(const_key):
        """Folder name for a constituent key: 'sp500_const' → 'sp500';
        the ETF snapshot 'etf_data' → 'etfs'."""
        return "etfs" if const_key == "etf_data" else const_key.removesuffix("_const")

    # ─────────────────────────────────────────────────────────────────────
    # Plumbing: URLs, HTTP, JSON/parquet writes.
    #
    # Endpoint generation was verified live against our key on 2026-07-31.
    #   [v3-only]  stable gates this behind a higher plan (403 "Premium Query
    #              Parameter" / "Restricted Endpoint") or drops fields we
    #              depend on — do NOT migrate without re-verifying.
    #   [stable]   verified working on our plan.
    # ─────────────────────────────────────────────────────────────────────
    def _url(self, base, path, **params):
        params["apikey"] = self.fmp_api
        query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
        return f"{base}/{path}?{query}"

    def _v3(self, path, **params):
        return self._url(V3_BASE, path, **params)

    def _stable(self, path, **params):
        return self._url(STABLE_BASE, path, **params)

    # [v3-only] Canadian index symbols 403 on every stable price route under
    # the current plan; v3 serves them fine.
    def _index_history_url(self, symbol, from_date=START_DATE):
        return self._v3(f"historical-price-full/{symbol}", **{"from": from_date})

    # [v3-only] stable/etf/holdings is a Restricted Endpoint (Ultimate plan).
    # The entire constituent pipeline hangs off this.
    def _etf_holder_url(self, etf_symbol):
        return self._v3(f"etf-holder/{etf_symbol}")

    # [v3-only] stable/etf-list returns only {symbol, name} — no 'exchange'.
    def _etf_list_url(self):
        return self._v3("etf/list")

    # [v3-only] stable historical-price-eod/full drops adjClose (the metric
    # calculators dropna on adjClose); the dividend-adjusted variant drops raw
    # OHLC, which would double the call count per symbol.
    def _prices_url(self, symbol, from_date=None):
        return self._v3(f"historical-price-full/{symbol}", **{"from": from_date})

    # [stable] FIELD_MAPPINGS profile dicts use the stable names.
    def _profile_url(self, symbol):
        return self._stable("profile", symbol=symbol)

    # [v3-only for now] stable renames fillingDate→filingDate,
    # calendarYear→fiscalYear, epsdiluted→epsDiluted, and DROPS fields mapped
    # to Django columns (grossProfitRatio, ebitdaratio, operatingIncomeRatio,
    # incomeBeforeTaxRatio, netIncomeRatio, link, finalLink). Migrate only
    # together with a derivation step for those ratios.
    def _income_url(self, symbol):
        return self._v3(f"income-statement/{symbol}", period="quarter")

    def _balance_url(self, symbol):
        return self._v3(f"balance-sheet-statement/{symbol}", period="quarter")

    def _cashflow_url(self, symbol):
        return self._v3(f"cash-flow-statement/{symbol}", period="quarter")

    # [stable] limit=400: stable defaults to FIVE rows (v3 returned full
    # history — 164 quarters for AAPL); probed 2026-08-01.
    def _ratios_url(self, symbol, limit=400):
        return self._stable("ratios", symbol=symbol, period="quarter", limit=limit)

    def _key_metrics_url(self, symbol, limit=400):
        return self._stable("key-metrics", symbol=symbol, period="quarter",
                            limit=limit)

    # [v3-only] stable/ratios-ttm drops 31 v3 fields incl. peRatioTTM,
    # dividendYielTTM, payoutRatioTTM — all mapped in company_ratios_ttm.
    def _ratios_ttm_url(self, symbol):
        return self._v3(f"ratios-ttm/{symbol}")

    # [v3-only for now] stable/key-metrics-ttm works but renames fields that
    # FIELD_MAPPINGS['company_metrics_ttm'] maps; keep v3 until that is audited.
    def _metrics_ttm_url(self, symbol):
        return self._v3(f"key-metrics-ttm/{symbol}")

    # [stable] Verified against v4 on 2026-09-26: identical numbers, but stable
    # also carries reportedCurrency and a top-level date/fiscalYear/period.
    # `structure` and `limit` are deliberately NOT passed — stable accepts and
    # silently ignores both (see cfg.SEGMENTATION_DATASETS).
    def _segmentation_url(self, symbol, kind, period="annual"):
        return self._stable(cfg.SEGMENTATION_DATASETS[kind], symbol=symbol,
                            period=period)

    # [stable] already stable in the original notebook
    def _sector_history_url(self, sector, exchange, from_date, to_date=None):
        return self._stable("historical-sector-performance", sector=sector,
                            exchange=exchange,
                            **{"from": from_date, "to": to_date})

    def _sector_pe_url(self, sector, exchange, from_date, to_date=None):
        return self._stable("historical-sector-pe", sector=sector,
                            exchange=exchange,
                            **{"from": from_date, "to": to_date})

    def _fred_url(self, series_id, observation_start=None):
        url = (f"{FRED_BASE}?series_id={series_id}"
               f"&api_key={self.fred_api}&file_type=json")
        if observation_start:
            url += f"&observation_start={observation_start}"
        return url

    @staticmethod
    def _get(url, timeout=30):
        """GET a URL and return parsed JSON; raises on HTTP errors."""
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _write_parquet(data: pd.DataFrame, file_name: str):
        """Write a DataFrame to parquet, creating parent folders as needed."""
        os.makedirs(os.path.dirname(file_name), exist_ok=True)
        data.to_parquet(file_name, engine="pyarrow", index=True)
        return file_name

    @staticmethod
    def _merge_rows_by_date(existing_rows, new_rows):
        """Merge two lists of dicts keyed on 'date'; new rows win on collision
        (a re-fetched date may correct a partial session). Newest first.
        Returns (merged, number_of_new_dates)."""
        by_date = {r["date"]: r for r in existing_rows
                   if isinstance(r, dict) and "date" in r}
        added = 0
        for r in new_rows:
            if isinstance(r, dict) and "date" in r:
                added += r["date"] not in by_date
                by_date[r["date"]] = r
        merged = sorted(by_date.values(), key=lambda r: r["date"], reverse=True)
        return merged, added

    def _save_json(self, data, filename, update=False):
        """Write JSON, creating parent folders. With update=True, merge by
        'date' instead of overwriting; supports both bare row lists and FMP
        price payloads shaped {'symbol': ..., 'historical': [rows]}.

        Fixes a data-loss bug in the original: dict-shaped price payloads fell
        through its list-only merge and silently OVERWROTE the file, so an
        update run with from_date set replaced full history with a few weeks.
        """
        os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)

        if not update or not os.path.exists(filename):
            with open(filename, "w") as f:
                json.dump(data, f)
            return

        with open(filename, "r") as f:
            existing = json.load(f)

        if (isinstance(data, dict) and isinstance(data.get("historical"), list)
                and isinstance(existing, dict)
                and isinstance(existing.get("historical"), list)):
            existing["historical"], _ = self._merge_rows_by_date(
                existing["historical"], data["historical"])
            merged = existing
        elif isinstance(data, list) and isinstance(existing, list):
            merged, _ = self._merge_rows_by_date(existing, data)
        else:
            merged = data  # incompatible shapes → overwrite (original behavior)

        with open(filename, "w") as f:
            json.dump(merged, f)

    # ─────────────────────────────────────────────────────────────────────
    # Metric calculators. Pure functions — no I/O, no config; kept static so
    # they can be tested and reused directly on any OHLC frame.
    # ─────────────────────────────────────────────────────────────────────
    @staticmethod
    def daily_metrics(raw_data: pd.DataFrame, ma_col: str = "adjClose") -> pd.DataFrame:
        """Daily returns, rolling volatility/return-to-risk, up/down day counts,
        and moving averages.

        ma_col: series the moving averages are computed on. The original used
        the first column after dropping 'date' (i.e. 'open' — almost certainly
        unintended); default is adjClose. Pass ma_col='open' to reproduce the
        old files bit-for-bit.
        """
        df = raw_data.copy()
        df = df.loc[~df.index.duplicated()].dropna(subset=["adjClose"])
        df["returns"] = df["adjClose"].pct_change()
        df["up_days"] = (df["returns"] > 0).astype(int)
        df["down_days"] = (df["returns"] < 0).astype(int)

        for w in [10, 20, 50, 120, 200]:
            df[f"{w}_day_ma"] = df[ma_col].rolling(w).mean()

        r1 = df["returns"] + 1
        windows = [
            ("30_day",  "30",   30,  False),
            ("60_day",  "60",   60,  False),
            ("90_day",  "90",   90,  False),
            ("120_day", "120",  120, False),
            ("1_yr",    "1_yr", 252, False),
            ("3_yr",    "3_yr", 756, True),
        ]

        for prefix, suffix, w, annualise in windows:
            if len(df) < w:
                continue
            cum = r1.rolling(w).apply(np.prod, raw=True)
            ret = (cum ** (1 / 3) - 1) if annualise else (cum - 1)
            vol = df["returns"].rolling(w).std() * np.sqrt(252)
            df[f"{prefix}_returns"] = ret
            df[f"{prefix}_volatility"] = vol
            df[f"{prefix}_return_to_risk"] = ret / vol
            df[f"number_of_up_days_{suffix}"] = df["up_days"].rolling(w).sum()
            df[f"number_of_down_days_{suffix}"] = df["down_days"].rolling(w).sum()
            df[f"up_down_days_{suffix}"] = (
                df[f"number_of_up_days_{suffix}"] / df[f"number_of_down_days_{suffix}"]
            )

        return df

    @staticmethod
    def monthly_metrics(raw_data: pd.DataFrame) -> pd.DataFrame:
        """Monthly returns, rolling volatility/return-to-risk, and up/down month
        counts, on a month-end resampled frame."""
        df = raw_data.copy()
        df = df.loc[~df.index.duplicated()].dropna(subset=["adjClose"])
        df["returns"] = df["adjClose"].pct_change()
        df["up_months"] = (df["returns"] > 0).astype(int)
        df["down_months"] = (df["returns"] < 0).astype(int)
        df["running_up_months"] = df["up_months"].cumsum()
        df["running_down_months"] = df["down_months"].cumsum()
        df["up_down_months"] = df["running_up_months"] / df["running_down_months"]

        r1 = df["returns"] + 1
        windows = [
            ("3_month", "3",    3,  False),
            ("6_month", "6",    6,  False),
            ("9_month", "9",    9,  False),
            ("1_yr",    "1_yr", 12, False),
            ("3_yr",    "3_yr", 36, True),
        ]

        for prefix, suffix, w, annualise in windows:
            if len(df) < w:
                continue
            cum = r1.rolling(w).apply(np.prod, raw=True)
            ret = (cum ** (1 / 3) - 1) if annualise else (cum - 1)
            vol = df["returns"].rolling(w).std() * np.sqrt(12)
            df[f"{prefix}_returns"] = ret
            df[f"{prefix}_volatility"] = vol
            df[f"{prefix}_return_to_risk"] = ret / vol
            df[f"number_of_up_months_{suffix}"] = df["up_months"].rolling(w).sum()
            df[f"number_of_down_months_{suffix}"] = df["down_months"].rolling(w).sum()

        return df

    # ═════════════════════════════════════════════════════════════════════
    # STAGE 0 — Universe (quarterly). Index membership churns on rebalance
    # dates. Every fetcher below reads these files to know which symbols to
    # pull, so this must run FIRST when it runs at all.
    # ═════════════════════════════════════════════════════════════════════
    def refresh_constituents(self, include_etf_list=True):
        """Refresh index membership → index_data/constituents/{key}_constituents.json.

        For each key in CONSTITUENT_PROXY_ETFS, fetch the index's members via
        the v3 etf-holder proxy ETF and keep rows carrying an 'asset' symbol.
        With include_etf_list=True also refreshes the tradable-ETF snapshot
        (v3 etf/list filtered to ETF_EXCHANGE_FILTER) as etf_data_constituents.json.

        On a failed or empty fetch the key is skipped and any existing file is
        left in place — the constituent JSONs drive every downstream fetcher,
        so a bad refresh must not blank them.

        Returns a StageResult; detail["lists"][key] = {"status": "updated" | "kept", "previous", "new", "error"}.
        """
        result = StageResult("refresh_constituents")
        lists = result.detail.setdefault("lists", {})

        def previous_count(path):
            if not os.path.exists(path):
                return None
            with open(path) as f:
                return len(json.load(f))

        def refresh(key, fetch_rows):
            path = self.constituents_path(key)
            previous = previous_count(path)
            try:
                rows = fetch_rows()
                if previous is not None and len(rows) < 0.5 * previous:
                    raise ValueError(
                        f"payload shrank {previous} → {len(rows)} — degraded FMP "
                        "feed? (seen 2026-08-02: IEFA served 138 of ~2,600 "
                        "holdings for a day)")
                self._save_json(rows, path)
                lists[key] = {"status": "updated", "previous": previous,
                              "new": len(rows), "error": None}
                result.record(True)
                print(f"{key}: {len(rows)} members")
            except Exception as e:
                lists[key] = {"status": "kept", "previous": previous,
                              "new": None, "error": redact(str(e))}
                result.record(False, key)
                print(f"{key} FAILED (existing file kept): {e}")

        for key, proxy_etf in cfg.CONSTITUENT_PROXY_ETFS.items():
            def holdings(proxy_etf=proxy_etf):
                response = self._get(self._etf_holder_url(proxy_etf))
                self.limiter.tick()
                members = [item for item in response if item.get("asset")]
                if not members:
                    raise ValueError("no rows with an 'asset' symbol in payload")
                return members
            refresh(key, holdings)

        if include_etf_list:
            def etf_list():
                etf_data = self._get(self._etf_list_url())
                self.limiter.tick()
                requested = [x for x in etf_data
                             if x.get("exchange") in cfg.ETF_EXCHANGE_FILTER]
                if not requested:
                    raise ValueError("exchange filter matched no ETFs")
                return requested
            refresh("etf_data", etf_list)

        return result

    # ═════════════════════════════════════════════════════════════════════
    # STAGE 1 — Fetch (live API). The expensive stage: ~90k FMP calls for a
    # full refresh, roughly 4 hours at the 295/min throttle.
    # ═════════════════════════════════════════════════════════════════════
    def fetch_stock_prices(self, from_date=None, constituent_keys=None,
                           limit=None, stage_name="fetch_stock_prices"):
        """Daily price history per constituent → stock_data_json/stock_prices/
        {sub_universe}/{SYMBOL}_prices.json, merged by date.

        `from_date` is passed STRAIGHT INTO THE REQUEST URL — nothing reads
        the existing file first (unlike fetch_index_prices, which self-detects).
        Three consequences:

          * The call count is the same whatever date you pass — one call per
            symbol. from_date buys payload size and parse time, not API budget.
          * The merge unions, it does not fill gaps. A from_date AFTER your
            last saved date leaves a silent hole mid-series.
          * adjClose is back-adjusted, so a symbol that splits inside the gap
            has its whole history restated. A narrow window replaces only the
            rows inside it, leaving a step discontinuity at the boundary that
            poisons every rolling window crossing it — out to 756 days.

        Because the call count is identical either way, from_date="1999-01-01"
        is the safe default for a routine top-up: same ~1h floor, immune to
        both the gap and the split seam.

        constituent_keys: subset of CONSTITUENT_PROXY_ETFS; default all eight.
        limit:            per-list member cap, for smoke-testing.

        Returns a StageResult (one attempt per symbol); detail["manifests"]
        lists the path_helpers manifests written.
        """
        keys = (list(cfg.CONSTITUENT_PROXY_ETFS) if constituent_keys is None
                else constituent_keys)
        manifests = []
        result = StageResult(stage_name)

        for const_key in keys:
            sub_universe = self.sub_universe_for(const_key)
            with open(self.constituents_path(const_key)) as f:
                members = json.load(f)
            if limit is not None:
                members = members[:limit]

            prices_dir = self.json_dir("stock_prices", sub_universe)
            universe_items, failed = {}, []

            for item in members:
                symbol = item.get("asset") or item.get("symbol")
                if not symbol:
                    continue
                try:
                    payload = self._get(self._prices_url(symbol, from_date))
                    self.limiter.tick()
                    if not payload.get("historical"):
                        raise ValueError("empty 'historical' payload")
                    self._save_json(payload, f"{prices_dir}{symbol}_prices.json",
                                    update=True)
                    universe_items[symbol] = {"prices": f"{symbol}_prices.json"}
                    result.record(True)
                except Exception as e:
                    failed.append(symbol)
                    result.record(False, f"{const_key}:{symbol}")
                    print(f"\n{const_key}: no data for {symbol}: {e}")
                print(f"\r{const_key}: {len(universe_items)} saved, "
                      f"{len(failed)} failed", end="", flush=True)
            print()

            manifest = os.path.join(self.json_root, "path_helpers", "prices",
                                    f"{sub_universe}_prices.json")
            self._save_json(universe_items, manifest)
            manifests.append(manifest)

        result.detail["manifests"] = manifests
        return result

    def fetch_etf_prices(self, from_date=None, limit=None):
        """Daily price history for the tradable-ETF snapshot, saved to
        stock_prices/etfs/. Same merge semantics as the constituent lists."""
        return self.fetch_stock_prices(from_date=from_date,
                                       constituent_keys=["etf_data"], limit=limit,
                                       stage_name="fetch_etf_prices")

    def _fetch_constituent_datasets(self, datasets, manifest_group, stage_name,
                                    constituent_keys=None, limit=None):
        """Shared driver for the per-symbol fetchers (profiles, statements,
        ratios, TTM) — one skeleton instead of four near-identical methods.

        datasets: (data_type, url_builder, file_suffix, merge) tuples.
            merge=True merges by 'date' (time series); merge=False overwrites
            (snapshots — TTM/profiles; the original's update=True on dateless
            TTM rows was a silent no-op, so those files never refreshed).
        manifest_group: writes path_helpers/{group}/{sub_universe}_{group}.json

        A symbol counts as failed if any of its datasets fails; files fetched
        before the failure are kept.
        """
        keys = (list(cfg.CONSTITUENT_PROXY_ETFS) if constituent_keys is None
                else constituent_keys)
        manifests = []
        result = StageResult(stage_name)

        for const_key in keys:
            sub_universe = self.sub_universe_for(const_key)
            with open(self.constituents_path(const_key)) as f:
                members = json.load(f)
            if limit is not None:
                members = members[:limit]

            universe_items, failed = {}, []

            for item in members:
                symbol = item.get("asset") or item.get("symbol")
                if not symbol:
                    continue
                entry = {}
                try:
                    for data_type, url_builder, suffix, merge in datasets:
                        payload = self._get(url_builder(symbol))
                        self.limiter.tick()
                        if not payload:
                            raise ValueError(f"empty {data_type} payload")
                        path = f"{self.json_dir(data_type, sub_universe)}{symbol}{suffix}"
                        self._save_json(payload, path, update=merge)
                        entry[data_type] = f"{symbol}{suffix}"
                    universe_items[symbol] = entry
                    result.record(True)
                except Exception as e:
                    failed.append(symbol)
                    result.record(False, f"{const_key}:{symbol}")
                    print(f"\n{const_key}: {symbol} failed: {e}")
                print(f"\r{const_key}: {len(universe_items)} saved, "
                      f"{len(failed)} failed", end="", flush=True)
            print()

            manifest = os.path.join(self.json_root, "path_helpers",
                                    manifest_group,
                                    f"{sub_universe}_{manifest_group}.json")
            self._save_json(universe_items, manifest)
            manifests.append(manifest)

        result.detail["manifests"] = manifests
        return result

    def fetch_profiles(self, constituent_keys=None, limit=None):
        """Company profiles for every constituent (stable /profile — the
        FIELD_MAPPINGS profile dicts use the stable names). Snapshot: files
        are overwritten each run."""
        return self._fetch_constituent_datasets(
            [("company_profiles", self._profile_url, "_profile.json", False)],
            manifest_group="profiles", stage_name="fetch_profiles",
            constituent_keys=constituent_keys, limit=limit)

    def fetch_etf_profiles(self, limit=None):
        """Profiles for the tradable-ETF snapshot → company_profiles/etfs/."""
        return self._fetch_constituent_datasets(
            [("company_profiles", self._profile_url, "_profile.json", False)],
            manifest_group="profiles", stage_name="fetch_etf_profiles",
            constituent_keys=["etf_data"], limit=limit)

    def fetch_financial_statements(self, constituent_keys=None, limit=None):
        """Quarterly income/balance/cash-flow statements (v3 — stable drops
        mapped Django fields). Merged by date, so reruns only add new quarters.

        No date parameter: always the full window. ~30,400 calls, the longest
        stage at roughly 2 hours.
        """
        return self._fetch_constituent_datasets(
            [("income_statements", self._income_url, "_income_statement.json", True),
             ("balance_sheet_statements", self._balance_url, "_balance_sheet.json", True),
             ("cash_flow_statements", self._cashflow_url, "_cash_flow.json", True)],
            manifest_group="fundamentals", stage_name="fetch_financial_statements",
            constituent_keys=constituent_keys, limit=limit)

    def fetch_ratios(self, constituent_keys=None, limit=None):
        """Quarterly ratios + key metrics (stable). Merged by date. No date
        parameter — always the full window. ~20,200 calls."""
        return self._fetch_constituent_datasets(
            [("ratios", self._ratios_url, "_ratios.json", True),
             ("metrics", self._key_metrics_url, "_metrics.json", True)],
            manifest_group="metrics", stage_name="fetch_ratios",
            constituent_keys=constituent_keys, limit=limit)

    def fetch_ttm_ratios(self, constituent_keys=None, limit=None):
        """TTM ratios + key metrics (v3 — stable drops 31 mapped fields).
        Snapshots: files are overwritten each run. The original passed
        update=True, but TTM rows carry no 'date', so its merge was a no-op
        and the files never refreshed after first write. ~20,200 calls."""
        return self._fetch_constituent_datasets(
            [("ratios_ttm", self._ratios_ttm_url, "_ratios_ttm.json", False),
             ("metrics_ttm", self._metrics_ttm_url, "_metrics_ttm.json", False)],
            manifest_group="metrics_ttm", stage_name="fetch_ttm_ratios",
            constituent_keys=constituent_keys, limit=limit)

    # Single implementation lives in pipeline_config so research_utils shares it
    # rather than keeping a second copy of the shape branch (the last second
    # copy silently returned the wrong period's numbers — DATA_UPLOAD.md bug 10).
    _normalise_segmentation = staticmethod(cfg.normalise_segmentation_periods)

    @staticmethod
    def _segments_current(path, today, period):
        """True if `path` already holds a segments file written today for the
        same period — the resume check. Any read/parse problem returns False so
        a corrupt file is refetched rather than skipped."""
        try:
            with open(path) as f:
                existing = json.load(f)
        except Exception:
            return False
        return (existing.get("as_of") == today
                and existing.get("period") == period
                and not existing.get("incomplete_kinds"))

    def fetch_revenue_segments(self, constituent_keys=None, period="annual",
                               limit=None, resume=False):
        """Revenue by product and by geography, one JSON per company →
        stock_data/revenue_segments/{SYMBOL}_segments.json.

        Deliberately NOT built on _fetch_constituent_datasets. That driver
        treats a falsy payload as a failure (`raise ValueError("empty …")`),
        which is right for prices and statements but wrong here: an empty
        payload is the NORMAL, correct answer for most of this universe, and
        reporting it as a failure would both mislead and break the run books'
        "hundreds of failures means the feed is degraded, stop" heuristic.
        So this counts three outcomes and only `errors` is retry-worthy:

            with_data  at least one segment kind returned rows
            no_data    HTTP 200 and [] from both kinds — nothing disclosed
            errors     HTTP error or exception — the only retry-worthy bucket

        The two kinds are INDEPENDENT calls. If one fails and the other
        succeeds the file is still written with whatever came back, and the
        symbol lands in BOTH `with_data` and `errors`, with the failed kind
        named in the file's `incomplete_kinds`. A symbol counted in two buckets
        is deliberate: it lets a retry re-fetch only the kind that actually
        failed instead of paying for both again.

        DEDUPED ACROSS LISTS. Unlike every other fetcher, a symbol is fetched
        once even when it appears in several constituent lists: segmentation is
        company-level and carries no per-universe variation, so the per-list
        re-fetch the other stages accept would be pure waste. Across the eight
        equity lists that is 6,375 unique symbols rather than 10,482 —
        12,750 calls instead of 20,964, ~43 min instead of ~1.2 h.

        Written as a SNAPSHOT (overwrite, no merge by date). Every call returns
        full history, and FMP restates segment history as disclosure changes
        (AAPL's 2010 row carries only 'Retail'), so merging would preserve
        superseded restatements forever.

        Symbols where BOTH kinds are empty get no file at all — a 404 is the
        honest "no segmentation disclosed", and writing them would add
        thousands of hollow S3 objects. Every outcome is still recorded in the
        manifest, which is bookkeeping only and never uploaded. The manifest is
        rewritten after EVERY list, not just at the end, so a crash late in the
        run doesn't erase the bookkeeping for the hours that succeeded; its
        `complete` flag is False until the run finishes.

        period: 'annual' (default) or 'quarter'. Quarter is ~9 months fresher
                but doubles the call count; annual is the pipeline default.
        limit:  per-list member cap, for smoke-testing.
        resume: skip symbols whose file was already written TODAY for the same
                period and is not flagged incomplete. Default False, so a plain
                call refreshes everything like the other snapshot fetchers.
                Pass True to continue an interrupted run without re-paying for
                the symbols that already landed.

        Returns a StageResult: saved = with data, no_data = nothing disclosed,
        failed = errors (the only retry-worthy bucket).
        """
        keys = (list(cfg.SEGMENTATION_CONSTITUENT_KEYS)
                if constituent_keys is None else constituent_keys)
        out_dir = self.revenue_segments_dir
        os.makedirs(out_dir, exist_ok=True)
        today = datetime.date.today().isoformat()

        manifest = os.path.join(self.json_root, "path_helpers", "segments",
                                f"segments_{period}.json")
        seen = {}
        with_data, no_data, errors, skipped = {}, [], {}, []

        def write_manifest():
            """Checkpointed after every list, not just at the end: a crash at
            symbol 6,000 of 6,375 would otherwise lose the whole run's
            bookkeeping even though the per-symbol files are safe on disk."""
            self._save_json({
                "as_of": today,
                "period": period,
                "constituent_keys": keys,
                "complete": False,
                "symbols_seen": len(seen),
                "universe_of": seen,
                "with_data": with_data,
                "no_data": sorted(no_data),
                "errors": errors,
                "skipped_already_current": sorted(skipped),
            }, manifest)

        for const_key in keys:
            sub_universe = self.sub_universe_for(const_key)
            with open(self.constituents_path(const_key)) as f:
                members = json.load(f)
            if limit is not None:
                members = members[:limit]

            for item in members:
                symbol = item.get("asset") or item.get("symbol")
                if not symbol or symbol in seen:
                    continue
                seen[symbol] = sub_universe

                # Never let these reach the wire or the output path: a comma
                # returns 200/[] (indistinguishable from "nothing disclosed"),
                # and a slash would make _save_json's makedirs create a stray
                # subdirectory, breaking the flat one-path-per-key contract.
                bad = [c for c in cfg.SEGMENTATION_UNSAFE_CHARS if c in symbol]
                if bad:
                    errors[symbol] = f"unsafe character(s) {bad} in symbol"
                    print(f"\n{const_key}: refusing {symbol!r} — "
                          f"unsafe character(s) {bad}")
                    continue

                out_path = os.path.join(out_dir, f"{symbol}_segments.json")
                if resume and self._segments_current(out_path, today, period):
                    skipped.append(symbol)
                    continue

                segments, currency, failed_kinds = {}, None, {}
                for kind in cfg.SEGMENTATION_DATASETS:
                    try:
                        payload = self._get(
                            self._segmentation_url(symbol, kind, period))
                        self.limiter.tick()
                        # Normalisation is inside the try on purpose. It is a
                        # pure function today, but an unguarded raise here would
                        # propagate through both loops and kill a 43-minute run.
                        rows, kind_currency, anomalies = \
                            self._normalise_segmentation(payload)
                    except Exception as e:
                        # continue, NOT break: the other kind is an independent
                        # call. Breaking would throw away a success already paid
                        # for and force a retry to re-fetch both.
                        failed_kinds[kind] = str(e)
                        print(f"\n{const_key}: {symbol} {kind} failed: {e}")
                        continue

                    for note in anomalies:
                        print(f"\n{const_key}: {symbol} {kind}: {note}")
                    if rows:
                        segments[kind] = rows
                    if kind_currency:
                        if currency and kind_currency != currency:
                            print(f"\n{const_key}: {symbol} currency differs "
                                  f"between kinds: {currency!r} vs "
                                  f"{kind_currency!r} — keeping {currency!r}")
                        currency = currency or kind_currency

                # Partial success is still success: write whatever came back,
                # and record the failure separately so it can be retried on its
                # own rather than re-fetching the kind that already worked.
                if segments:
                    out = {
                        "symbol": symbol,
                        "as_of": today,
                        "period": period,
                        "reportedCurrency": currency,
                        "coverage": {kind: len(segments.get(kind, {}))
                                     for kind in cfg.SEGMENTATION_DATASETS},
                    }
                    if failed_kinds:
                        out["incomplete_kinds"] = sorted(failed_kinds)
                    for kind in cfg.SEGMENTATION_DATASETS:
                        out[kind] = segments.get(kind, {})
                    self._save_json(out, out_path)
                    with_data[symbol] = out["coverage"]
                elif not failed_kinds:
                    no_data.append(symbol)

                if failed_kinds:
                    errors[symbol] = failed_kinds

                print(f"\r{len(with_data)} with data, {len(no_data)} no data, "
                      f"{len(errors)} errors, {len(skipped)} skipped "
                      f"({len(seen)} symbols)", end="", flush=True)

            write_manifest()
        print()

        payload = json.load(open(manifest)) if os.path.exists(manifest) else {}
        payload["complete"] = True
        self._save_json(payload, manifest)

        product = sum(1 for c in with_data.values() if c.get("product"))
        geographic = sum(1 for c in with_data.values() if c.get("geographic"))
        attempted = max(len(seen) - len(skipped), 1)
        print(f"\n{len(seen)} unique symbols, {len(with_data)} files written")
        print(f"  product coverage:    {product:5d} ({product / attempted:.0%})")
        print(f"  geographic coverage: {geographic:5d} "
              f"({geographic / attempted:.0%})")
        print(f"  no data: {len(no_data)}   errors: {len(errors)}   "
              f"skipped: {len(skipped)}")
        if errors:
            print(f"  retry just the failures with "
                  f"constituent_keys=… on the affected list, or re-run with "
                  f"resume=True to skip the {len(with_data)} already written")

        by_universe = {}
        for symbol, sub in seen.items():
            slot = by_universe.setdefault(sub, [0, 0])
            slot[0] += 1
            slot[1] += symbol in with_data
        print("\n  coverage by list (symbols first seen in that list):")
        for sub in sorted(by_universe):
            total, hit = by_universe[sub]
            print(f"    {sub:15s} {hit:5d}/{total:<5d} ({hit / max(total, 1):.0%})")
        print(f"manifest → {manifest}")
        return StageResult(
            "fetch_revenue_segments",
            attempted=len(seen) - len(skipped),
            saved=len(with_data),
            failed=len(errors),
            no_data=len(no_data),
            failed_items=sorted(errors),
            detail={"manifest": manifest, "skipped": len(skipped)},
        )

    def fetch_index_prices(self, from_date=START_DATE, indexes=None):
        """Index price history → index_data/index_prices_v2/{daily,monthly}/.

        THE ONE SELF-DETECTING FETCHER. For each index: if a daily parquet
        already exists, fetch only from its last saved date (that date is
        re-fetched and replaced, in case the last save caught a partial
        session); otherwise fetch the full history from `from_date`. Metrics
        are recomputed over the combined raw history so rolling windows stay
        correct across the append seam, then both parquets are rewritten.

        Call it bare — `from_date` only applies on a cold backfill. Indexes
        do not split, so the narrow-window seam that makes self-detection
        unsafe for stock prices does not arise here.

        Stays on v3 historical-price-full: most tickers are ^-symbols,
        plan-gated on stable. 65 calls.

        indexes: optional list of INDEX_TICKERS keys to refresh a subset.
        Returns a StageResult (one attempt per index); failures are collected
        and reported, not raised, so one dead ticker doesn't kill the run.
        """
        keys = list(cfg.INDEX_TICKERS) if indexes is None else indexes
        result, failed = StageResult("fetch_index_prices"), []

        for n, key in enumerate(keys, start=1):
            ticker = cfg.INDEX_TICKERS[key]["ticker"]
            daily_path = os.path.join(self.index_prices_dir, "daily",
                                      f"{key}_prices.parquet")
            monthly_path = os.path.join(self.index_prices_dir, "monthly",
                                        f"{key}_prices.parquet")
            try:
                existing_raw, last_date = self._load_existing_raw(daily_path)
                fetch_from = (last_date.strftime("%Y-%m-%d")
                              if last_date is not None else from_date)

                response = self._get(self._index_history_url(ticker, fetch_from))
                historical = response.get("historical")

                if not historical:
                    if existing_raw is None:
                        raise ValueError("empty 'historical' payload")
                    result.record(True)
                    print(f"[{n}/{len(keys)}] {key}: no new rows since {fetch_from}")
                    continue

                df = pd.DataFrame(historical)
                df = df.set_index(pd.to_datetime(df["date"]))
                new_raw = df[::-1].drop(
                    columns=["date", "unadjustedVolume", "change",
                             "changePercent", "changeOverTime", "vwap"],
                    errors="ignore",
                )

                if existing_raw is not None:
                    combined = pd.concat([existing_raw, new_raw])
                    # keep="last": the re-fetched overlap date wins
                    combined = combined.loc[~combined.index.duplicated(keep="last")].sort_index()
                    added = len(combined) - len(existing_raw)
                else:
                    combined = new_raw
                    added = len(combined)

                daily = self.daily_metrics(combined)
                monthly = self.monthly_metrics(combined.resample("ME").last())

                self._write_parquet(daily, daily_path)
                self._write_parquet(monthly, monthly_path)

                result.record(True)
                mode = "backfill" if existing_raw is None else "update"
                print(f"[{n}/{len(keys)}] {key}: +{added} rows ({mode}, "
                      f"{len(combined)} total) — {cfg.INDEX_TICKERS[key]['full_name']}")
            except Exception as e:
                failed.append(key)
                result.record(False, key)
                print(f"[{n}/{len(keys)}] {key} ({ticker}) FAILED: {e}")

        if failed:
            print(f"\n{len(failed)}/{len(keys)} indexes failed: {failed}")
        return result

    @staticmethod
    def _load_existing_raw(path):
        """Return (raw-columns DataFrame, last index date) from a previously
        saved parquet, or (None, None) if the file doesn't exist yet."""
        if not os.path.exists(path):
            return None, None
        existing = pd.read_parquet(path)
        raw = existing[[c for c in RAW_PRICE_COLS if c in existing.columns]]
        return raw, raw.index.max()

    def fetch_sector_history(self, from_date="2010-01-01", to_date=None,
                             exchange_keys=None, sector_keys=None):
        """Historical sector performance and sector PE per (exchange, sector),
        both stable endpoints, merged by date into
        sector_performance/{exchange}/{sector}.json and
        sector_pe/{exchange}/{sector}.json.

        110 calls at the default 5 exchanges x 11 sectors x 2 — cheap enough
        to over-fetch. NOTE: these JSONs are deliberately never uploaded; the
        app serves its sector snapshot live from FMP.
        """
        # Probed 2026-08-01: these stable endpoints return [] if 'from' is sent
        # without 'to' — so an open-ended window defaults 'to' to today.
        if from_date is not None and to_date is None:
            to_date = datetime.date.today().isoformat()
        ex_keys = list(cfg.EXCHANGES) if exchange_keys is None else exchange_keys
        sec_keys = list(cfg.SECTOR_NAMES) if sector_keys is None else sector_keys
        result, failed = StageResult("fetch_sector_history"), []

        for ex_key in ex_keys:
            exchange = cfg.EXCHANGES[ex_key]["index_name"]
            for sec_key in sec_keys:
                sector = cfg.SECTOR_NAMES[sec_key]
                try:
                    perf = self._get(self._sector_history_url(
                        sector, exchange, from_date, to_date))
                    self.limiter.tick()
                    pe = self._get(self._sector_pe_url(
                        sector, exchange, from_date, to_date))
                    self.limiter.tick()
                    if not perf and not pe:
                        raise ValueError("no data for this exchange/sector")
                    if perf:
                        self._save_json(perf, os.path.join(
                            self.json_root, "sector_performance", ex_key,
                            f"{sec_key}.json"), update=True)
                    if pe:
                        self._save_json(pe, os.path.join(
                            self.json_root, "sector_pe", ex_key,
                            f"{sec_key}.json"), update=True)
                    print(f"\r{ex_key}/{sec_key}: perf {len(perf)}, pe {len(pe)}      ",
                          end="", flush=True)
                    result.record(True)
                except Exception as e:
                    failed.append(f"{ex_key}/{sec_key}")
                    result.record(False, f"{ex_key}/{sec_key}")
                    print(f"\n{ex_key}/{sec_key} failed: {e}")
        print()
        if failed:
            print(f"{len(failed)} combos failed: {failed}")
        return result

    def fetch_fred_series(self, series_ids=None, observation_start=None):
        """FRED → stock_data_json/econ_data/{series}.json, merged by date.
        ~17 calls on the free FRED API. Full-history refetch is also cheap."""
        if not self.fred_api:
            raise RuntimeError("FRED_API missing — add it to backend/.env "
                               "(free key: fred.stlouisfed.org user account)")
        ids = cfg.FRED_SERIES if series_ids is None else series_ids
        result, failed = StageResult("fetch_fred_series"), []
        for sid in ids:
            try:
                raw = self._get(self._fred_url(sid, observation_start))
                rows = [{"date": o["date"], "value": float(o["value"])}
                        for o in raw["observations"] if o["value"] != "."]
                if not rows:
                    raise ValueError("no observations returned")
                self._save_json(
                    rows,
                    os.path.join(self.econ_json_dir, f"{sid}.json"),
                    update=True)
                print(f"\r{sid}: {len(rows)} obs      ", end="", flush=True)
                result.record(True)
            except Exception as e:
                failed.append(sid)
                result.record(False, sid)
                print(f"\n{sid} failed: {e}")
        print()
        if failed:
            print(f"{len(failed)} series failed: {failed}")
        return result

    def get_sector_snapshot(self):
        """Today's sector performance snapshot (v3 sector-performance) plus a
        market-breadth headline. Returns (rows, message); rows keep FMP's shape
        {'sector': ..., 'changesPercentage': '0.63%'}.

        Stays on v3: its changesPercentage comes as "0.63%" strings, and this
        parser and the endpoint must migrate together (stable's
        sector-performance-snapshot returns floats per exchange).

        The original hardcoded ==11 for "all sectors up" and crashed on any
        unparsable percentage; this counts against the rows actually parsed.
        """
        data = self._get(self._v3("sector-performance"))

        changes = []
        for row in data:
            try:
                changes.append(float(str(row.get("changesPercentage", "")).rstrip("%")))
            except ValueError:
                print(f"skipping unparsable row: {row}")

        positive = sum(c > 0 for c in changes)

        if changes and positive == len(changes):
            message = "All Sectors Outperformed"
        elif positive >= 6:
            message = "General Positive Day in Markets"
        elif positive <= 1:
            message = "Red Across the Board"
        else:
            message = "Red Mostly Across The Board"

        return data, message

    def get_index_sector_exposure(self, const_key):
        """Sector weights of the index's proxy ETF. The one piece with no
        local source — 1 live v3 etf-sector-weightings call."""
        etf = cfg.CONSTITUENT_PROXY_ETFS[const_key]
        data = self._get(self._v3(f"etf-sector-weightings/{etf}"))
        rows = [{"sector": r["sector"],
                 "weight": float(str(r["weightPercentage"]).rstrip("%"))}
                for r in data]
        return (pd.DataFrame(rows).set_index("sector")
                .sort_values("weight", ascending=False))

    # ═════════════════════════════════════════════════════════════════════
    # STAGE 2 — Transform (local only, no API calls). Every build_* method
    # recomputes from the full local JSON, so there are no append seams:
    # rolling windows are correct across whatever the fetch stage merged in.
    #
    # Order matters. build_factor_metrics reads the output of BOTH
    # build_price_parquets and build_fundamentals_parquets — run it first and
    # every symbol skips with FileNotFoundError, printing "SKIPPED — no rows
    # built" and leaving the previous snapshot in place.
    # ═════════════════════════════════════════════════════════════════════
    def build_price_parquets(self, sub_universes=None, limit=None):
        """Price JSON → per-symbol daily + monthly metric parquets at
        stock_data/stock_prices/{daily,monthly}/{sub}/{SYMBOL}_prices.parquet.

        limit: per-folder file cap, for smoke-testing.
        """
        subs = cfg.ALL_SUB_UNIVERSES if sub_universes is None else sub_universes
        result = StageResult("build_price_parquets")
        for sub in subs:
            folder = self.json_dir("stock_prices", sub)
            if not os.path.isdir(folder):
                continue
            files = [f for f in sorted(os.listdir(folder))
                     if f.endswith("_prices.json")]
            if limit is not None:
                files = files[:limit]
            done, failed = 0, 0
            for fname in files:
                symbol = fname.removesuffix("_prices.json")
                try:
                    with open(f"{folder}{fname}") as f:
                        payload = json.load(f)
                    df = pd.DataFrame(payload["historical"])
                    df = df.set_index(pd.to_datetime(df["date"]))
                    clean_df = df[::-1].drop(
                        columns=["date", "unadjustedVolume", "change",
                                 "changePercent", "changeOverTime", "vwap"],
                        errors="ignore",
                    )
                    daily = self.daily_metrics(clean_df)
                    monthly = self.monthly_metrics(clean_df.resample("ME").last())
                    self._write_parquet(daily, os.path.join(
                        self.price_parquet_dir("daily", sub),
                        f"{symbol}_prices.parquet"))
                    self._write_parquet(monthly, os.path.join(
                        self.price_parquet_dir("monthly", sub),
                        f"{symbol}_prices.parquet"))
                    done += 1
                    result.record(True)
                except Exception as e:
                    failed += 1
                    result.record(False, f"{sub}/{symbol}")
                    print(f"\n{sub}/{fname}: {e}")
                print(f"\r{sub}: {done} processed, {failed} failed",
                      end="", flush=True)
            print()
            result.detail[sub] = {"saved": done, "failed": failed}
        return result

    def build_fundamentals_parquets(self, data_types=None, sub_universes=None,
                                    limit=None):
        """Per-stock JSON → field-mapped parquet, one file per stock per data
        type: stock_data/{data_type}/{sub}/{SYMBOL}{suffix}.parquet.

        Applies FIELD_MAPPINGS so the parquet columns are the snake_case names
        the frontend already consumes; keeps only mapped columns (data types
        with mapping=None keep FMP's names unchanged). 'symbol' is injected
        where the payload lacks it (TTM rows). Columns named date/*_date are
        parsed to datetime.

        limit: per-folder file cap, for smoke-testing.
        """
        types = (list(cfg.FUNDAMENTALS_DATASETS) if data_types is None
                 else data_types)
        subs = cfg.ALL_SUB_UNIVERSES if sub_universes is None else sub_universes
        result = StageResult("build_fundamentals_parquets")

        for data_type in types:
            spec = cfg.FUNDAMENTALS_DATASETS[data_type]
            json_suffix = spec["suffix"] + ".json"
            mapping = (cfg.FIELD_MAPPINGS[spec["mapping"]] if spec["mapping"]
                       else None)

            for sub in subs:
                folder = self.json_dir(data_type, sub)
                if not os.path.isdir(folder):
                    continue
                files = sorted(f for f in os.listdir(folder)
                               if f.endswith(json_suffix))
                if limit is not None:
                    files = files[:limit]
                done, failed = 0, 0

                for fname in files:
                    symbol = fname.removesuffix(json_suffix)
                    try:
                        with open(f"{folder}{fname}") as f:
                            payload = json.load(f)
                        rows = payload if isinstance(payload, list) else [payload]
                        df = pd.DataFrame(rows)
                        if df.empty:
                            raise ValueError("no rows")
                        if "symbol" not in df.columns:
                            df["symbol"] = symbol
                        if mapping is not None:
                            keep = [k for k in mapping if k in df.columns]
                            df = df[keep].rename(columns=mapping)
                        for col in df.columns:
                            if col == "date" or col.endswith("_date"):
                                df[col] = pd.to_datetime(df[col], errors="coerce")
                        self._write_parquet(df, os.path.join(
                            self.parquet_root, data_type, sub,
                            f"{symbol}{spec['suffix']}.parquet"))
                        done += 1
                        result.record(True)
                    except Exception as e:
                        failed += 1
                        result.record(False, f"{data_type}/{sub}/{symbol}")
                        print(f"\n{data_type}/{sub}/{fname}: {e}")
                    print(f"\r{data_type}/{sub}: {done} processed, {failed} failed",
                          end="", flush=True)
                if files:
                    print()
                result.detail[f"{data_type}/{sub}"] = {"saved": done, "failed": failed}
        return result

    @staticmethod
    def _read_first_row(path):
        """Single-row fundamentals parquet → dict, or {} if absent/empty."""
        if not os.path.isfile(path):
            return {}
        df = pd.read_parquet(path)
        if df.empty:
            return {}
        return df.iloc[0].to_dict()

    def build_factor_metrics_row(self, symbol, sub_universe):
        """One symbol's factor row. Raises FileNotFoundError when the required
        price parquet is missing; optional fields become None and keep the row."""
        price_path = os.path.join(self.price_parquet_dir("daily", sub_universe),
                                  f"{symbol}_prices.parquet")
        if not os.path.isfile(price_path):
            raise FileNotFoundError("no daily price parquet")

        prices = pd.read_parquet(price_path, columns=["adjClose"])["adjClose"]
        prices = prices.dropna().sort_index()
        if len(prices) < 2:
            raise ValueError("fewer than 2 adjClose prints")

        row = {"symbol": symbol, "as_of": prices.index[-1]}

        for label in list(WINDOWS) + ["ytd"]:
            period_return, daily_std = window_return_and_std(prices, label)
            row[label] = period_return
            std_key = "YTDSTD" if label == "ytd" else f"{label}STD"
            row[std_key] = daily_std

        profile = self._read_first_row(os.path.join(
            self.parquet_root, "company_profiles", sub_universe,
            f"{symbol}_profile.parquet"))
        row["name"] = profile.get("name")
        row["sector"] = profile.get("sector")
        row["beta"] = profile.get("beta")

        sources = {
            "ratios_ttm": self._read_first_row(os.path.join(
                self.parquet_root, "ratios_ttm", sub_universe,
                f"{symbol}_ratios_ttm.parquet")),
            "metrics_ttm": self._read_first_row(os.path.join(
                self.parquet_root, "metrics_ttm", sub_universe,
                f"{symbol}_metrics_ttm.parquet")),
        }
        for out_col, candidates in cfg.FACTOR_FIELD_SOURCES.items():
            value = None
            for dataset, column in candidates:
                candidate = sources[dataset].get(column)
                if candidate is not None and not pd.isna(candidate):
                    value = candidate
                    break
            row[out_col] = value

        return row

    def build_factor_metrics(self, sub_universes=None, limit=None):
        """One snapshot parquet per index list (overwritten each run):
        stock_data/factor_metrics/{sub}_metrics_returns.parquet. Local only.

        Reads build_price_parquets' daily parquets plus company_profiles/,
        ratios_ttm/ and metrics_ttm/ from build_fundamentals_parquets — run
        those first.

        No blanket dropna: nulls are preserved per field, because the backend's
        rank_returns already drops per-metric at point of use. The legacy
        producer dropped any row with a null in ANY of ~20 columns, ejecting a
        stock from every metric over one non-meaningful ratio.

        Returns a StageResult; detail["lists"][sub] = {"rows", "skipped", "stale"}.
        """
        subs = cfg.FACTOR_SUB_UNIVERSES if sub_universes is None else sub_universes
        os.makedirs(self.factor_metrics_dir, exist_ok=True)
        result = StageResult("build_factor_metrics")
        lists = result.detail.setdefault("lists", {})

        for sub in subs:
            folder = self.price_parquet_dir("daily", sub)
            if not os.path.isdir(folder):
                print(f"{sub}: SKIPPED — no price parquets at {folder}")
                result.record(False, sub)
                continue

            symbols = sorted(f.removesuffix("_prices.parquet")
                             for f in os.listdir(folder)
                             if f.endswith("_prices.parquet"))
            if limit is not None:
                symbols = symbols[:limit]

            rows, skipped = [], {}
            for symbol in symbols:
                try:
                    rows.append(self.build_factor_metrics_row(symbol, sub))
                except (FileNotFoundError, KeyError, ValueError, OSError) as e:
                    skipped[symbol] = str(e)

            if not rows:
                print(f"{sub}: SKIPPED — no rows built ({len(skipped)} skipped); "
                      "existing parquet left untouched")
                result.record(False, sub)
                continue

            # A stale symbol's as_of can sit years behind the universe's newest
            # print (a delisting or a long halt), so its window returns are
            # measured over a different calendar period than everyone else's
            # and land in charts as spurious outliers. Null the return/stdev
            # columns for anything lagging by more than STALE_BDAY_TOLERANCE
            # business days; the row stays for its ratios, sector, and beta.
            newest_as_of = max(row["as_of"] for row in rows)
            stale = 0
            for row in rows:
                gap = np.busday_count(row["as_of"].date(), newest_as_of.date())
                if gap > cfg.STALE_BDAY_TOLERANCE:
                    for col in FACTOR_WINDOW_COLUMNS:
                        row[col] = None
                    stale += 1

            df = pd.DataFrame(rows).reindex(columns=FACTOR_METRICS_COLUMNS)
            for col in FACTOR_NUMERIC_COLS:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            for col in ["symbol", "name", "sector"]:
                df[col] = df[col].astype("string")
            df["as_of"] = pd.to_datetime(df["as_of"])
            df = df.reset_index(drop=True)

            path = os.path.join(self.factor_metrics_dir,
                                f"{sub}_metrics_returns.parquet")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            df.to_parquet(path, engine="pyarrow", index=False)
            lists[sub] = {"rows": len(df), "skipped": len(skipped), "stale": stale}
            result.record(True)

            reasons = {}
            for reason in skipped.values():
                reasons[reason] = reasons.get(reason, 0) + 1
            print(f"{sub}: {len(df)} built, {len(skipped)} skipped, "
                  f"{stale} stale (returns nulled) {reasons if reasons else ''} → {path}")

        return result

    # The two aggregated profile files the Django backend still reads. Both
    # carry the same 27-column schema; they differ only in row scope.
    #   company_profiles.parquet — every sub-universe, ETFs included
    #                              (StockCalculations.py:124)
    #   long_profiles.parquet    — the stock lists only, no etfs/ folder
    #                              (StockCalculations.py:131)
    # Scope was confirmed against the live files: the June company_profiles
    # was 50/50 is_etf True/False, while long_profiles held 3 is_etf=True rows
    # — index constituents that happen to be ETFs. So long_profiles is scoped
    # by FOLDER, not by the is_etf flag, and this reproduces that.
    PROFILE_AGGREGATES = {
        "company_profiles": None,                 # None = every sub-universe
        "long_profiles": "FACTOR_SUB_UNIVERSES",  # the 8 stock lists
    }

    def build_profile_aggregate(self, targets=None):
        """Concatenate the per-symbol company_profiles parquets into the two
        aggregated files the backend reads.

        The rest of the pipeline writes one parquet per symbol, which suits
        per-symbol lookups but not `get_company_profiles()` /
        `get_universe_profiles()`, which need every profile at once — 13k S3
        round-trips is not an option, so the aggregate has to exist.

        Reads: stock_data/company_profiles/{sub}/{SYMBOL}_profile.parquet
               (build_fundamentals_parquets output — run that first)
        Writes: stock_data/company_profiles/company_profiles.parquet
                stock_data/long_profiles/long_profiles.parquet

        Every per-symbol file is read ONCE and both aggregates are sliced from
        that one pass — long_profiles is company_profiles restricted to the
        stock sub-universes, so re-reading 17k parquets for it would double the
        cost for nothing.

        Columns are reindexed to the FIELD_MAPPINGS['long_profiles'] output
        order, so a symbol whose FMP payload was missing a field gets a null
        rather than shifting the schema. Duplicates (a symbol in two index
        lists) are dropped on first occurrence — the profile payload is
        per-symbol, so the copies are identical.

        Returns a StageResult; detail["rows"][name] = row count.
        """
        result = StageResult("build_profile_aggregate")
        columns = list(cfg.FIELD_MAPPINGS["long_profiles"].values())
        names = list(self.PROFILE_AGGREGATES) if targets is None else targets

        # One pass over every per-symbol profile, tagged with its folder so
        # the narrower aggregate can be sliced without re-reading.
        frames, missing, read = [], [], 0
        for sub in cfg.ALL_SUB_UNIVERSES:
            folder = os.path.join(self.parquet_root, "company_profiles", sub)
            if not os.path.isdir(folder):
                missing.append(sub)
                continue
            for fname in sorted(os.listdir(folder)):
                if not fname.endswith("_profile.parquet"):
                    continue
                try:
                    frame = pd.read_parquet(os.path.join(folder, fname))
                    frame["_sub"] = sub
                    frames.append(frame)
                    read += 1
                except Exception as e:
                    print(f"\n{sub}/{fname}: {e}")
            print(f"\r  read {read:,} profiles ({sub})            ",
                  end="", flush=True)
        print()

        if not frames:
            print("SKIPPED — no per-symbol profiles found; "
                  "existing files left untouched")
            result.record(False, "no per-symbol profiles")
            return result

        everything = pd.concat(frames, ignore_index=True)
        rows = result.detail.setdefault("rows", {})

        for name in names:
            scope = self.PROFILE_AGGREGATES[name]
            subs = (cfg.ALL_SUB_UNIVERSES if scope is None
                    else getattr(cfg, scope))
            df = everything[everything["_sub"].isin(subs)]
            before = len(df)
            df = (df.drop_duplicates(subset="symbol", keep="first")
                    .sort_values("symbol", kind="stable")
                    .reset_index(drop=True)
                    .reindex(columns=columns))
            # A column null for every symbol comes back as object; is_etf is
            # the one the backend treats as a boolean.
            if "is_etf" in df.columns:
                df["is_etf"] = df["is_etf"].fillna(False).astype(bool)

            # Datetime columns must NOT survive into the aggregate.
            # build_fundamentals_parquets parses *_date to datetime64 for the
            # per-symbol files, but StockCalculations.file_compressor does
            # `json.dumps(df.to_dict(orient="records"))` with NO default=str,
            # so a Timestamp raises "Object of type Timestamp is not JSON
            # serializable" — taking down get_company_profiles(), which runs
            # both as a view and as a Celery beat task. The June files stored
            # these as strings; match that.
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    df[col] = df[col].dt.strftime("%Y-%m-%d").astype(object)
                    df[col] = df[col].where(df[col].notna(), None)

            # Arrives as strings from the FMP payload; the June aggregate held
            # it as float64 and the frontend treats it as a number.
            if "no_of_employees" in df.columns:
                df["no_of_employees"] = pd.to_numeric(
                    df["no_of_employees"], errors="coerce")

            path = os.path.join(self.parquet_root, name, f"{name}.parquet")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            df.to_parquet(path, engine="pyarrow", index=False)
            rows[name] = len(df)
            result.record(True)
            print(f"{name}: {len(df):,} symbols ({before - len(df)} duplicates "
                  f"dropped{', missing folders: ' + str(missing) if missing else ''}) "
                  f"→ {path}")

        return result

    def upload_profile_aggregates(self):
        """→ stock_data/company_profiles/company_profiles.parquet and
        stock_data/long_profiles/long_profiles.parquet.

        Separate from upload_fundamentals(), which walks the per-sub-universe
        SUB-folders and so never sees a file sitting at the data-type root."""
        keys = []
        for name in self.PROFILE_AGGREGATES:
            path = os.path.join(self.parquet_root, name, f"{name}.parquet")
            if not os.path.isfile(path):
                print(f"{name}: not built yet — run build_profile_aggregate()")
                continue
            keys.append(self.upload_single_file(path))
        return keys

    def constituent_weights(self, const_key):
        """symbol → index weight (decimal) from the local constituent JSON."""
        with open(self.constituents_path(const_key)) as f:
            rows = json.load(f)
        weights = {}
        for row in rows:
            sym, pct = row.get("asset"), row.get("weightPercentage")
            if sym and pct is not None:
                weights[sym] = float(pct) / 100
        return weights

    def _load_adj_close_matrix(self, sub_universe, symbols, lookback=100):
        """date x symbol adjClose frame from the local daily metric parquets
        (adjClose column only — cheap even for r2000). Returns (prices, missing);
        symbols with no local parquet are skipped, never fetched."""
        folder = self.price_parquet_dir("daily", sub_universe)
        series, missing = [], []
        for sym in symbols:
            path = os.path.join(folder, f"{sym}_prices.parquet")
            if not os.path.isfile(path):
                missing.append(sym)
                continue
            s = pd.read_parquet(path, columns=["adjClose"])["adjClose"]
            series.append(s.iloc[-lookback:].rename(sym))
        if not series:
            raise FileNotFoundError(f"no price parquets under {folder} — run "
                                    "build_price_parquets() first")
        return pd.concat(series, axis=1).sort_index(), missing

    @staticmethod
    def compute_contr_to_vol(prices, weights, frequency=90, trading_days=252,
                             min_coverage=0.9, edge_tolerance=5):
        """Per-stock contribution to portfolio volatility over the last
        `frequency` trading days.

        contr_i = w_i·(Σw)_i / σ_p, annualised — the σ-decomposition, so the
        contr_to_vol column sums to the annualised portfolio vol. Weights are the
        published index weights (not renormalised over surviving stocks);
        pct_contr_to_vol sums to 1 regardless.

        Multi-exchange lists (msci_eafe, msci_sm) mix ~15 trading calendars, so
        symbols are judged against a trimmed union grid, not exact endpoints
        (requiring a print on the exact first/last union date dropped ALL of
        msci_eafe): dates where <50% of symbols traded are discarded (ragged
        edges, minor-calendar strays), then a symbol is kept if its first and
        last prints fall within `edge_tolerance` rows of the window edges and it
        covers >= min_coverage of the window. Remaining exchange-holiday gaps are
        ffilled (and edge gaps bfilled) — a flat price, i.e. a zero return, for
        at most `edge_tolerance` rows. Returns (df, dropped_symbols).
        """
        dense = prices[prices.notna().mean(axis=1) >= 0.5]
        window = dense.tail(frequency + 1)
        tol = min(edge_tolerance, len(window))
        first_ok, last_ok = window.index[tol - 1], window.index[-tol]

        keep, dropped = [], []
        for sym in window.columns:
            col = window[sym]
            first, last = col.first_valid_index(), col.last_valid_index()
            if (first is not None and first <= first_ok and last >= last_ok
                    and col.notna().mean() >= min_coverage):
                keep.append(sym)
            else:
                dropped.append(sym)
        if len(keep) < 2:
            return pd.DataFrame(), sorted(dropped)
        window = window[keep].ffill().bfill()

        returns = window.pct_change(fill_method=None).iloc[1:]
        w = pd.Series({sym: weights[sym] for sym in keep})
        cov = returns.cov()
        cov_w = cov @ w
        port_std_daily = float(np.sqrt(w @ cov_w))
        ann = np.sqrt(trading_days)

        contr = w * cov_w / port_std_daily * ann
        period_return = window.iloc[-1] / window.iloc[0] - 1

        df = pd.DataFrame({
            "weight": w,
            "annualized_vol": returns.std() * ann,
            "contr_to_vol": contr,
            "pct_contr_to_vol": contr / contr.sum(),
            "period_return": period_return,
            "contr_to_return": w * period_return,
        }).sort_values("pct_contr_to_vol", ascending=False)
        df.index.name = "symbol"
        df["window_days"] = frequency
        df["as_of"] = window.index[-1]
        return df, dropped

    def build_contr_to_var(self, constituent_keys=None, frequency=90):
        """One risk-decomposition snapshot per index list (overwritten each
        run): index_data/contr_to_var/{sub}_contr_to_var.parquet. Local only —
        needs constituents + build_price_parquets' daily parquets."""
        keys = (list(cfg.CONSTITUENT_PROXY_ETFS) if constituent_keys is None
                else constituent_keys)
        os.makedirs(self.contr_to_var_dir, exist_ok=True)
        result = StageResult("build_contr_to_var")
        for const_key in keys:
            sub = self.sub_universe_for(const_key)
            try:
                weights = self.constituent_weights(const_key)
                prices, missing = self._load_adj_close_matrix(
                    sub, list(weights), lookback=frequency + 10)
                df, dropped = self.compute_contr_to_vol(prices, weights,
                                                        frequency=frequency)
            except (FileNotFoundError, ValueError) as e:
                result.record(False, sub)
                print(f"{sub}: SKIPPED — {e}; existing parquet left untouched")
                continue
            if df.empty:
                result.record(False, sub)
                print(f"{sub}: SKIPPED — no symbols survived alignment "
                      f"({len(missing)} no local prices, {len(dropped)} dropped); "
                      "existing parquet left untouched")
                continue
            out_path = os.path.join(self.contr_to_var_dir,
                                    f"{sub}_contr_to_var.parquet")
            df.reset_index().to_parquet(out_path, index=False)
            result.record(True)
            result.detail[sub] = len(df)
            print(f"{sub}: {len(df)} stocks ({len(missing)} no local prices, "
                  f"{len(dropped)} gappy window) → {out_path}")
        return result

    def _load_fred_series(self, series_id, column=None):
        with open(os.path.join(self.econ_json_dir, f"{series_id}.json")) as f:
            rows = json.load(f)
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df.rename(columns={"value": column}) if column else df

    @staticmethod
    def _monthly_last(df):
        """Last observation of each calendar month, actual dates preserved
        (replaces the original's groupby(year, month) index mangling)."""
        return df[~df.index.to_period("M").duplicated(keep="last")]

    @staticmethod
    def _rolling_compound(returns, window, annualize=False):
        """Compounded return over `window` months; annualize=True for the
        (prod)^(12/window)-1 form used by the 3-year columns."""
        cum = (returns + 1).rolling(window).apply(np.prod, raw=True)
        return cum ** (12 / window) - 1 if annualize else cum - 1

    def build_econ_parquets(self):
        """FRED JSONs → macro parquets in econ_data/ (local only, no API calls).

        yield_spreads: daily curve levels + spreads in bps, on the 10-year's
        dates (the original's 'hihgyieldtenspread' typo is not preserved)."""
        os.makedirs(self.econ_dir, exist_ok=True)

        legs = {"ten": "DGS10", "two": "DGS2", "five": "DGS5",
                "thirty": "DGS30", "mlhy": "BAMLH0A0HYM2EY"}
        yields = pd.concat(
            [self._load_fred_series(sid, col) for col, sid in legs.items()],
            axis=1).sort_index()
        yields = yields[yields["ten"].notna()]
        yields["ten_two_spread"] = (yields["ten"] - yields["two"]) * 100
        yields["ten_thirty_spread"] = (yields["thirty"] - yields["ten"]) * 100
        yields["five_two_spread"] = (yields["five"] - yields["two"]) * 100
        yields["five_ten_spread"] = (yields["ten"] - yields["five"]) * 100
        yields["high_yield_ten_spread"] = (yields["mlhy"] - yields["ten"]) * 100
        yields.reset_index().to_parquet(
            os.path.join(self.econ_dir, "yield_spreads.parquet"), index=False)

        cpi = self._monthly_last(self._load_fred_series("CPIAUCSL")).copy()
        cpi["returns"] = cpi["value"].pct_change()
        cpi["yearly_returns"] = self._rolling_compound(cpi["returns"], 12)
        cpi.reset_index().to_parquet(
            os.path.join(self.econ_dir, "cpi.parquet"), index=False)

        nfp = self._monthly_last(self._load_fred_series("PAYEMS")).copy()
        nfp["returns"] = nfp["value"].pct_change()
        nfp["quarterly_returns"] = self._rolling_compound(nfp["returns"], 3)
        nfp["yearly_returns"] = self._rolling_compound(nfp["returns"], 12)
        nfp.reset_index().to_parquet(
            os.path.join(self.econ_dir, "nonfarm.parquet"), index=False)

        unemp = self._monthly_last(self._load_fred_series("UNRATE"))
        unemp.reset_index().to_parquet(
            os.path.join(self.econ_dir, "unemployment.parquet"), index=False)

        print(f"yield_spreads ({len(yields)}), cpi ({len(cpi)}), "
              f"nonfarm ({len(nfp)}), unemployment ({len(unemp)}) → {self.econ_dir}/")

        result = StageResult("build_econ_parquets", attempted=4, saved=4)
        result.detail = {"yield_spreads": len(yields), "cpi": len(cpi),
                         "nonfarm": len(nfp), "unemployment": len(unemp)}
        return result

    def _load_monthly_metrics(self, kind, key):
        if kind == "etf":
            path = os.path.join(self.price_parquet_dir("monthly", "etfs"),
                                f"{key}_prices.parquet")
        else:
            path = os.path.join(self.index_prices_dir, "monthly",
                                f"{key}_prices.parquet")
        return pd.read_parquet(path, columns=REL_PERF_COLS)

    def build_relative_performance(self, pair_keys=None):
        """Monthly relative-performance spreads per pair (local only):
        econ_data/relative_perf/{pair}.parquet, left-joined on the base leg's
        dates like the original.

        Depends on build_price_parquets' monthly ETF parquets AND
        fetch_index_prices' monthly index parquets — don't run this leg
        standalone on a cold checkout."""
        keys = (list(cfg.RELATIVE_PERF_PAIRS) if pair_keys is None else pair_keys)
        out_dir = os.path.join(self.econ_dir, "relative_perf")
        os.makedirs(out_dir, exist_ok=True)
        result, failed = StageResult("build_relative_performance"), []
        for pair in keys:
            try:
                (base_kind, base_key), (comp_kind, comp_key) = cfg.RELATIVE_PERF_PAIRS[pair]
                base = self._load_monthly_metrics(base_kind, base_key)
                comp = self._load_monthly_metrics(comp_kind, comp_key)
                df = base.join(comp, how="left", lsuffix="_base", rsuffix="_comp")
                df["quarterly_spread"] = df["3_month_returns_comp"] - df["3_month_returns_base"]
                df["yearly_spread"] = df["1_yr_returns_comp"] - df["1_yr_returns_base"]
                df["three_year_spread"] = df["3_yr_returns_comp"] - df["3_yr_returns_base"]
                df["base_symbol"], df["comp_symbol"] = base_key, comp_key
                df.reset_index().to_parquet(
                    os.path.join(out_dir, f"{pair}.parquet"), index=False)
                print(f"\r{pair}: {len(df)} months      ", end="", flush=True)
                result.record(True)
            except Exception as e:
                failed.append(pair)
                result.record(False, pair)
                print(f"\n{pair} failed: {e}")
        print(f"\n{len(keys) - len(failed)} pairs → {out_dir}/")
        if failed:
            print(f"{len(failed)} pairs failed: {failed}")
        return result

    # ═════════════════════════════════════════════════════════════════════
    # STAGE 3 — Upload to s3://{bucket}. Local path == S3 key: a file at
    # {root}/stock_data/x.parquet lands at s3://{bucket}/stock_data/x.parquet.
    #
    # Uploads are UNCONDITIONAL — there is no mtime or ETag comparison, so
    # every call re-pushes every file in the folder. upload_fundamentals() is
    # ~88,000 objects; skip it when only prices changed.
    # ═════════════════════════════════════════════════════════════════════
    @property
    def s3(self):
        """Lazily-built S3 client, reused across uploads."""
        if self._s3 is None:
            if self.aws_key and self.aws_secret:
                self._s3 = boto3.client(
                    "s3",
                    aws_access_key_id=self.aws_key,
                    aws_secret_access_key=self.aws_secret,
                    region_name="us-east-1",
                )
            else:
                # No keys in the environment: boto3's default chain — the ECS
                # task role on AWS, an SSO profile (AWS_PROFILE) locally.
                self._s3 = boto3.client("s3", region_name="us-east-1")
        return self._s3

    def _s3_prefix_for(self, folder_path):
        """Default S3 prefix for a local folder: its path relative to root.
        Reproduces the notebook's `folder_path.removeprefix('./')` exactly,
        now that paths are absolute."""
        return os.path.relpath(folder_path, self.root).replace(os.sep, "/")

    @staticmethod
    def _files_in(folder_path):
        """File names (non-recursive, sorted) in a local folder; [] if the
        folder doesn't exist. The original printed a warning and then crashed
        with a NameError on the unset return variable."""
        if not os.path.isdir(folder_path):
            print(f"The folder '{folder_path}' does not exist.")
            return []
        return sorted(
            f for f in os.listdir(folder_path)
            if os.path.isfile(os.path.join(folder_path, f))
        )

    def upload_folder(self, folder_path, file_names=None, s3_prefix=None):
        """Upload local files to s3://{bucket}/{s3_prefix}/{file}.

        file_names: defaults to every file in folder_path
        s3_prefix:  defaults to folder_path relative to root
        Returns (uploaded_keys, failed_names).
        """
        if file_names is None:
            file_names = self._files_in(folder_path)
        if s3_prefix is None:
            s3_prefix = self._s3_prefix_for(folder_path)

        uploaded, failed = [], []
        for name in file_names:
            s3_key = f"{s3_prefix}/{name}"
            try:
                self.s3.upload_file(
                    Filename=os.path.join(folder_path, name),
                    Bucket=self.bucket,
                    Key=s3_key,
                )
                uploaded.append(s3_key)
                print(f"\rUploaded [{len(uploaded)}/{len(file_names)}] {s3_key}",
                      end="", flush=True)
            except Exception as e:
                failed.append(name)
                print(f"\nUpload failed for {name}: {e}")

        print(f"\n{len(uploaded)} uploaded, {len(failed)} failed "
              f"→ s3://{self.bucket}/{s3_prefix}/")
        return uploaded, failed

    def upload_index_prices(self, frequencies=("daily", "monthly")):
        """→ index_data/index_prices_v2/{daily,monthly}/. NOTE: the backend
        still reads index_prices_v1 until it is cut over to this prefix
        (backend/utils/StockCalculations.py:70)."""
        return {freq: self.upload_folder(
                    os.path.join(self.index_prices_dir, freq))
                for freq in frequencies}

    def upload_stock_prices(self, frequencies=("daily", "monthly"),
                            sub_universes=None):
        """→ stock_data/stock_prices/{frequency}/{SYMBOL}_prices.parquet.

        The local {sub_universe} folder level is deliberately dropped from the
        key — the frontend asks by symbol, not by list; a symbol present in two
        lists just re-uploads identical content. ~34,000 objects."""
        subs = cfg.ALL_SUB_UNIVERSES if sub_universes is None else sub_universes
        for freq in frequencies:
            for sub in subs:
                folder = self.price_parquet_dir(freq, sub)
                if not os.path.isdir(folder):
                    continue
                self.upload_folder(
                    folder, s3_prefix=f"stock_data/stock_prices/{freq}")

    def upload_fundamentals(self, data_types=None, sub_universes=None):
        """→ stock_data/{data_type}/{SYMBOL}{suffix}.parquet — one object per
        stock per data type, fetchable by symbol alone. Raw JSONs stay local as
        the fetch/merge source of truth. ~88,000 objects, the long one."""
        types = (list(cfg.FUNDAMENTALS_DATASETS) if data_types is None
                 else data_types)
        subs = cfg.ALL_SUB_UNIVERSES if sub_universes is None else sub_universes
        for data_type in types:
            for sub in subs:
                folder = os.path.join(self.parquet_root, data_type, sub)
                if not os.path.isdir(folder):
                    continue
                self.upload_folder(folder, s3_prefix=f"stock_data/{data_type}")

    def upload_constituents(self):
        """→ index_data/constituents/{key}_constituents.json, the exact keys
        the backend reads (StockCalculations.py:174).

        QUARTERLY ONLY, right after refresh_constituents() — otherwise it
        re-pushes byte-identical JSONs."""
        return self.upload_folder(os.path.join(self.index_root, "constituents"))

    def upload_factor_metrics(self):
        """→ stock_data/factor_metrics/… — LIVE, feeds /factor-performance."""
        return self.upload_folder(self.factor_metrics_dir)

    def upload_contr_to_var(self):
        """→ index_data/contr_to_var/… — no backend reader yet; forward-looking."""
        return self.upload_folder(self.contr_to_var_dir)

    def upload_revenue_segments(self):
        """→ stock_data/revenue_segments/{SYMBOL}_segments.json, symbol-
        addressable like the price and fundamentals objects.

        No prefix override and no sub-universe level to drop: fetch_revenue_
        segments dedupes and writes one flat folder whose path is already the
        S3 key. Object count is the number of companies that actually disclose
        segments, not the universe size.

        NO BACKEND READER YET — same forward-looking status as contr_to_var.
        The backend's JSON-from-S3 path (fs.open(...).read() + json.loads, see
        StockCalculations.get_index_constituents) reads these as-is when a
        consumer lands; a 404 means the company discloses no segmentation."""
        return self.upload_folder(self.revenue_segments_dir)

    def upload_econ(self):
        """→ econ_data/… — 4 macro parquets at the root, 20 pair parquets under
        relative_perf/. LIVE: feeds /api/economic-data/ and /capital-markets."""
        results = {"macro": self.upload_folder(self.econ_dir)}
        rel_dir = os.path.join(self.econ_dir, "relative_perf")
        if os.path.isdir(rel_dir):
            results["relative_perf"] = self.upload_folder(rel_dir)
        return results

    def upload_single_file(self, local_path, s3_key=None):
        """Upload one file; the key defaults to its path relative to root."""
        if s3_key is None:
            s3_key = self._s3_prefix_for(local_path)
        self.s3.upload_file(Filename=local_path, Bucket=self.bucket, Key=s3_key)
        print(f"Uploaded s3://{self.bucket}/{s3_key}")
        return s3_key

    # ═════════════════════════════════════════════════════════════════════
    # Inspection — local, read-only, no API calls. Run this BEFORE a fetch to
    # pick from_date, and after Stage 1 to confirm the new data landed.
    # ═════════════════════════════════════════════════════════════════════
    def modal_last_dates(self, sample=60, seed=7):
        """Per sub-universe: price-file count and the MODAL last price date over
        a random sample of `sample` files (see status() for why modal). Reads
        only the first 4 KB of each file and prints nothing — the runner's
        freshness check uses it.

        Returns {sub: {"files", "modal_last_date", "newest", "sampled"}}."""
        import collections
        import random
        import re

        pattern = re.compile(rb'"date"\s*:\s*"(\d{4}-\d{2}-\d{2})"')
        out = {}
        for sub in cfg.ALL_SUB_UNIVERSES:
            folder = self.json_dir("stock_prices", sub)
            if not os.path.isdir(folder):
                out[sub] = {"files": 0, "modal_last_date": None,
                            "newest": None, "sampled": 0}
                continue
            files = [f for f in os.listdir(folder) if f.endswith("_prices.json")]
            picks = random.Random(seed).sample(files, min(sample, len(files)))
            dates = []
            for name in picks:
                with open(os.path.join(folder, name), "rb") as fh:
                    match = pattern.search(fh.read(4096))
                if match:
                    dates.append(match.group(1).decode())
            modal = collections.Counter(dates).most_common(1)
            out[sub] = {
                "files": len(files),
                "modal_last_date": modal[0][0] if modal else None,
                "newest": max(dates) if dates else None,
                "sampled": len(dates),
            }
        return out

    def status(self, sample=60, seed=7):
        """What's on disk and how stale it is, as a DataFrame.

        Per sub-universe: file count, and the MODAL last price date across a
        random sample of `sample` symbols. Modal, not max: delisted names keep
        their own last print (a symbol stuck in 2022 is a delisting, not a
        pipeline failure), so the mode is what the live universe looks like.

        Only the first 4 KB of each JSON is read — 'historical' is newest-first,
        so the first date in the file is the last date of data.
        """
        rows = [{"sub_universe": sub, **info}
                for sub, info in self.modal_last_dates(sample, seed).items()]

        prices = pd.DataFrame(rows)

        outputs = []
        for label, folder in [
            ("price JSON", os.path.join(self.json_root, "stock_prices")),
            ("statements JSON", os.path.join(self.json_root, "income_statements")),
            ("ratios_ttm JSON", os.path.join(self.json_root, "ratios_ttm")),
            ("price parquet", os.path.join(self.parquet_root, "stock_prices")),
            ("index parquet", self.index_prices_dir),
            ("factor_metrics", self.factor_metrics_dir),
            ("revenue_segments", self.revenue_segments_dir),
            ("contr_to_var", self.contr_to_var_dir),
            ("econ parquet", self.econ_dir),
            ("constituents", os.path.join(self.index_root, "constituents")),
        ]:
            count, newest = 0, None
            for dirpath, _, names in os.walk(folder):
                for name in names:
                    count += 1
                    mtime = os.path.getmtime(os.path.join(dirpath, name))
                    newest = mtime if newest is None else max(newest, mtime)
            outputs.append({
                "dataset": label,
                "files": count,
                "last_written": (datetime.datetime.fromtimestamp(newest)
                                 .strftime("%Y-%m-%d %H:%M") if newest else None),
            })

        print(f"root: {self.root}\n")
        print("Price data on disk (modal last date across a random sample):")
        print(prices.to_string(index=False))
        print("\nOutput freshness (file mtimes, not data dates):")
        print(pd.DataFrame(outputs).to_string(index=False))

        live = prices[prices["modal_last_date"].notna()]["modal_last_date"]
        if len(live):
            print(f"\nModal last price date across all lists: {live.mode().iloc[0]}")
            print("Pass a from_date at or BEFORE that date — a later one leaves "
                  "a silent gap.\nfrom_date='1999-01-01' costs the same number "
                  "of API calls and avoids\nboth the gap and the split-adjustment "
                  "seam. See fetch_stock_prices.__doc__.")
        return prices
