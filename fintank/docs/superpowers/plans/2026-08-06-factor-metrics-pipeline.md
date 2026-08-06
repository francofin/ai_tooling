# Factor Metrics Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the dead factor-performance chain end to end — a local-only producer in `stock_data_getter_v2.ipynb` writing per-index factor-metric parquets to S3, a new backend module that ranks them into deciles, and the endpoint `/factor-performance` already calls.

**Architecture:** Three layers, landing together. (1) The notebook gains a *Factor Metrics* section that joins four already-staged local datasets into one row per symbol per index list — no API calls, following the `create_index_contr_to_var` precedent. (2) `analyzer/analyzer_utils/factor_tools.py` reads those parquets from S3 and does decile bucketing at request time, replacing `backend/utils/Rankings.py` (deleted). (3) The frontend dropdown moves to v2 universe slugs.

**Tech Stack:** pandas/pyarrow in a Jupyter notebook; Django REST + `s3fs`/`pyarrow` + Django cache on the backend; Next.js Pages Router + ApexCharts on the frontend.

**Spec:** `docs/superpowers/specs/2026-08-05-factor-metrics-pipeline-design.md`

## Global Constraints

- **Column contract.** The parquet's column names are consumed by name in `factor_tools.py`. They are exactly: `symbol, name, sector, as_of, 1M, 3M, 6M, ytd, 1MSTD, 3MSTD, 6MSTD, YTDSTD, beta, div_yield, pe, pb, psales, pcf, roe, cfd, debt_equity, fcf`. No `int_cov` in any layer.
- **Units.** `1M/3M/6M/ytd` are **percent** (5.42 means 5.42%). The four `*STD` columns are **daily decimal** stdev (0.012). `roe` and `debt_equity` are decimals as FMP reports them; `div_yield` is a percent. Never rescale on read.
- **No API calls** anywhere in Layer 1. Every input is already on disk under `backend/class_files/`.
- **Universe slugs** (8, no Dow): `sp500, nas, tsx, tsx_small_cap, r2000, rmicro, msci_eafe, msci_sm`.
- **Bucket count**: 5 when the ranked column has ≤100 non-null rows, 10 otherwise. Labels `Q1…Qn`.
- **Credentials** load from `backend/.env` only. Never hardcode a key.
- Working directory for notebook code is `backend/class_files/`; for Django commands, `backend/`.
- Python interpreter for all backend commands: `/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python`.

---

### Task 1: Refresh the stale TTM parquets

The staged `ratios_ttm` parquets were written 2026-08-02, before `field_mappings` gained `ps_ratio` and `pcf_ratio`. They are missing those columns today. This is a local transform — no API calls — and it must run before anything reads those files.

**Files:**
- Modify: none (runs an existing notebook function)
- Verify: `backend/class_files/stock_data/ratios_ttm/sp500/AAPL_ratios_ttm.parquet`

**Interfaces:**
- Consumes: `create_fundamentals_dataframes(data_types=None, sub_universes=None, limit=None)` — already defined in the notebook's *Aggregate & Export to Parquet* cell.
- Produces: `ratios_ttm` parquets containing `ps_ratio` and `pcf_ratio`, which Task 3's field precedence prefers.

- [ ] **Step 1: Confirm the columns are missing today**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank/backend/class_files
/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python -c "
import pandas as pd
df = pd.read_parquet('stock_data/ratios_ttm/sp500/AAPL_ratios_ttm.parquet')
print('ps_ratio' in df.columns, 'pcf_ratio' in df.columns)
"
```

Expected: `False False`

- [ ] **Step 2: Re-run the transform**

In the notebook, run the definition cells (everything above *Homepage Aggregations*), then run this in a fresh cell in the *Full Runs* section:

```python
create_fundamentals_dataframes(data_types=["ratios_ttm", "metrics_ttm"])
```

This is local-only and takes a few minutes for ~10,100 symbols × 2 types. Do **not** "Run All" — the bottom cells are live run cells that trigger real fetches.

- [ ] **Step 3: Confirm the columns are present**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank/backend/class_files
/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python -c "
import pandas as pd
df = pd.read_parquet('stock_data/ratios_ttm/sp500/AAPL_ratios_ttm.parquet')
print('ps_ratio' in df.columns, 'pcf_ratio' in df.columns)
print(df[['pe_ratio','ps_ratio','pcf_ratio','pb_ratio','roe']].to_dict('records'))
"
```

Expected: `True True`, then a row of floats.

- [ ] **Step 4: Commit**

Parquets are local staging and are not in git — there is nothing to commit for this task. Confirm with `git status --short backend/class_files` that nothing is staged, and move on.

---

### Task 2: Window-return helper (pure function, test-first)

The heart of the producer: given a symbol's `adjClose` series, compute the 1M/3M/6M/YTD return and stdev. Built and tested as a standalone function first, because it is where every legacy bug lived.

**Files:**
- Create: `backend/utils/factor_windows.py`
- Create: `backend/utils/test_factor_windows.py`

`/backend/class_files` is gitignored wholesale, so tracked source cannot live
there. `backend/utils/` already holds four standalone scripts no Django code
imports (`RunCovar`, `GetPrices`, `SP500PeerList`, `PeerCalculations`), so a
producer-only module fits its existing use.

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `WINDOWS = {"1M": 1, "3M": 3, "6M": 6}` — label → months. `"ytd"` is handled separately.
  - `window_return_and_std(adj_close: pd.Series, label: str) -> tuple[float | None, float | None]` — returns `(percent_return, daily_decimal_std)`, `(None, None)` when the window's anchor predates the series. `adj_close` must have a `DatetimeIndex` sorted ascending. `label` is one of `1M`, `3M`, `6M`, `ytd`.

Task 3 imports both from this module into the notebook.

- [ ] **Step 1: Write the failing tests**

Create `backend/utils/test_factor_windows.py`. It sits next to the module
rather than in a `tests/` package: `manage.py test` discovers `test*.py` from
`backend/`, so it gets imported during Django test discovery — the import must
be package-qualified or discovery raises. Django collects zero tests from it
(these are plain pytest functions, not `TestCase` subclasses), which is
expected.

```python
import numpy as np
import pandas as pd
import pytest

from utils.factor_windows import WINDOWS, window_return_and_std


def _series(dates, values):
    return pd.Series(values, index=pd.to_datetime(dates))


def test_one_month_return_is_a_percent():
    dates = pd.bdate_range("2026-06-01", "2026-08-05")
    prices = _series(dates, np.linspace(100.0, 110.0, len(dates)))
    ret, _ = window_return_and_std(prices, "1M")
    # anchor is the last trading day on or before 2026-07-05
    anchor = prices.asof(pd.Timestamp("2026-07-05"))
    assert ret == pytest.approx((prices.iloc[-1] / anchor - 1) * 100)
    assert ret > 1.0  # a percent, not a decimal fraction


def test_ytd_anchors_on_the_last_close_of_the_prior_year():
    dates = ["2025-12-30", "2025-12-31", "2026-01-02", "2026-01-05"]
    prices = _series(dates, [50.0, 100.0, 105.0, 120.0])
    ret, _ = window_return_and_std(prices, "ytd")
    assert ret == pytest.approx(20.0)  # 120 / 100 - 1


def test_std_is_daily_decimal_not_annualised():
    dates = pd.bdate_range("2026-01-02", "2026-08-05")
    rng = np.random.default_rng(0)
    prices = _series(dates, 100 * np.cumprod(1 + rng.normal(0, 0.01, len(dates))))
    _, std = window_return_and_std(prices, "6M")
    assert 0.001 < std < 0.05  # daily scale; annualised would be ~0.16


def test_january_does_not_crash_on_month_underflow():
    """date(year, month - 3, day) raised ValueError here in the legacy code."""
    dates = pd.bdate_range("2025-06-02", "2026-01-15")
    prices = _series(dates, np.linspace(100.0, 120.0, len(dates)))
    ret, std = window_return_and_std(prices, "3M")
    assert ret is not None and std is not None


def test_day_31_does_not_crash_on_short_target_month():
    """date(2026, 2, 31) raised ValueError in the legacy code."""
    dates = pd.bdate_range("2025-06-02", "2026-08-31")
    prices = _series(dates, np.linspace(100.0, 120.0, len(dates)))
    ret, _ = window_return_and_std(prices, "6M")
    assert ret is not None


def test_window_longer_than_history_returns_none_not_a_partial_number():
    dates = pd.bdate_range("2026-07-20", "2026-08-05")
    prices = _series(dates, np.linspace(100.0, 105.0, len(dates)))
    assert window_return_and_std(prices, "6M") == (None, None)


def test_empty_series_returns_none():
    assert window_return_and_std(pd.Series(dtype=float), "1M") == (None, None)


def test_window_labels_cover_the_frontend_periods():
    assert set(WINDOWS) == {"1M", "3M", "6M"}
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank/backend
/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python -m pytest utils/test_factor_windows.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'factor_windows'`.

- [ ] **Step 3: Write the implementation**

Create `backend/utils/factor_windows.py`:

```python
"""Trading-day window returns for the factor metrics producer.

Kept as a module rather than a notebook cell so it can be unit-tested: this
is where all three legacy window bugs lived --

  1. date(year, month - 3, day) raised ValueError in Jan-Jun and on days
     29-31, swallowed by a bare except, so symbols silently vanished.
  2. A 240-calendar-day fetch window truncated YTD after ~Aug 28 with no
     error, understating both the return and the stdev.
  3. Prices came from historical-chart/1day, which carries no adjClose, so
     returns were dividend-blind. Callers here pass adjClose.

Returns are PERCENT (5.42 == 5.42%), matching what the backend divides by
100. Stdev is DAILY DECIMAL, matching the legacy frame the factor page
renders in its bucket-holdings tables.
"""
import pandas as pd

WINDOWS = {"1M": 1, "3M": 3, "6M": 6}


def _anchor_date(as_of, label):
    """Calendar start of the window; the caller resolves it to a trading day."""
    if label == "ytd":
        return pd.Timestamp(year=as_of.year - 1, month=12, day=31)
    return as_of - pd.DateOffset(months=WINDOWS[label])


def window_return_and_std(adj_close, label):
    """(percent return, daily decimal stdev) over `label`, or (None, None).

    The anchor is the last trading day at or before the calendar start --
    Series.asof, so a weekend or holiday start resolves backwards instead of
    raising. A window whose anchor predates the first print yields (None,
    None) rather than a partial-window number.
    """
    if adj_close is None or len(adj_close) < 2:
        return None, None

    prices = adj_close.dropna().sort_index()
    if len(prices) < 2:
        return None, None

    as_of = prices.index[-1]
    anchor = _anchor_date(as_of, label)
    if anchor < prices.index[0]:
        return None, None

    anchor_price = prices.asof(anchor)
    if pd.isna(anchor_price) or anchor_price == 0:
        return None, None

    window = prices.loc[anchor:]
    if len(window) < 2:
        return None, None

    period_return = (prices.iloc[-1] / anchor_price - 1) * 100
    daily_std = window.pct_change().std()

    if pd.isna(period_return):
        return None, None
    return float(period_return), (None if pd.isna(daily_std) else float(daily_std))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank/backend
/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python -m pytest utils/test_factor_windows.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank
git add backend/utils/factor_windows.py backend/utils/test_factor_windows.py
git commit -m "feat: add trading-day window returns for factor metrics

Replaces the legacy calendar-date arithmetic that crashed in Jan-Jun and on
days 29-31, and the 240-day lookback that silently truncated YTD.

Lives in backend/utils rather than class_files, which is gitignored."
```

---

### Task 3: Producer section in the notebook

**Files:**
- Modify: `backend/class_files/stock_data_getter_v2.ipynb` — insert two new cells (one markdown, one code) after the *Index Contribution to Volatility* code cell (index 28) and before the *Capital Markets / Economic Data* markdown cell (index 29).

**Interfaces:**
- Consumes: `factor_windows.WINDOWS`, `factor_windows.window_return_and_std` (Task 2); notebook globals `PARQUET_ROOT`, `stock_prices_parquet_dir`, `save_and_export_raw_df_to_parquet`, `upload_files_to_s3`.
- Produces:
  - `FACTOR_METRICS_DIR = "./stock_data/factor_metrics"`
  - `FACTOR_SUB_UNIVERSES` — the 8 slugs
  - `create_factor_metrics_dataframes(sub_universes=None, limit=None) -> dict[str, pd.DataFrame]`
  - `upload_factor_metrics_files()` → S3 keys `stock_data/factor_metrics/{sub}_metrics_returns.parquet`

- [ ] **Step 1: Insert the markdown cell**

Use `NotebookEdit` to insert a markdown cell at index 29 with this source:

```markdown
## Factor Metrics

Cross-sectional ranking inputs for `/factor-performance`: one row per symbol per
index list, joining four datasets already staged locally — **no API calls**,
same shape as the contribution-to-volatility section above.

Replaces the legacy `StockResearcher` class, which made three FMP calls per
stock (~30,000 for the full universe) and pickled the result. Bugs not carried
over: calendar-date window arithmetic that raised `ValueError` in Jan–Jun and on
days 29–31 (swallowed by a bare `except`, so symbols silently vanished); a
240-day price window that truncated YTD after ~Aug 28; prices read from
`historical-chart/1day`, which carries no `adjClose` and so measured
dividend-blind returns; and a blanket `dropna()` that ejected a stock from every
metric because one ratio was non-meaningful.

Interest coverage is deliberately absent — FMP reports it as `0` for a large
share of the universe including AAPL, which buries megacaps in the worst decile.

Returns are **percent**; the four `*STD` columns are **daily decimal** stdev.
Column names are a contract with `analyzer/analyzer_utils/factor_tools.py`.
```

- [ ] **Step 2: Insert the code cell**

Use `NotebookEdit` to insert a code cell at index 30 with this source:

```python
# ── Factor metrics ───────────────────────────────────────────────────────────
# Local data only. Run create_stock_price_dataframe() and
# create_fundamentals_dataframes() first — this reads their output.

import sys
if ".." not in sys.path:
    sys.path.insert(0, "..")   # backend/ — the notebook's cwd is class_files/
from utils.factor_windows import WINDOWS, window_return_and_std

FACTOR_METRICS_DIR = f"{PARQUET_ROOT}/factor_metrics"

# The 8 constituent lists; ETFs have no fundamentals to rank on.
FACTOR_SUB_UNIVERSES = [s for s in ALL_SUB_UNIVERSES if s != "etfs"]

# Output column → (dataset, column) candidates, tried in order, first non-null
# wins. Left-hand names are the legacy contract; do not rename.
#
# UNIT TRAPS (probed live 2026-08-05):
#   dividend_yield_percent is a PERCENT (AAPL 0.34); its sibling
#   dividend_yield is the DECIMAL (0.0034) — 100x apart, same payload.
#   roe is a DECIMAL (AAPL 1.372 = 137%), not a percent.
#   FMP misspells the source field as dividendYielPercentageTTM in ratios-ttm
#   and spells it correctly in key-metrics-ttm; field_mappings handles both.
#   Do NOT "normalise" the spelling.
FACTOR_FIELD_SOURCES = {
    "div_yield":   [("ratios_ttm", "dividend_yield_percent"),
                    ("metrics_ttm", "dividend_yield_percent")],
    "pe":          [("ratios_ttm", "pe_ratio"), ("metrics_ttm", "pe_ratio")],
    "pb":          [("ratios_ttm", "pb_ratio"), ("metrics_ttm", "pb_ratio")],
    "psales":      [("ratios_ttm", "ps_ratio"), ("metrics_ttm", "psales_ratio")],
    "pcf":         [("ratios_ttm", "pcf_ratio"),
                    ("metrics_ttm", "price_to_cashflow")],
    "roe":         [("ratios_ttm", "roe")],
    "cfd":         [("ratios_ttm", "cash_flow_to_debt")],
    "debt_equity": [("ratios_ttm", "debt_to_equity_ratio"),
                    ("metrics_ttm", "debt_to_equity")],
    "fcf":         [("ratios_ttm", "free_cash_flow_per_share")],
}

FACTOR_NUMERIC_COLS = (
    list(WINDOWS) + ["ytd"]
    + [f"{label}STD" for label in list(WINDOWS) + ["YTD"]]
    + ["beta"] + list(FACTOR_FIELD_SOURCES)
)

# Named FACTOR_METRICS_COLUMNS, not FACTOR_COLUMNS: factor_tools.py on the
# backend uses that name for a different thing (response key → column).
FACTOR_METRICS_COLUMNS = (["symbol", "name", "sector", "as_of"]
                          + list(WINDOWS) + ["ytd"]
                          + ["1MSTD", "3MSTD", "6MSTD", "YTDSTD"]
                          + ["beta"] + list(FACTOR_FIELD_SOURCES))


def _read_first_row(path):
    """Single-row fundamentals parquet → dict, or {} if absent/empty."""
    if not os.path.isfile(path):
        return {}
    df = pd.read_parquet(path)
    if df.empty:
        return {}
    return df.iloc[0].to_dict()


def build_factor_metrics_row(symbol, sub_universe):
    """One symbol's factor row. Raises FileNotFoundError when the required
    price parquet is missing; optional fields become None and keep the row."""
    price_path = f"{stock_prices_parquet_dir('daily', sub_universe)}/{symbol}_prices.parquet"
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

    profile = _read_first_row(
        f"{PARQUET_ROOT}/company_profiles/{sub_universe}/{symbol}_profile.parquet")
    row["name"] = profile.get("name")
    row["sector"] = profile.get("sector")
    row["beta"] = profile.get("beta")

    sources = {
        "ratios_ttm": _read_first_row(
            f"{PARQUET_ROOT}/ratios_ttm/{sub_universe}/{symbol}_ratios_ttm.parquet"),
        "metrics_ttm": _read_first_row(
            f"{PARQUET_ROOT}/metrics_ttm/{sub_universe}/{symbol}_metrics_ttm.parquet"),
    }
    for out_col, candidates in FACTOR_FIELD_SOURCES.items():
        value = None
        for dataset, column in candidates:
            candidate = sources[dataset].get(column)
            if candidate is not None and not pd.isna(candidate):
                value = candidate
                break
        row[out_col] = value

    return row


def create_factor_metrics_dataframes(sub_universes=None, limit=None):
    """One snapshot parquet per index list (overwritten each run):
    {FACTOR_METRICS_DIR}/{sub}_metrics_returns.parquet. Local data only.

    No blanket dropna: nulls are preserved per field, because the backend's
    rank_returns already drops per-metric at point of use. The legacy
    producer dropped any row with a null in ANY of ~20 columns, ejecting a
    stock from every metric over one non-meaningful ratio.
    """
    subs = FACTOR_SUB_UNIVERSES if sub_universes is None else sub_universes
    os.makedirs(FACTOR_METRICS_DIR, exist_ok=True)
    results = {}

    for sub in subs:
        folder = stock_prices_parquet_dir("daily", sub)
        if not os.path.isdir(folder):
            print(f"{sub}: SKIPPED — no price parquets at {folder}")
            continue

        symbols = sorted(f.removesuffix("_prices.parquet")
                         for f in os.listdir(folder)
                         if f.endswith("_prices.parquet"))
        if limit is not None:
            symbols = symbols[:limit]

        rows, skipped = [], {}
        for symbol in symbols:
            try:
                rows.append(build_factor_metrics_row(symbol, sub))
            except (FileNotFoundError, KeyError, ValueError) as e:
                skipped[symbol] = str(e)

        if not rows:
            print(f"{sub}: SKIPPED — no rows built ({len(skipped)} skipped); "
                  "existing parquet left untouched")
            continue

        df = pd.DataFrame(rows).reindex(columns=FACTOR_METRICS_COLUMNS)
        for col in FACTOR_NUMERIC_COLS:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        for col in ["symbol", "name", "sector"]:
            df[col] = df[col].astype("string")
        df["as_of"] = pd.to_datetime(df["as_of"])
        df = df.reset_index(drop=True)

        path = f"{FACTOR_METRICS_DIR}/{sub}_metrics_returns.parquet"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        df.to_parquet(path, engine="pyarrow", index=False)
        results[sub] = df

        reasons = {}
        for reason in skipped.values():
            reasons[reason] = reasons.get(reason, 0) + 1
        print(f"{sub}: {len(df)} built, {len(skipped)} skipped "
              f"{reasons if reasons else ''} → {path}")

    return results


def upload_factor_metrics_files():
    """→ s3://{AWS_BUCKET_NAME}/stock_data/factor_metrics/… (local path == key)."""
    return upload_files_to_s3(FACTOR_METRICS_DIR)


# create_factor_metrics_dataframes(sub_universes=["sp500"], limit=25)  # smoke test
# create_factor_metrics_dataframes()                                   # local, no API
# upload_factor_metrics_files()
```

- [ ] **Step 3: Smoke-test the producer**

Run the notebook's definition cells (everything above *Homepage Aggregations*), then in a scratch cell:

```python
out = create_factor_metrics_dataframes(sub_universes=["sp500"], limit=25)
df = out["sp500"]
print(len(df), list(df.columns))
print(df.dtypes)
df.head(3)
```

Expected: 25 rows; columns exactly `FACTOR_METRICS_COLUMNS` with no `int_cov`; `symbol`/`name`/`sector` are `string`, `as_of` is `datetime64[ns]`, everything else `float64`; no column entirely null.

- [ ] **Step 4: Cross-check one symbol against FMP**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank/backend
/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python -c "
import os, requests
from dotenv import load_dotenv
load_dotenv('.env')
r = requests.get(f\"https://financialmodelingprep.com/api/v3/stock-price-change/AAPL?apikey={os.getenv('FMP_API')}\", timeout=30)
print({k: v for k, v in r.json()[0].items() if k in ('1M','3M','6M','ytd')})
"
```

Compare against the AAPL row. Expect **close but not identical** agreement: ours is `adjClose`-based (total return) and FMP's is not. A sign flip or a 100× gap is a bug; a few tenths of a percent is expected.

- [ ] **Step 5: Full run and upload**

```python
create_factor_metrics_dataframes()   # local, no API calls
upload_factor_metrics_files()        # 8 parquets → S3
```

Expected row counts track the constituent lists: `sp500` ≈ 503, `nas` ≈ 102, `tsx` ≈ 217, `tsx_small_cap` ≈ 222, `r2000` ≈ 1955, `rmicro` ≈ 988, `msci_eafe` ≈ 2606, `msci_sm` ≈ 3522. Read the skip tallies — a large `no daily price parquet` count means `create_stock_price_dataframe()` has not been run for that list.

- [ ] **Step 6: Nothing to commit**

`/backend/class_files` is gitignored wholesale (`.gitignore:57`) — the notebook
has never been tracked, and must not become tracked, because the directory also
holds the staged data trees and has historically held credentials. Confirm with
`git ls-files backend/class_files` that it prints nothing, and move on. The
tested part of this task's logic lives in `backend/utils/factor_windows.py`,
which *is* tracked (Task 2).

---

### Task 4: Backend S3 reader

**Files:**
- Modify: `backend/utils/StockCalculations.py` — add a method to `GetData` immediately after `load_contr_to_var` (around line 105).

**Interfaces:**
- Consumes: `GetData.fs` (the per-PID `s3fs` filesystem property).
- Produces: `GetData.load_factor_metrics(universe: str) -> pd.DataFrame` — the parquet as written by Task 3, with `as_of` cast to `str` for JSON serialisation. Task 5 calls this.

- [ ] **Step 1: Add the method**

Insert after `load_contr_to_var`:

```python
    def load_factor_metrics(self, universe: str) -> pd.DataFrame:
        """stock_data/factor_metrics/{universe}_metrics_returns.parquet -- the
        cross-sectional factor snapshot written by
        create_factor_metrics_dataframes(). One row per constituent,
        overwritten each pipeline run. Returns are percent; the *STD columns
        are daily decimal."""
        bucket = 'thetradingfloor'
        key = f"stock_data/factor_metrics/{universe}_metrics_returns.parquet"
        path = f"s3://{bucket}/{key}"
        table = pq.read_table(path, filesystem=self.fs)
        df = table.to_pandas()
        if 'as_of' in df.columns:
            df['as_of'] = df['as_of'].astype(str)
        return df
```

- [ ] **Step 2: Verify it round-trips against the uploaded file**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank/backend
/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fintank_backend.settings')
django.setup()
from utils.StockCalculations import GetData
df = GetData().load_factor_metrics('sp500')
print(len(df), list(df.columns))
assert 'int_cov' not in df.columns
print(df.head(2).to_dict('records'))
"
```

Expected: ~503 rows, the contract columns, no `int_cov`.

- [ ] **Step 3: Commit**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank
git add backend/utils/StockCalculations.py
git commit -m "feat: add load_factor_metrics S3 reader"
```

---

### Task 5: factor_tools module (test-first)

The ranking half. Replaces `GetStockRanks`'s ~940 lines — of which ~700 were four near-identical frequency methods — with one parameterised path, fixing three bugs on the way.

**Files:**
- Create: `backend/analyzer/analyzer_utils/factor_tools.py`
- Modify: `backend/analyzer/tests.py` — append a new test class at the end.

**Interfaces:**
- Consumes: `GetData.load_factor_metrics(universe)` (Task 4).
- Produces:
  - `FACTOR_UNIVERSES` — tuple of the 8 slugs
  - `FACTOR_FREQUENCIES = ("1M", "3M", "6M", "ytd")`
  - `FACTOR_COLUMNS` — `{response_key: frame_column}`, 15 keys including `sectors`
  - `get_factor_ranks(frequency: str, universe: str) -> dict` — the response pack. Task 6's view calls this.

- [ ] **Step 1: Write the failing tests**

Append to `backend/analyzer/tests.py`:

```python
@override_settings(CACHES=LOCMEM_CACHE)
class FactorRankTests(SimpleTestCase):
    """Decile packs for /factor-performance, from the factor_metrics parquet."""

    SECTORS = ['Technology', 'Energy', 'Utilities']

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    @classmethod
    def _frame(cls, n=120):
        rng = np.random.default_rng(3)
        return pd.DataFrame({
            'symbol': [f'S{i:04d}' for i in range(n)],
            'name': [f'Name {i}' for i in range(n)],
            'sector': [cls.SECTORS[i % len(cls.SECTORS)] for i in range(n)],
            'as_of': ['2026-08-05'] * n,
            '1M': rng.normal(0, 5, n), '3M': rng.normal(0, 8, n),
            '6M': rng.normal(0, 12, n), 'ytd': rng.normal(0, 15, n),
            '1MSTD': rng.uniform(0.005, 0.03, n),
            '3MSTD': rng.uniform(0.005, 0.03, n),
            '6MSTD': rng.uniform(0.005, 0.03, n),
            'YTDSTD': rng.uniform(0.005, 0.03, n),
            'beta': rng.uniform(0.4, 2.0, n),
            'div_yield': rng.uniform(0, 6, n), 'pe': rng.uniform(5, 60, n),
            'pb': rng.uniform(0.5, 20, n), 'psales': rng.uniform(0.5, 15, n),
            'pcf': rng.uniform(2, 40, n), 'roe': rng.uniform(-0.2, 1.5, n),
            'cfd': rng.uniform(0, 3, n), 'debt_equity': rng.uniform(0, 4, n),
            'fcf': rng.uniform(-5, 20, n),
        })

    def _run(self, frame=None, frequency='1M', universe='sp500'):
        from analyzer.analyzer_utils import factor_tools
        with patch.object(factor_tools.data_getter, 'load_factor_metrics',
                          return_value=self._frame() if frame is None else frame):
            return factor_tools.get_factor_ranks(frequency, universe)

    def test_pack_carries_every_key_the_page_reads_and_no_interest_coverage(self):
        from analyzer.analyzer_utils import factor_tools
        payload = self._run()
        expected = {'pe', 'ps', 'pb', 'pcf', 'div', 'fcf', 'roe', 'de', 'cfd',
                    'beta', 'stdevone', 'stdevthree', 'stdevsix', 'stdevytd',
                    'sectors'}
        self.assertEqual(set(payload['data']), expected)
        self.assertNotIn('int_cov', payload['data'])
        self.assertEqual(set(factor_tools.FACTOR_COLUMNS), expected)

    def test_each_pack_has_the_four_fields_the_charter_reads(self):
        for key, pack in self._run()['data'].items():
            with self.subTest(metric=key):
                self.assertEqual(set(pack),
                                 {'buckets', 'values', 'bucket_holdings', 'bucket_keys'})
                self.assertEqual(len(pack['buckets']), len(pack['values']))
                self.assertEqual(pack['bucket_keys'], pack['buckets'])

    def test_no_stock_is_dropped_from_the_last_bucket(self):
        """The legacy loop sliced before deciding to jump i to len(data), so a
        remainder tail landed in no bucket at all."""
        frame = self._frame(n=205)
        pack = self._run(frame=frame)['data']['pe']
        total = sum(len(v) for v in pack['bucket_holdings'].values())
        self.assertEqual(total, 205)

    def test_ten_buckets_above_a_hundred_rows_and_five_at_or_below(self):
        """Two universes, so the second call cannot hit the first's cache entry."""
        self.assertEqual(
            len(self._run(frame=self._frame(n=205), universe='sp500')['data']['pe']['buckets']), 10)
        self.assertEqual(
            len(self._run(frame=self._frame(n=80), universe='nas')['data']['pe']['buckets']), 5)

    def test_beta_buckets_rank_on_beta_not_price_to_cash_flow(self):
        """Every legacy frequency method read beta = self.get_pcf_metrics(...)."""
        frame = self._frame()
        payload = self._run(frame=frame)['data']
        beta_top = [s['metric'] for s in payload['beta']['bucket_holdings']['Q1']]
        pcf_top = [s['metric'] for s in payload['pcf']['bucket_holdings']['Q1']]
        self.assertNotEqual(beta_top, pcf_top)
        self.assertAlmostEqual(max(beta_top), frame['beta'].max(), places=6)

    def test_bucket_value_is_the_equal_weighted_mean_return(self):
        """prod(1 + w*r) - 1 compounds one asset across time; aggregating many
        assets within one period is a weighted sum."""
        frame = self._frame(n=20)
        pack = self._run(frame=frame)['data']['pe']
        top = pack['bucket_holdings']['Q1']
        expected = sum(s['return'] for s in top) / len(top) / 100
        self.assertAlmostEqual(pack['values'][0], round(expected * 100, 2), places=2)

    def test_buckets_are_ordered_by_the_metric_descending(self):
        pack = self._run()['data']['pe']
        first = [s['metric'] for s in pack['bucket_holdings']['Q1']]
        last = [s['metric'] for s in pack['bucket_holdings'][pack['buckets'][-1]]]
        self.assertGreater(min(first), max(last))

    def test_nulls_are_dropped_per_metric_not_per_row(self):
        """One null pe must not remove the stock from the roe chart."""
        frame = self._frame(n=120)
        frame.loc[0, 'pe'] = np.nan
        payload = self._run(frame=frame)['data']
        pe_count = sum(len(v) for v in payload['pe']['bucket_holdings'].values())
        roe_count = sum(len(v) for v in payload['roe']['bucket_holdings'].values())
        self.assertEqual(pe_count, 119)
        self.assertEqual(roe_count, 120)

    def test_a_column_too_sparse_to_bucket_returns_an_empty_pack(self):
        """The legacy int(len/5) == 0 path raised ZeroDivisionError."""
        frame = self._frame(n=120)
        frame['cfd'] = np.nan
        frame.loc[:1, 'cfd'] = [1.0, 2.0]
        pack = self._run(frame=frame)['data']['cfd']
        self.assertEqual(pack['buckets'], [])
        self.assertEqual(pack['bucket_holdings'], {})

    def test_sectors_are_grouped_not_bucketed(self):
        pack = self._run()['data']['sectors']
        self.assertEqual(sorted(pack['buckets']), sorted(self.SECTORS))

    def test_unknown_universe_and_frequency_raise_key_error(self):
        from analyzer.analyzer_utils import factor_tools
        with self.assertRaises(KeyError):
            factor_tools.get_factor_ranks('1M', 'not_a_universe')
        with self.assertRaises(KeyError):
            factor_tools.get_factor_ranks('9M', 'sp500')

    def test_empty_snapshot_raises_key_error(self):
        with self.assertRaises(KeyError):
            self._run(frame=pd.DataFrame())

    def test_result_is_served_from_cache_on_the_second_call(self):
        from analyzer.analyzer_utils import factor_tools
        with patch.object(factor_tools.data_getter, 'load_factor_metrics',
                          return_value=self._frame()) as loader:
            factor_tools.get_factor_ranks('1M', 'sp500')
            factor_tools.get_factor_ranks('1M', 'sp500')
        self.assertEqual(loader.call_count, 1)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank/backend
/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python manage.py test analyzer.tests.FactorRankTests -v 2
```

Expected: every case errors with `ModuleNotFoundError: No module named 'analyzer.analyzer_utils.factor_tools'`.

- [ ] **Step 3: Write the implementation**

Create `backend/analyzer/analyzer_utils/factor_tools.py`:

```python
"""Factor decile performance for /factor-performance.

Replaces backend/utils/Rankings.py, which read a pickle per index from the
bucket root and carried ~700 lines of four near-identical frequency methods.
Source is now stock_data/factor_metrics/{universe}_metrics_returns.parquet,
written by create_factor_metrics_dataframes() in stock_data_getter_v2.ipynb.

Three bugs from that version are fixed here:

  1. Every frequency method read `beta = self.get_pcf_metrics(...)`, so the
     page's beta chart rendered price-to-cash-flow data under a beta label.
  2. get_ranked_quintiles sliced a bucket before its increment logic decided
     to jump to the end, so a remainder tail (e.g. rows 200-204 of 205 at a
     20-row bucket size) landed in no bucket and vanished from both the
     returns and the holdings tables. It also divided by zero when a sparse
     column left fewer rows than buckets.
  3. Bucket return was prod(1 + w*r) - 1 -- the operation for compounding one
     asset across time, not for aggregating many assets within one period. It
     introduces cross-terms, largest exactly where decile buckets live: the
     tails of the sorted metric. It is a weighted sum here.

Interest coverage is deliberately absent: FMP reports it as 0 for a large
share of the universe including AAPL.

Units: the frequency columns are PERCENT, so bucket values divide by 100 and
the pack's `values` are then presented as round(v * 100, 2), unchanged from
the legacy contract the frontend reads.
"""
import gzip
import json

import numpy as np
import pandas as pd
from django.core.cache import cache
from django.utils import timezone

from utils.StockCalculations import GetData

data_getter = GetData()

CACHE_TTL = 86400  # 24h, matching the rest of the S3-backed endpoints

FACTOR_UNIVERSES = ('sp500', 'nas', 'tsx', 'tsx_small_cap', 'r2000',
                    'rmicro', 'msci_eafe', 'msci_sm')

FACTOR_FREQUENCIES = ('1M', '3M', '6M', 'ytd')

# Response key (what the page reads) → parquet column. 'sectors' is grouped
# rather than bucketed and is handled separately.
FACTOR_COLUMNS = {
    'pe': 'pe',
    'ps': 'psales',
    'pb': 'pb',
    'pcf': 'pcf',
    'div': 'div_yield',
    'fcf': 'fcf',
    'roe': 'roe',
    'de': 'debt_equity',
    'cfd': 'cfd',
    'beta': 'beta',
    'stdevone': '1MSTD',
    'stdevthree': '3MSTD',
    'stdevsix': '6MSTD',
    'stdevytd': 'YTDSTD',
    'sectors': 'sector',
}

LARGE_UNIVERSE_ROWS = 100  # above this, deciles; at or below, quintiles


def _bucket_count(row_count):
    return 10 if row_count > LARGE_UNIVERSE_ROWS else 5


def _native(value):
    """numpy scalar → Python scalar. json.dumps (used by the cache write) has
    no encoder for np.float64, and the sector pack's metric is a string."""
    if isinstance(value, str):
        return value
    return None if pd.isna(value) else float(value)


def _holdings(frame, frequency, metric_column):
    """[{symbol, return, metric}] — one pass over the frame; the legacy
    version built this with a per-row .iloc lookup."""
    records = (frame[['symbol', frequency, metric_column]]
               .rename(columns={frequency: 'return', metric_column: 'metric'})
               .to_dict('records'))
    return [{'symbol': str(r['symbol']),
             'return': _native(r['return']),
             'metric': _native(r['metric'])} for r in records]


def _equal_weighted_return(returns):
    """Weighted sum of an equal-weighted bucket. Returns are percent."""
    if len(returns) == 0:
        return 0.0
    return float((returns / 100).sum() / len(returns))


def _empty_pack():
    return {'buckets': [], 'values': [], 'bucket_holdings': {}, 'bucket_keys': []}


def _metric_pack(df, frequency, metric_column):
    """Rank on the metric descending, split into even buckets, and give each
    bucket its equal-weighted return."""
    ranked = (df[['symbol', frequency, metric_column]]
              .dropna()
              .sort_values(by=metric_column, ascending=False)
              .reset_index(drop=True))

    count = _bucket_count(len(ranked))
    if len(ranked) < count:
        return _empty_pack()

    labels, values, holdings = [], [], {}
    for i, bucket in enumerate(np.array_split(ranked, count), start=1):
        label = f'Q{i}'
        labels.append(label)
        values.append(round(_equal_weighted_return(bucket[frequency]) * 100, 2))
        holdings[label] = _holdings(bucket, frequency, metric_column)

    return {'buckets': labels, 'values': values,
            'bucket_holdings': holdings, 'bucket_keys': labels}


def _sector_pack(df, frequency):
    """One bucket per sector, equal-weighted within the sector."""
    ranked = df[['symbol', frequency, 'sector']].dropna()
    if ranked.empty:
        return _empty_pack()

    labels, values, holdings = [], [], {}
    for sector, group in ranked.groupby('sector', sort=True):
        labels.append(sector)
        values.append(round(_equal_weighted_return(group[frequency]) * 100, 2))
        holdings[sector] = _holdings(group, frequency, 'sector')

    return {'buckets': labels, 'values': values,
            'bucket_holdings': holdings, 'bucket_keys': labels}


def get_factor_ranks(frequency, universe):
    """Decile packs for every factor at one frequency, for one index list.

    Nulls are dropped per metric, at point of use -- a stock with no P/E still
    appears in the ROE chart. The legacy producer dropped any row with a null
    in any of ~20 columns before the data ever got here.
    """
    if universe not in FACTOR_UNIVERSES:
        raise KeyError(f"Unknown universe '{universe}'.")
    if frequency not in FACTOR_FREQUENCIES:
        raise KeyError(f"Unknown frequency '{frequency}'.")

    cache_key = f'factor:ranks:{universe}:{frequency}:v1'
    compressed = cache.get(cache_key)
    if compressed:
        return json.loads(gzip.decompress(compressed))

    df = data_getter.load_factor_metrics(universe)
    if df.empty:
        raise KeyError(f"No factor metrics for '{universe}'.")

    packs = {}
    for key, column in FACTOR_COLUMNS.items():
        if key == 'sectors':
            packs[key] = _sector_pack(df, frequency)
        else:
            packs[key] = _metric_pack(df, frequency, column)

    payload = {
        'universe': universe,
        'frequency': frequency,
        'as_of': str(df['as_of'].iloc[0]) if 'as_of' in df.columns else None,
        'constituent_count': int(len(df)),
        'data': packs,
        'last_updated': timezone.now().isoformat(),
    }
    cache.set(cache_key, gzip.compress(json.dumps(payload).encode()), CACHE_TTL)
    return payload
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank/backend
/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python manage.py test analyzer -v 2
```

Expected: 47 tests pass (34 existing + 13 new). If `test_bucket_value_is_the_equal_weighted_mean_return` fails on rounding, check that `_equal_weighted_return` divides by 100 exactly once.

- [ ] **Step 5: Delete the superseded module**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank
grep -rn "Rankings" backend --include=*.py | grep -v "backend/utils/Rankings.py"
```

Expected: no output — nothing imports it. Then:

```bash
git rm backend/utils/Rankings.py
```

Note: this removes the hardcoded `fmp_api` / `fred_api` literals from the working tree but **not from git history**. Rotating those keys is a separate action.

- [ ] **Step 6: Commit**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank
git add backend/analyzer/analyzer_utils/factor_tools.py backend/analyzer/tests.py
git commit -m "feat: replace Rankings.py with factor_tools

Reads the factor_metrics parquet instead of a pickle, and fixes three bugs:
beta buckets ranked on price-to-cash-flow, a remainder tail that landed in no
bucket, and prod(1 + w*r) - 1 where a weighted sum belongs. Drops the
hardcoded FMP/FRED keys with the old module."
```

---

### Task 6: View and URL

**Files:**
- Modify: `backend/analyzer/views.py` — append after `get_index_page_quotes` (ends around line 440)
- Modify: `backend/analyzer/urls.py` — add a path to `urlpatterns`

**Interfaces:**
- Consumes: `factor_tools.get_factor_ranks(frequency, universe)` (Task 5).
- Produces: `GET /api/getstockquintiles/<frequency>/<universe>/` returning the pack. Task 7's frontend calls it.

- [ ] **Step 1: Add the view**

Append to `backend/analyzer/views.py`:

```python
@api_view(['GET'])
def get_stock_quintiles_task(request, frequency, universe):
    """Factor decile performance for one index list at one frequency."""
    from .analyzer_utils.factor_tools import get_factor_ranks as _getter
    try:
        payload = _getter(frequency, universe)
        return Response(payload, status=status.HTTP_200_OK)
    except KeyError as e:
        return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)
    except (ValueError, TypeError) as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 2: Add the URL**

In `backend/analyzer/urls.py`, add as the last entry of `urlpatterns`:

```python
    path('getstockquintiles/<str:frequency>/<str:universe>/', views.get_stock_quintiles_task, name='stock_quintiles'),
```

- [ ] **Step 3: Verify the route resolves and the shape is right**

Start Redis and the dev server, then:

```bash
curl -s "http://localhost:8000/api/getstockquintiles/1M/sp500/" | python3 -c "
import json, sys
p = json.load(sys.stdin)
print(p['universe'], p['frequency'], p['constituent_count'], p['as_of'])
print(sorted(p['data']))
print(p['data']['pe']['buckets'], p['data']['pe']['values'])
"
curl -s -o /dev/null -w '%{http_code}\n' "http://localhost:8000/api/getstockquintiles/1M/not_a_universe/"
curl -s -o /dev/null -w '%{http_code}\n' "http://localhost:8000/api/getstockquintiles/9M/sp500/"
```

Expected: the first prints `sp500 1M 503 …`, 15 sorted keys, and `['Q1'…'Q10']` with 10 values. The two error calls print `404`.

- [ ] **Step 4: Commit**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank
git add backend/analyzer/views.py backend/analyzer/urls.py
git commit -m "feat: add /getstockquintiles/ endpoint for factor performance"
```

---

### Task 7: Frontend — universe slugs and the interest-coverage removal

**Files:**
- Modify: `src/data/chartsettings.json` — the `markets` array
- Modify: `src/pages/factor-performance.js` — five edits

**Interfaces:**
- Consumes: `GET /api/getstockquintiles/<frequency>/<universe>/` (Task 6). `markets[].value` must be one of `FACTOR_UNIVERSES`.
- Produces: nothing downstream.

- [ ] **Step 1: Replace the markets list**

In `src/data/chartsettings.json`, replace the `markets` array with:

```json
  "markets": [
    { "label": "S&P 500", "value": "sp500" },
    { "label": "NASDAQ 100", "value": "nas" },
    { "label": "Russell 2000", "value": "r2000" },
    { "label": "Russell Microcap", "value": "rmicro" },
    { "label": "S&P/TSX Composite", "value": "tsx" },
    { "label": "S&P/TSX SmallCap", "value": "tsx_small_cap" },
    { "label": "MSCI EAFE", "value": "msci_eafe" },
    { "label": "MSCI World Small Cap", "value": "msci_sm" }
  ],
```

Dow Jones is gone — there is no constituent list for it in the v2 pipeline. `MSCI World Index` becomes `MSCI EAFE`: the v2 list is IEFA (developed ex-US/Canada), not the URTH world index the v1 pipeline used. `markets` is read only by `factor-performance.js`, so the edit is contained.

- [ ] **Step 2: Add the trailing slash to the request**

`src/pages/factor-performance.js:272` — every other route in `analyzer/urls.py` ends in a slash:

```js
        periodicityData = axios.get(`${process.env.NEXT_PUBLIC_FINTANK_API_URL}/getstockquintiles/${frequency}/${index}/`)
```

- [ ] **Step 3: Remove the interest-coverage state hooks**

Delete lines 98–101:

```js
  const [intCovChart, setIntCovChart] = useState(false)
  const [intCovData, setIntCovData] = useState(null)
  const [intCovKeys, setIntCovKeys] = useState([]);
  const [intCovStocks, setIntCovStocks] = useState(null);
```

- [ ] **Step 4: Remove the `'int'` branch from handlBucketData**

Delete lines 208–213:

```js
    else if(e.target.value === 'int'){
      bucketData = intCovStocks;
      bucketKeys = intCovKeys;
      props.bucketActionRun(bucketData, bucketKeys, 'Interest Coverage Rankings', indexLabel, 'Interest Coverage');
      setLoading(false)
      !loading && window.open("/rankings/int","_blank")
    }
```

`src/pages/rankings/[slug].js` is generic and reads from the Redux bucket action, so the now-unreachable `int` slug needs no change.

- [ ] **Step 5: Remove the charter block and the chart column**

Delete lines 331–335:

```js
        const intcovCharter = factorCharter(periodicityResults?.data?.int_cov?.values, periodicityResults?.data?.int_cov?.buckets, 'Interest Coverage', 'Stock Returns Ranked by Interest Coverage')
        setIntCovChart(true)
        setIntCovData(intcovCharter)
        setIntCovKeys(periodicityResults?.data?.int_cov?.bucket_keys)
        setIntCovStocks(periodicityResults?.data?.int_cov?.bucket_holdings)
```

And the column at lines 619–629:

```js
                  {intCovChart &&
                    <Col lg='6'>
                      <Button variant="link" value={'int'} onClick={handlBucketData}>Click to view Universe bucket holdings
                          <FontAwesomeIcon
                            icon={faAngleDoubleRight}
                            className="ms-2"
                          />
                      </Button>
                      <ReactApexChart options={intCovData?.options} series={intCovData?.series} type="bar" height={325} />
                    </Col>
                    }
```

The `cfd` column that followed it now sits alone in that `<Row>`, which is fine — the grid is `lg='6'` per column.

- [ ] **Step 6: Verify no references survive and the page builds**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank
grep -n "intCov\|int_cov\|'int'" src/pages/factor-performance.js
npm run lint
```

Expected: no grep output; lint clean.

- [ ] **Step 7: Load the page**

`npm run dev` (port 8020) with the Django server and Redis up. Open `/factor-performance`, pick **S&P 500** + **1 Month Returns**, submit. Confirm: 15 charts render, there is no Interest Coverage chart, the Beta chart's Q1 holdings show high beta values (not P/E-like multiples), and "Click to view Universe bucket holdings" opens a populated `/rankings/<slug>` tab.

- [ ] **Step 8: Commit**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank
git add src/data/chartsettings.json src/pages/factor-performance.js
git commit -m "feat: point factor performance at the v2 universe slugs

Drops Dow Jones (no v2 constituent list), relabels MSCI World as MSCI EAFE
to match the IEFA-based list, adds three new lists, and removes the
interest-coverage chart."
```

---

### Task 8: Document the new pipeline stage

**Files:**
- Modify: `backend/class_files/DATA_UPLOAD.md`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Add the transform row**

In the *Stage 2 — Transform* table, after the `create_index_contr_to_var` row:

```markdown
| `create_factor_metrics_dataframes()` | daily price parquets + profiles + `ratios_ttm`/`metrics_ttm` parquets | `stock_data/factor_metrics/{sub}_metrics_returns.parquet` — one row per constituent: 1M/3M/6M/YTD returns (percent) and daily stdev, beta, sector, and 9 TTM ratios. Snapshot, overwritten each run. **Local only, no API calls** — the v1 `StockResearcher` made 3 FMP calls per stock (~30k). Interest coverage is deliberately excluded (FMP reports 0 for much of the universe). |
```

- [ ] **Step 2: Add the upload row**

In the *Stage 3 — Upload* table, after `upload_contr_to_var_files()`:

```markdown
| `upload_factor_metrics_files()` | `stock_data/factor_metrics/{sub}_metrics_returns.parquet` (8 snapshots) | **Live** — served by `GET /api/getstockquintiles/{frequency}/{universe}/` (`analyzer_utils/factor_tools.py`), which powers `/factor-performance`. Replaces the v1 `{index}_metrics_returns.pkl` objects at the bucket root |
```

- [ ] **Step 3: Update the summary section**

In *What lands on S3 after a full run*, add this bullet after the
contribution-to-vol one:

```markdown
- **Factor metric snapshots**: 8 parquets under `stock_data/factor_metrics/` (one per index list, ~10,100 constituent rows total)
```

Leave *Not yet ported* alone — none of its entries are resolved by this work.

- [ ] **Step 4: Note the retired pickles**

Under *Operational notes*, add:

```markdown
- The v1 `{sp,dj,nas,tsx,r2,msci}_metrics_returns.pkl` objects at the bucket
  root are superseded by `stock_data/factor_metrics/`. Nothing reads them —
  delete once the new path is verified. There is no `dj` list in v2: the Dow
  dropped off `/factor-performance` with the cutover.
```

- [ ] **Step 5: Nothing to commit**

`DATA_UPLOAD.md` lives under the gitignored `/backend/class_files` and has never
been tracked. Save the edits and move on — do not `git add -f` it.

---

## Verification checklist

Run after Task 8:

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank/backend
/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python manage.py test analyzer      # 47 pass
/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python -m pytest utils/test_factor_windows.py -v   # 8 pass
cd /home/franc/projects/ai_agents/ai_tooling/fintank
npm run lint                                                                             # clean
grep -rn "Rankings\|int_cov" backend src --include=*.py --include=*.js | grep -v node_modules   # no output
```

Then load `/factor-performance` and step through all 8 universes × 4 frequencies at least once — `msci_sm` is the largest list (~3,522 rows) and the slowest first (uncached) request.
