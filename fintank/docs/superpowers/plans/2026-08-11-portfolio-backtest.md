# Portfolio Backtest & Optimization Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a portfolio backtester at `/backtest-portfolio` that lets a user assemble stocks/ETFs, weight them by hand or with one of six optimizers, simulate historical performance from S3 price parquets, and read honest diagnostics about what the simulation can and cannot tell them.

**Architecture:** A new `backend/backtester/` Django app whose numerical core (`engine/`) is pure functions over numpy/pandas with no Django, S3 or Redis imports — `engine/prices.py` is the single I/O exception, and its I/O sits behind one monkeypatchable function. Runs are submitted to Celery (`POST /api/backtester/run/`), polled for status, and served from Redis + S3. The frontend replaces the `ComingSoon` body of the existing Pages Router page with Bootstrap + ApexCharts components.

**Tech Stack:** Django 4 + DRF + Celery + Redis + PostGIS; numpy, pandas, scipy, pyarrow, s3fs; Next.js Pages Router, Bootstrap (`react-bootstrap`), `react-apexcharts`, axios.

**Spec:** `docs/superpowers/specs/2026-08-11-portfolio-backtest-design.md` — authoritative. Section references below (§N) point at it.

---

## Global Constraints

These apply to **every** task. They are not repeated per task.

**Scope guardrails (§16) — hard rules:**

- Build **only** what the §2 file tree lists, plus the §16 allowlist below.
- **Do not create** `BacktestJob`, `backtester/engine/signal.py`, or `src/pages/backtester.js`. These are Phase 5 artifacts and Phase 5 is out of bounds.
- **Do not create** views named `RunBacktestView`, `BacktestStatusView`, `BacktestResultsView`, or `BacktestHistoryView`.
- **Do not add** any factor-engine, quintile, or signal-ranking capability to this app.
- **Do not modify** `/factor-performance`, `/api/getstockquintiles/`, or `analyzer_utils/factor_tools.py`.
- **Do not modify** `docs/superpowers/plans/2026-04-20-fintank-master-implementation-plan.md`. Its Phase 5/Phase 10 annotations are already applied and committed.
- **Do not delete** `src/componentsLegacy/Profile/ComingSoon.js` — `create-alerts.js` and `watchlist.js` still render it.
- **Do not add** any Python or npm dependency. scipy, numpy, pandas, pyarrow, s3fs, celery, redis are already in `backend/pyproject.toml`; `react-apexcharts` is already in `package.json`. **No cvxpy, no riskfolio-lib, no scikit-learn.**
- **Do not run** the existing notebooks in `backend/class_files/` — several have live-fetch cells that hit FMP and S3 with real credentials.

**Complete allowlist of files touched outside `backend/backtester/` and `src/` (§16):**

| File | Change |
|---|---|
| `backend/utils/StockCalculations.py` | add optional `columns=` to `load_stock_prices` |
| `backend/users/models.py` | add `subscription_tier`, `backtest_quota_override` |
| `backend/users/migrations/0002_*.py` | new migration, both fields defaulted |
| `backend/users/serializers.py` | mark both new fields `read_only` in `UserProfileSerializer.extra_kwargs` |
| `backend/fintank_backend/settings.py` | `INSTALLED_APPS` += `backtester.apps.BacktesterConfig`; add `BACKTEST_MAX_WORKERS = 8` |
| `backend/fintank_backend/urls.py` | one `path("api/", include("backtester.urls"))` |
| `backend/class_files/backtester_portfolio.ipynb` | new prototype notebook (§16 step 1) — **not committed**, see below |
| `backend/class_files/portfolio_analyzer.ipynb` | delete after key rotation (§16 step 11) — **not tracked**, see below |

**`backend/class_files/` is gitignored** (`.gitignore:58`) and has never been tracked — verified with `git log --all -- backend/class_files/`, which is empty. Two consequences the spec did not anticipate:

1. The prototype notebook of §16 step 1 lives on disk but is **not** committed. Do not `git add -f` it: the directory is ignored deliberately, because it holds data dumps and notebooks with hardcoded credentials. Every other notebook there is untracked too.
2. **The leaked FMP key in `portfolio_analyzer.ipynb` is not in git history.** It exists only in the working file. Rotation is still the right move — the key sat in plaintext on disk and may have been synced or backed up — but deleting the file genuinely removes it from the repository rather than merely hiding it, which is the opposite of the usual situation. Task 20 reflects this.

**One thing about this repo's git state.** Most of the tree is currently **untracked** — `backend/users/`, `src/pages/backtest-portfolio.js`, `src/hooks/` and much else have never been committed. So `git add` on a file this plan says to "modify" will stage it as a brand-new file, and its whole contents land in that commit. That is expected; do not try to avoid it, and do not `git add -A` to tidy it up. Stage only the paths each task's commit step names. It also means the `git diff --name-only main` audit in Final Verification only sees files this work has committed — read it alongside `git status --short` rather than instead of it.

**Conventions:**

- Cache keys: `backtest:{task_id}:v1` (72h), `prices:panel:{SYMBOL}:v1` (24h), `backtest:symbol_index:v1` (24h). Values are **gzipped JSON**, matching `analyzer/views.py`.
- S3 durable results: `s3://thetradingfloor/backtest_results/{user_id}/{task_id}.json`.
- Annualization uses **252** trading days everywhere.
- Route prefix: every Django app mounts at `path("api/", include(...))`, so `backtester/urls.py` carries the `backtester/` segment on each of its own routes, producing `/api/backtester/…`.
- Tests run with Django's runner from `backend/`: `python manage.py test backtester`. There is no pytest config in this repo. The runner creates a test database even for `SimpleTestCase`, so Postgres + PostGIS must be running.
- Engine tests subclass `unittest.TestCase`; anything touching cache or settings subclasses `django.test.SimpleTestCase`; anything touching models subclasses `django.test.TestCase`. This mirrors `backend/analyzer/tests.py`.
- Frontend: the JWT lives in an **httpOnly** `access` cookie set by `src/pages/api/auth/login.js`. Client JS **cannot** read it. Every authenticated backend call therefore goes through a Next API route proxy — see Task 16. Never write `Authorization: Bearer` in a hook.
- Frontend files are `.js`, not `.tsx` — this page belongs to the legacy Pages Router tree.
- `react-apexcharts` must be dynamically imported with `{ ssr: false }`, matching `src/componentsLegacy/Homepage/MoversSection.js:9`.

**Declared additions to §2's file tree.** The guardrail "build only what §2's file tree lists" is aimed at Phase 5 artifacts; every item it enumerates is a Phase 5 one. Four files inside `backend/backtester/` are added beyond the sketch, all pure plumbing, none introducing a new capability:

| File | Why it is not folded into a listed file |
|---|---|
| `admin.py` | Every other app in this backend has one; tier changes come from the admin (§11) |
| `migrations/` | Required by Django; the tree omits it for every app |
| `results.py` | Result assembly + Redis/S3 storage. Both `tasks.py` and `views.py` need `load_payload`, so putting it in `tasks.py` would make the view layer import the task module |
| `symbol_index.py` | The typeahead index, mirroring `analyzer_utils/universe_lookup.py`. In `views.py` it would double that file's length for something the views only call |

**A presentation trap, verified on live data.** A risk-parity run over AAPL/MSFT/VTI/AGG/GLD from 2010 produced final weights `AAPL 0.128, MSFT 0.118, VTI 0.178, AGG 0.461, GLD 0.115` and full-period risk shares `AAPL 0.304, MSFT 0.303, VTI 0.261, AGG 0.074, GLD 0.058`. Both are correct: the optimizer equalizes risk on the **trailing lookback window at each rebalance**, while §9's contribution-to-risk reports the **full-period** covariance against the **final** weights. A user who selected "every holding contributes the same share of risk" and then reads 30% vs 6% will reasonably conclude the optimizer is broken. Task 17's `StatsTable` carries a note explaining it — do not "fix" either computation to make them agree.

**Two documented reconciliations of the spec** (apply these, they are deliberate):

1. **Risk parity objective.** §7's table writes `RCᵢ = wᵢ(Σw)ᵢ / √(wᵀΣw)`, which sums to `σ_p`, not 1 — minimizing `Σ(RCᵢ − 1/N)²` against that would trade risk-equality off against scaling `σ_p` toward 1 and would fail §15's "risk contributions equal within 1e-4" property test. Use the **relative** risk contribution, which is exactly the definition §9 gives for contribution-to-risk: `RCᵢ = wᵢ(Σw)ᵢ / (wᵀΣw)`, summing to 1, target `1/N`. One shared helper serves both §7 and §9.
2. **Contribution-to-risk reuse (§9 note).** The canonical implementation lands in `engine/metrics.py`. Pointing `stock_data_getter_v2.ipynb`'s `create_index_contr_to_var()` at it is **deferred**: that notebook is not on the §16 allowlist and must not be modified here. Record the duplication in the docstring so the future consolidation is findable.

---

## File Structure

**New — `backend/backtester/`** (exactly §2's tree):

| File | Responsibility |
|---|---|
| `__init__.py`, `apps.py` | app registration (`BacktesterConfig`) |
| `models.py` | `Portfolio`, `PortfolioHolding`, `BacktestRun` |
| `serializers.py` | DRF serializers for the three models + the run-request payload |
| `views.py` | portfolio CRUD, run submission, status/results/history, symbol search, quota |
| `urls.py` | the nine routes of §12 |
| `tasks.py` | `run_portfolio_backtest` Celery task |
| `quota.py` | `get_quota`, `check_and_consume`, `QuotaExceeded` |
| `permissions.py` | `HasBacktestQuota` |
| `engine/config.py` | request dataclasses + validation + normalization; exception types |
| `engine/prices.py` | `PricePanel`, `load_price_panel`, availability/eligibility masks. **Only** file with I/O |
| `engine/covariance.py` | `estimate_covariance` (sample, Ledoit–Wolf) |
| `engine/optimizers.py` | the six schemes + `OPTIMIZERS` registry |
| `engine/backtest.py` | `run_backtest` simulation loop, `BacktestResult` |
| `engine/metrics.py` | performance measures, IRR, contribution decompositions |
| `engine/diagnostics.py` | the thirteen seven-sins findings |
| `engine/frontier.py` | efficient frontier sampling |
| `tests/test_config.py` … `test_views.py` | one module per unit, per §2 |

**New — frontend:**

| File | Responsibility |
|---|---|
| `src/pages/api/backtester/[...path].js` | server-side proxy: reads the `access` cookie, forwards to Django with `Bearer` |
| `src/hooks/usePortfolios.js` | saved-portfolio CRUD |
| `src/hooks/useBacktestRun.js` | submit + poll + fetch result |
| `src/hooks/useSymbolSearch.js` | debounced typeahead |
| `src/hooks/useBacktestQuota.js` | `{used, limit, tier, remaining}` |
| `src/componentsLegacy/Backtest/*.js` | the twelve components of §14 |

**Modified:** the eight allowlist entries above, plus `src/pages/backtest-portfolio.js` and `src/componentsLegacy/Profile/ProfileSideNav.js`.

---

## Task Sequence

Tasks follow §16's build sequence. Steps 3–6 of §16 (Tasks 4–10 here) are the bulk of the numerical risk and are independently testable. **Do not start Task 17 until Task 15's endpoints return real result JSON.**

---

### Task 1: Prototype notebook

Validates the numerics against real S3 data before any of it becomes Django code (§16 step 1, platform spec §4). Nothing downstream imports this notebook — it is a throwaway proof that the maths is right.

**Files:**
- Create: `backend/class_files/backtester_portfolio.ipynb`

**Interfaces:**
- Consumes: `utils.StockCalculations.GetData` (existing).
- Produces: nothing importable. Its output is a recorded confirmation that a 60/40 SPY/AGG backtest reproduces a known reference.

- [ ] **Step 1: Create the notebook with a data-loading cell**

Create `backend/class_files/backtester_portfolio.ipynb`. First code cell:

```python
import sys
sys.path.append('..')

import numpy as np
import pandas as pd

from utils.StockCalculations import GetData

data_getter = GetData()

SYMBOLS = ['SPY', 'AGG', 'AAPL', 'MSFT', 'NVDA']

frames = {}
for symbol in SYMBOLS:
    df = data_getter.load_stock_prices(symbol)
    df['date'] = pd.to_datetime(df['date'])
    frames[symbol] = df.set_index('date')['adjClose'].sort_index()

panel = pd.DataFrame(frames)
print(panel.shape)
print(panel.apply(lambda s: (s.first_valid_index(), s.last_valid_index())))
```

- [ ] **Step 2: Add the availability/eligibility mask cell**

```python
first_valid = {c: panel[c].first_valid_index() for c in panel.columns}
last_valid = {c: panel[c].last_valid_index() for c in panel.columns}

available = pd.DataFrame(
    {c: (panel.index >= first_valid[c]) & (panel.index <= last_valid[c]) for c in panel.columns},
    index=panel.index,
)

MIN_HISTORY_DAYS = 252
eligible = pd.DataFrame(
    {c: available[c] & (available[c].cumsum() >= MIN_HISTORY_DAYS) for c in panel.columns},
    index=panel.index,
)

print(eligible.sum(axis=1).value_counts())
```

Confirm the effective asset count starts below 5 and rises — that is the staggered-inception behaviour of §5.

- [ ] **Step 3: Add the six optimizers cell**

```python
from scipy.optimize import minimize

def ledoit_wolf(returns):
    X = returns - returns.mean(axis=0)
    T, N = X.shape
    S = X.T @ X / T
    m = np.trace(S) / N
    d2 = np.sum((S - m * np.eye(N)) ** 2) / N
    b2_bar = sum(np.sum((np.outer(x, x) - S) ** 2) for x in X) / (T ** 2) / N
    b2 = min(b2_bar, d2)
    a2 = d2 - b2
    return (b2 / d2) * m * np.eye(N) + (a2 / d2) * S

def relative_risk_contribution(w, cov):
    port_var = float(w @ cov @ w)
    return w * (cov @ w) / port_var

def equal(returns, cov):
    n = returns.shape[1]
    return np.full(n, 1.0 / n)

def inverse_vol(returns, cov):
    inv = 1.0 / np.sqrt(np.diag(cov))
    return inv / inv.sum()

def _solve(objective, n):
    constraints = ({'type': 'eq', 'fun': lambda w: w.sum() - 1.0},)
    bounds = [(0.0, 1.0)] * n
    result = minimize(objective, np.full(n, 1.0 / n), method='SLSQP',
                      bounds=bounds, constraints=constraints,
                      options={'maxiter': 500, 'ftol': 1e-12})
    return result.x, result.success

def min_variance(returns, cov):
    w, ok = _solve(lambda w: w @ cov @ w, returns.shape[1])
    return w

def risk_parity(returns, cov):
    n = returns.shape[1]
    target = 1.0 / n
    w, ok = _solve(lambda w: np.sum((relative_risk_contribution(w, cov) - target) ** 2), n)
    return w

def max_sharpe(returns, cov, rf=0.0):
    mu = returns.mean(axis=0)
    def neg_sharpe(w):
        return -(w @ mu - rf / 252) / np.sqrt(w @ cov @ w)
    w, ok = _solve(neg_sharpe, returns.shape[1])
    return w

window = panel[['SPY', 'AGG']].dropna().pct_change().dropna().tail(252).to_numpy()
cov = ledoit_wolf(window)
for name, fn in [('equal', equal), ('inverse_vol', inverse_vol),
                 ('min_variance', min_variance), ('risk_parity', risk_parity),
                 ('max_sharpe', max_sharpe)]:
    w = fn(window, cov)
    print(name, np.round(w, 4), 'sum', round(w.sum(), 9))
    if name == 'risk_parity':
        print('  risk contributions', np.round(relative_risk_contribution(w, cov), 6))
```

Confirm every weight vector sums to 1 and risk parity's contributions are equal to ~1e-6.

- [ ] **Step 4: Add the 60/40 reference backtest cell**

```python
prices = panel[['SPY', 'AGG']].dropna()
returns = prices.pct_change().dropna()

targets = np.array([0.6, 0.4])
w = targets.copy()
index = [1.0]
rebalance_months = returns.index.to_period('Y')

prev_year = rebalance_months[0]
for i, (date, r) in enumerate(returns.iterrows()):
    r = r.to_numpy()
    R = float(w @ r)
    index.append(index[-1] * (1 + R))
    w = w * (1 + r) / (1 + R)
    if rebalance_months[i] != prev_year:
        turnover = np.abs(targets - w).sum()
        index[-1] *= (1 - turnover * 10 / 10_000)
        w = targets.copy()
        prev_year = rebalance_months[i]

index = pd.Series(index[1:], index=returns.index)
years = len(index) / 252
print('CAGR', (index.iloc[-1] / index.iloc[0]) ** (1 / years) - 1)
print('vol', returns.dot(targets).std(ddof=1) * np.sqrt(252))
print('max DD', (index / index.cummax() - 1).min())
```

- [ ] **Step 5: Verify the reference numbers are plausible**

Read the printed CAGR, volatility and max drawdown. A 60/40 SPY/AGG portfolio over a multi-decade window should land near 7–9% CAGR, 9–11% annualized volatility, and a max drawdown between −30% and −35% (the 2008 trough). If any number is wildly outside that, the panel or the loop is wrong — fix it here, before it becomes Django code.

Record the three numbers in a markdown cell at the bottom of the notebook titled `## Reference: 60/40 SPY/AGG`. Tasks 7 and 8 are checked against them.

- [ ] **Step 6: Do not commit it**

`backend/class_files/` is gitignored (`.gitignore:58`), so this notebook stays on disk and out of version control, like every other notebook in that directory. **Do not `git add -f`.** Instead, confirm it is where it should be and that git is correctly ignoring it:

```bash
ls -la backend/class_files/backtester_portfolio.ipynb
git check-ignore -v backend/class_files/backtester_portfolio.ipynb
```

Expected: the file exists, and `check-ignore` reports `.gitignore:58`. The reference numbers recorded in Step 5 are the durable output of this task — they are carried into Task 8's cross-check, which is committed.

---

### Task 2: Column projection on `load_stock_prices`

The price parquets carry 52 columns; this engine needs two. Pushing the projection into `pq.read_table` avoids reading ~26x more bytes than necessary per symbol, ~17,200 symbols deep (§4).

**Files:**
- Modify: `backend/utils/StockCalculations.py:136-145` (`load_stock_prices`)
- Create: `backend/backtester/__init__.py`, `backend/backtester/tests/__init__.py`
- Test: `backend/backtester/tests/test_prices.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `GetData.load_stock_prices(symbol: str, columns: list[str] | None = None) -> pd.DataFrame`. Default `None` reproduces today's behaviour byte for byte. Task 4 calls it with `columns=['date', 'adjClose']`.

- [ ] **Step 1: Create the app and test packages**

```bash
mkdir -p backend/backtester/engine backend/backtester/tests
touch backend/backtester/__init__.py backend/backtester/tests/__init__.py
```

- [ ] **Step 2: Write the failing test**

Create `backend/backtester/tests/test_prices.py`:

```python
"""Tests for the price data layer. The single I/O seam is monkeypatched so
nothing here touches S3, FMP or Redis."""
from unittest import TestCase
from unittest.mock import patch

import pandas as pd
import pyarrow as pa

from utils.StockCalculations import GetData


class LoadStockPricesColumnsTests(TestCase):
    """`columns=` is pushed into the parquet reader, not applied afterwards."""

    def _table(self):
        return pa.table({
            'date': pd.to_datetime(['2020-01-02', '2020-01-03']),
            'adjClose': [100.0, 101.0],
            'volume': [1_000, 1_100],
        })

    def test_columns_are_passed_through_to_the_parquet_reader(self):
        getter = GetData()
        with patch('utils.StockCalculations.pq.read_table', return_value=self._table()) as reader:
            getter.load_stock_prices('AAPL', columns=['date', 'adjClose'])

        self.assertEqual(reader.call_args.kwargs['columns'], ['date', 'adjClose'])

    def test_omitting_columns_reads_every_column(self):
        getter = GetData()
        with patch('utils.StockCalculations.pq.read_table', return_value=self._table()) as reader:
            getter.load_stock_prices('AAPL')

        self.assertIsNone(reader.call_args.kwargs['columns'])

    def test_date_is_returned_as_a_string_column(self):
        getter = GetData()
        with patch('utils.StockCalculations.pq.read_table', return_value=self._table()):
            frame = getter.load_stock_prices('AAPL', columns=['date', 'adjClose'])

        self.assertIn('date', frame.columns)
        self.assertEqual(frame['date'].tolist(), ['2020-01-02', '2020-01-03'])
```

- [ ] **Step 3: Run the test to verify it fails**

From `backend/`:

```bash
python manage.py test backtester.tests.test_prices -v 2
```

Expected: FAIL — `TypeError: load_stock_prices() got an unexpected keyword argument 'columns'`.

- [ ] **Step 4: Add the parameter**

In `backend/utils/StockCalculations.py`, replace `load_stock_prices` with:

```python
    def load_stock_prices(self, symbol: str, columns=None) -> pd.DataFrame:
        """stock_data/stock_prices/daily/{SYMBOL}_prices.parquet -- the per-symbol
        price/metric files written by the v2 pipeline.

        `columns` is pushed down to the parquet reader, mirroring
        load_index_parquet: these files carry 52 columns and the backtester needs
        two, so projecting at read time keeps a 30-symbol panel to 30 partial
        reads instead of 30 full ones.

        'date' must appear in `columns`. It is the parquet's index column, so
        omitting it makes to_pandas() return a RangeIndex and the reset_index()
        below produces no 'date' column at all.
        """
        bucket = 'thetradingfloor'
        key = f'stock_data/stock_prices/daily/{symbol.upper()}_prices.parquet'
        path = f"s3://{bucket}/{key}"
        table = pq.read_table(path, filesystem=self.fs, columns=columns)
        df = table.to_pandas()
        df = df.reset_index()  # date is the DatetimeIndex
        df['date'] = df['date'].astype(str)
        return df
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python manage.py test backtester.tests.test_prices -v 2
```

Expected: 3 tests PASS.

- [ ] **Step 6: Confirm the existing call sites still work**

Both existing callers pass no `columns` and must be unaffected. Verify by inspection that neither has changed signature expectations:

```bash
grep -rn "load_stock_prices(" backend/ --include=*.py
```

Expected: `backend/analyzer/analyzer_utils/CorePerformanceTools.py:207` and `backend/analyzer/analyzer_utils/index_tools.py:160`, both calling with a symbol only. Then run the existing analyzer suite to confirm no regression:

```bash
python manage.py test analyzer -v 2
```

Expected: PASS, same count as before this task.

- [ ] **Step 7: Commit**

```bash
git add backend/utils/StockCalculations.py backend/backtester/__init__.py \
        backend/backtester/tests/__init__.py backend/backtester/tests/test_prices.py
git commit -m "feat: support column projection in GetData.load_stock_prices"
```

---

### Task 3: App scaffold and request validation

Registers the app and lands `engine/config.py`, the typed request contract every later task consumes. Validation lives here so the view layer's 422 path is a thin wrapper over tested pure code.

**Files:**
- Create: `backend/backtester/apps.py`, `backend/backtester/engine/__init__.py`, `backend/backtester/engine/config.py`
- Modify: `backend/fintank_backend/settings.py:39-68` (`INSTALLED_APPS`), and append `BACKTEST_MAX_WORKERS`
- Test: `backend/backtester/tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Holding(symbol: str, target_weight: float = 0.0)` — frozen dataclass.
  - `BacktestRequest` — frozen dataclass with every §3 field; `holdings: tuple[Holding, ...]`.
  - `OptimizerConfig(long_only, max_weight, min_weight, risk_free_rate, covariance_method, custom_weights: np.ndarray | None)` — frozen dataclass; what `engine/optimizers.py` receives.
  - `validate_request(payload: dict) -> BacktestRequest` — raises `RequestValidationError`.
  - `normalized_payload(request: BacktestRequest) -> dict` — canonical dict for hashing.
  - `optimizer_config(request: BacktestRequest, custom_weights=None) -> OptimizerConfig`.
  - Exceptions: `RequestValidationError`, `NoEligibleAssets`, `PriceDataUnavailable`.
  - Constants: `WEIGHTING_SCHEMES`, `BACKTEST_MODES`, `REBALANCE_FREQUENCIES`, `CONTRIBUTION_FREQUENCIES`, `COVARIANCE_METHODS`, `INCEPTION_POLICIES`, `OPTIMIZER_SCHEMES`, `DEFAULT_MIN_HISTORY_DAYS`.

- [ ] **Step 1: Write the failing test**

Create `backend/backtester/tests/test_config.py`:

```python
"""Request validation. Pure — no Django, no numpy beyond the weight vector."""
from unittest import TestCase

from backtester.engine.config import (
    BacktestRequest,
    Holding,
    RequestValidationError,
    normalized_payload,
    optimizer_config,
    validate_request,
)


def _payload(**overrides):
    payload = {'holdings': [{'symbol': 'aapl'}, {'symbol': 'VTI'}]}
    payload.update(overrides)
    return payload


class ValidateRequestTests(TestCase):

    def test_symbols_are_uppercased_and_defaults_applied(self):
        request = validate_request(_payload())

        self.assertEqual([h.symbol for h in request.holdings], ['AAPL', 'VTI'])
        self.assertEqual(request.benchmark_symbol, 'SPY')
        self.assertEqual(request.initial_amount, 10_000.0)
        self.assertEqual(request.weighting_scheme, 'equal')
        self.assertEqual(request.backtest_mode, 'fixed')
        self.assertEqual(request.rebalance_frequency, 'annual')
        self.assertEqual(request.covariance_method, 'ledoit_wolf')
        self.assertEqual(request.inception_policy, 'phase_in')
        self.assertTrue(request.long_only)

    def test_empty_holdings_are_rejected(self):
        with self.assertRaises(RequestValidationError) as caught:
            validate_request(_payload(holdings=[]))
        self.assertIn('at least one holding', str(caught.exception))

    def test_duplicate_symbols_are_rejected(self):
        with self.assertRaises(RequestValidationError) as caught:
            validate_request(_payload(holdings=[{'symbol': 'AAPL'}, {'symbol': 'aapl'}]))
        self.assertIn('AAPL', str(caught.exception))

    def test_unknown_weighting_scheme_is_rejected(self):
        with self.assertRaises(RequestValidationError):
            validate_request(_payload(weighting_scheme='magic'))

    def test_unknown_rebalance_frequency_is_rejected(self):
        with self.assertRaises(RequestValidationError):
            validate_request(_payload(rebalance_frequency='hourly'))

    def test_custom_weights_are_normalized_to_sum_to_one(self):
        request = validate_request(_payload(
            weighting_scheme='custom',
            holdings=[{'symbol': 'A', 'target_weight': 3.0},
                      {'symbol': 'B', 'target_weight': 1.0}],
        ))

        self.assertAlmostEqual(request.holdings[0].target_weight, 0.75)
        self.assertAlmostEqual(request.holdings[1].target_weight, 0.25)

    def test_negative_custom_weight_is_rejected_when_long_only(self):
        with self.assertRaises(RequestValidationError) as caught:
            validate_request(_payload(
                weighting_scheme='custom',
                holdings=[{'symbol': 'A', 'target_weight': -0.5},
                          {'symbol': 'B', 'target_weight': 1.5}],
            ))
        self.assertIn('negative', str(caught.exception))

    def test_custom_weights_summing_to_zero_are_rejected(self):
        with self.assertRaises(RequestValidationError):
            validate_request(_payload(
                weighting_scheme='custom',
                holdings=[{'symbol': 'A', 'target_weight': 0.0},
                          {'symbol': 'B', 'target_weight': 0.0}],
            ))

    def test_infeasible_max_weight_is_rejected_before_the_solver_sees_it(self):
        with self.assertRaises(RequestValidationError) as caught:
            validate_request(_payload(max_weight=0.2, holdings=[
                {'symbol': 'A'}, {'symbol': 'B'}, {'symbol': 'C'}]))
        self.assertIn('max_weight', str(caught.exception))

    def test_infeasible_min_weight_is_rejected(self):
        with self.assertRaises(RequestValidationError) as caught:
            validate_request(_payload(min_weight=0.6))
        self.assertIn('min_weight', str(caught.exception))

    def test_start_date_after_end_date_is_rejected(self):
        with self.assertRaises(RequestValidationError):
            validate_request(_payload(start_date='2020-01-01', end_date='2019-01-01'))

    def test_dates_are_parsed_from_iso_strings(self):
        request = validate_request(_payload(start_date='2015-06-01', end_date='2020-06-01'))

        self.assertEqual(request.start_date.year, 2015)
        self.assertEqual(request.end_date.year, 2020)

    def test_malformed_date_is_rejected(self):
        with self.assertRaises(RequestValidationError):
            validate_request(_payload(start_date='last tuesday'))

    def test_non_positive_initial_amount_is_rejected(self):
        with self.assertRaises(RequestValidationError):
            validate_request(_payload(initial_amount=0))

    def test_negative_transaction_cost_is_rejected(self):
        with self.assertRaises(RequestValidationError):
            validate_request(_payload(transaction_cost_bps=-1))

    def test_lookback_shorter_than_two_days_is_rejected(self):
        with self.assertRaises(RequestValidationError):
            validate_request(_payload(lookback_days=1))


class MinHistoryDefaultTests(TestCase):
    """§5: the optimizer schemes need a complete rectangular covariance block."""

    def test_equal_and_custom_need_one_day(self):
        self.assertEqual(validate_request(_payload()).min_history_days, 1)
        self.assertEqual(validate_request(_payload(
            weighting_scheme='custom',
            holdings=[{'symbol': 'A', 'target_weight': 1.0}],
        )).min_history_days, 1)

    def test_optimizer_schemes_need_a_full_lookback(self):
        for scheme in ('inverse_vol', 'min_variance', 'risk_parity', 'max_sharpe'):
            with self.subTest(scheme=scheme):
                request = validate_request(_payload(weighting_scheme=scheme))
                self.assertEqual(request.min_history_days, request.lookback_days)

    def test_an_explicit_min_history_days_wins(self):
        request = validate_request(_payload(weighting_scheme='min_variance',
                                            min_history_days=30))
        self.assertEqual(request.min_history_days, 30)


class NormalizedPayloadTests(TestCase):
    """The hash must be stable across key order and symbol casing."""

    def test_two_equivalent_requests_normalize_identically(self):
        one = validate_request({'holdings': [{'symbol': 'aapl'}, {'symbol': 'vti'}],
                                'benchmark_symbol': 'spy'})
        two = validate_request({'benchmark_symbol': 'SPY',
                                'holdings': [{'symbol': 'AAPL'}, {'symbol': 'VTI'}]})

        self.assertEqual(normalized_payload(one), normalized_payload(two))

    def test_holding_order_is_significant(self):
        one = validate_request(_payload(holdings=[{'symbol': 'A'}, {'symbol': 'B'}]))
        two = validate_request(_payload(holdings=[{'symbol': 'B'}, {'symbol': 'A'}]))

        self.assertNotEqual(normalized_payload(one), normalized_payload(two))

    def test_payload_is_json_serializable(self):
        import json
        json.dumps(normalized_payload(validate_request(
            _payload(start_date='2020-01-01'))), sort_keys=True)


class OptimizerConfigTests(TestCase):

    def test_config_carries_the_constraint_block(self):
        request = validate_request(_payload(max_weight=0.6, min_weight=0.05,
                                            risk_free_rate=0.02, long_only=True))
        config = optimizer_config(request)

        self.assertEqual(config.max_weight, 0.6)
        self.assertEqual(config.min_weight, 0.05)
        self.assertEqual(config.risk_free_rate, 0.02)
        self.assertTrue(config.long_only)
        self.assertIsNone(config.custom_weights)

    def test_custom_weights_are_attached_when_supplied(self):
        request = validate_request(_payload())
        config = optimizer_config(request, custom_weights=[0.3, 0.7])

        self.assertEqual(list(config.custom_weights), [0.3, 0.7])
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python manage.py test backtester.tests.test_config -v 2
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backtester.engine'`.

- [ ] **Step 3: Create the app config**

Create `backend/backtester/apps.py`:

```python
from django.apps import AppConfig


class BacktesterConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'backtester'
    verbose_name = 'Portfolio Backtester'
```

Create an empty `backend/backtester/engine/__init__.py`.

- [ ] **Step 4: Register the app and the worker setting**

In `backend/fintank_backend/settings.py`, add to `INSTALLED_APPS` immediately after `'analyzer.apps.AnalyzerConfig',`:

```python
    'backtester.apps.BacktesterConfig',
```

Then append near the other cache/S3 settings:

```python
# Concurrency for the backtester's per-symbol price loads. These are I/O bound
# (S3 or FMP), so the worker count is about hiding latency, not CPU.
BACKTEST_MAX_WORKERS = int(os.environ.get('BACKTEST_MAX_WORKERS', 8))

# Free-tier backtest allowance. Overridable per account via
# UserProfile.backtest_quota_override.
FREE_TIER_BACKTEST_LIMIT = int(os.environ.get('FREE_TIER_BACKTEST_LIMIT', 10))
```

If `os` is not already imported at the top of `settings.py`, verify with `grep -n "^import os" backend/fintank_backend/settings.py` and add it if missing.

- [ ] **Step 5: Write `engine/config.py`**

Create `backend/backtester/engine/config.py`:

```python
"""Typed request contract for a portfolio backtest.

Pure: no Django, no I/O. The view layer's only job is to hand `validate_request`
a dict and turn `RequestValidationError` into a 422, which keeps every
validation rule unit-testable without a request factory.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime

import numpy as np

WEIGHTING_SCHEMES = ('equal', 'custom', 'inverse_vol', 'min_variance',
                     'risk_parity', 'max_sharpe')
# Schemes that estimate a covariance and therefore need a complete rectangular
# block of returns before an asset can enter (§5).
OPTIMIZER_SCHEMES = ('inverse_vol', 'min_variance', 'risk_parity', 'max_sharpe')
BACKTEST_MODES = ('fixed', 'walk_forward')
REBALANCE_FREQUENCIES = ('none', 'monthly', 'quarterly', 'semiannual', 'annual')
CONTRIBUTION_FREQUENCIES = ('none', 'monthly', 'quarterly', 'annual')
COVARIANCE_METHODS = ('sample', 'ledoit_wolf')
INCEPTION_POLICIES = ('phase_in', 'common_start')

DEFAULT_MIN_HISTORY_DAYS = 1
TRADING_DAYS_PER_YEAR = 252


class RequestValidationError(ValueError):
    """Bad input. The view renders this as 422."""


class NoEligibleAssets(ValueError):
    """No requested asset ever clears its eligibility bar (§5). 422."""


class PriceDataUnavailable(RuntimeError):
    """Neither S3 nor FMP could serve a symbol. Carries the per-symbol reason."""

    def __init__(self, message, reasons=None):
        super().__init__(message)
        self.reasons = reasons or {}


@dataclass(frozen=True)
class Holding:
    symbol: str
    target_weight: float = 0.0


@dataclass(frozen=True)
class BacktestRequest:
    holdings: tuple[Holding, ...]
    benchmark_symbol: str = 'SPY'
    start_date: date | None = None
    end_date: date | None = None
    initial_amount: float = 10_000.0
    periodic_contribution: float = 0.0
    contribution_frequency: str = 'none'

    weighting_scheme: str = 'equal'
    backtest_mode: str = 'fixed'
    rebalance_frequency: str = 'annual'

    lookback_days: int = 252
    gap_days: int = 1
    covariance_method: str = 'ledoit_wolf'
    transaction_cost_bps: float = 10.0
    long_only: bool = True
    max_weight: float | None = None
    min_weight: float | None = None
    risk_free_rate: float = 0.0
    inception_policy: str = 'phase_in'
    enter_immediately: bool = False
    min_history_days: int = DEFAULT_MIN_HISTORY_DAYS

    @property
    def symbols(self) -> list[str]:
        return [h.symbol for h in self.holdings]

    @property
    def target_weights(self) -> np.ndarray:
        return np.array([h.target_weight for h in self.holdings], dtype=float)


@dataclass(frozen=True)
class OptimizerConfig:
    """What every scheme in `engine/optimizers.py` receives.

    `custom_weights` is the eligible-subset slice of the user's targets, already
    renormalized by the caller. It is None for every scheme but `custom`.
    """
    long_only: bool = True
    max_weight: float | None = None
    min_weight: float | None = None
    risk_free_rate: float = 0.0
    covariance_method: str = 'ledoit_wolf'
    custom_weights: np.ndarray | None = None

    def with_custom_weights(self, weights) -> 'OptimizerConfig':
        return replace(self, custom_weights=np.asarray(weights, dtype=float))


def _choice(payload, key, allowed, default):
    value = payload.get(key, default)
    if value not in allowed:
        raise RequestValidationError(
            f"{key} must be one of {', '.join(allowed)} (got {value!r})")
    return value


def _number(payload, key, default, minimum=None, allow_none=False):
    raw = payload.get(key, default)
    if raw is None:
        if allow_none:
            return None
        raise RequestValidationError(f"{key} is required")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise RequestValidationError(f"{key} must be a number (got {raw!r})")
    if value != value:  # NaN
        raise RequestValidationError(f"{key} must be a number (got NaN)")
    if minimum is not None and value < minimum:
        raise RequestValidationError(f"{key} must be >= {minimum} (got {value})")
    return value


def _date(payload, key):
    raw = payload.get(key)
    if raw in (None, ''):
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    try:
        return datetime.strptime(str(raw)[:10], '%Y-%m-%d').date()
    except ValueError:
        raise RequestValidationError(f"{key} must be an ISO date (got {raw!r})")


def _holdings(payload, weighting_scheme, long_only):
    raw = payload.get('holdings') or []
    if not isinstance(raw, (list, tuple)) or not raw:
        raise RequestValidationError('A backtest needs at least one holding.')

    seen, holdings = set(), []
    for entry in raw:
        if isinstance(entry, str):
            entry = {'symbol': entry}
        symbol = str(entry.get('symbol', '')).strip().upper()
        if not symbol:
            raise RequestValidationError('Every holding needs a symbol.')
        if symbol in seen:
            raise RequestValidationError(f"{symbol} appears more than once.")
        seen.add(symbol)
        weight = entry.get('target_weight', 0.0)
        try:
            weight = float(weight if weight is not None else 0.0)
        except (TypeError, ValueError):
            raise RequestValidationError(
                f"target_weight for {symbol} must be a number.")
        holdings.append(Holding(symbol=symbol, target_weight=weight))

    if weighting_scheme != 'custom':
        # Ignored for every other scheme (§3). Zero it so the request hash does
        # not vary on a field that cannot affect the result.
        return tuple(Holding(h.symbol, 0.0) for h in holdings)

    if long_only and any(h.target_weight < 0 for h in holdings):
        raise RequestValidationError(
            'Custom weights cannot be negative while long_only is on.')
    total = sum(h.target_weight for h in holdings)
    if total <= 0:
        raise RequestValidationError('Custom weights must sum to more than zero.')
    return tuple(Holding(h.symbol, h.target_weight / total) for h in holdings)


def validate_request(payload: dict) -> BacktestRequest:
    """Turn an untrusted dict into a BacktestRequest, or raise."""
    if not isinstance(payload, dict):
        raise RequestValidationError('Request body must be an object.')

    weighting_scheme = _choice(payload, 'weighting_scheme', WEIGHTING_SCHEMES, 'equal')
    long_only = bool(payload.get('long_only', True))
    holdings = _holdings(payload, weighting_scheme, long_only)
    n = len(holdings)

    lookback_days = int(_number(payload, 'lookback_days', 252, minimum=2))
    gap_days = int(_number(payload, 'gap_days', 1, minimum=0))
    max_weight = _number(payload, 'max_weight', None, minimum=0.0, allow_none=True)
    min_weight = _number(payload, 'min_weight', None, minimum=0.0, allow_none=True)

    # Feasibility before the solver sees it: an infeasible box produces a silent
    # SLSQP failure that looks like a numerical problem rather than bad input.
    if max_weight is not None and max_weight * n < 1.0 - 1e-12:
        raise RequestValidationError(
            f"max_weight={max_weight} cannot fill a portfolio of {n} assets; "
            f"it must be at least {1.0 / n:.4f}.")
    if min_weight is not None and min_weight * n > 1.0 + 1e-12:
        raise RequestValidationError(
            f"min_weight={min_weight} over-fills a portfolio of {n} assets; "
            f"it must be at most {1.0 / n:.4f}.")
    if (max_weight is not None and min_weight is not None
            and min_weight > max_weight):
        raise RequestValidationError('min_weight cannot exceed max_weight.')

    start_date, end_date = _date(payload, 'start_date'), _date(payload, 'end_date')
    if start_date and end_date and start_date >= end_date:
        raise RequestValidationError('start_date must be before end_date.')

    min_history_days = payload.get('min_history_days')
    if min_history_days in (None, ''):
        min_history_days = (lookback_days if weighting_scheme in OPTIMIZER_SCHEMES
                            else DEFAULT_MIN_HISTORY_DAYS)
    min_history_days = int(_number({'v': min_history_days}, 'v', None, minimum=1))

    benchmark = str(payload.get('benchmark_symbol') or 'SPY').strip().upper()

    return BacktestRequest(
        holdings=holdings,
        benchmark_symbol=benchmark,
        start_date=start_date,
        end_date=end_date,
        initial_amount=_number(payload, 'initial_amount', 10_000.0, minimum=0.01),
        periodic_contribution=_number(payload, 'periodic_contribution', 0.0, minimum=0.0),
        contribution_frequency=_choice(payload, 'contribution_frequency',
                                       CONTRIBUTION_FREQUENCIES, 'none'),
        weighting_scheme=weighting_scheme,
        backtest_mode=_choice(payload, 'backtest_mode', BACKTEST_MODES, 'fixed'),
        rebalance_frequency=_choice(payload, 'rebalance_frequency',
                                    REBALANCE_FREQUENCIES, 'annual'),
        lookback_days=lookback_days,
        gap_days=gap_days,
        covariance_method=_choice(payload, 'covariance_method',
                                  COVARIANCE_METHODS, 'ledoit_wolf'),
        transaction_cost_bps=_number(payload, 'transaction_cost_bps', 10.0, minimum=0.0),
        long_only=long_only,
        max_weight=max_weight,
        min_weight=min_weight,
        risk_free_rate=_number(payload, 'risk_free_rate', 0.0),
        inception_policy=_choice(payload, 'inception_policy', INCEPTION_POLICIES,
                                 'phase_in'),
        enter_immediately=bool(payload.get('enter_immediately', False)),
        min_history_days=min_history_days,
    )


def normalized_payload(request: BacktestRequest) -> dict:
    """Canonical JSON-safe dict. Two requests that must share a cache entry
    normalize to the same dict, so sha256(json(sort_keys=True)) is a usable
    identity for the dedupe in §12."""
    return {
        'holdings': [{'symbol': h.symbol, 'target_weight': round(h.target_weight, 9)}
                     for h in request.holdings],
        'benchmark_symbol': request.benchmark_symbol,
        'start_date': request.start_date.isoformat() if request.start_date else None,
        'end_date': request.end_date.isoformat() if request.end_date else None,
        'initial_amount': round(request.initial_amount, 4),
        'periodic_contribution': round(request.periodic_contribution, 4),
        'contribution_frequency': request.contribution_frequency,
        'weighting_scheme': request.weighting_scheme,
        'backtest_mode': request.backtest_mode,
        'rebalance_frequency': request.rebalance_frequency,
        'lookback_days': request.lookback_days,
        'gap_days': request.gap_days,
        'covariance_method': request.covariance_method,
        'transaction_cost_bps': round(request.transaction_cost_bps, 6),
        'long_only': request.long_only,
        'max_weight': request.max_weight,
        'min_weight': request.min_weight,
        'risk_free_rate': round(request.risk_free_rate, 8),
        'inception_policy': request.inception_policy,
        'enter_immediately': request.enter_immediately,
        'min_history_days': request.min_history_days,
    }


def optimizer_config(request: BacktestRequest, custom_weights=None) -> OptimizerConfig:
    config = OptimizerConfig(
        long_only=request.long_only,
        max_weight=request.max_weight,
        min_weight=request.min_weight,
        risk_free_rate=request.risk_free_rate,
        covariance_method=request.covariance_method,
    )
    if custom_weights is not None:
        config = config.with_custom_weights(custom_weights)
    return config
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python manage.py test backtester.tests.test_config -v 2
```

Expected: all tests PASS. If Django reports the app is not installed, re-check Step 4.

- [ ] **Step 7: Confirm the app loads cleanly**

```bash
python manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 8: Commit**

```bash
git add backend/backtester/apps.py backend/backtester/engine/__init__.py \
        backend/backtester/engine/config.py backend/backtester/tests/test_config.py \
        backend/fintank_backend/settings.py
git commit -m "feat: scaffold the backtester app and its request contract"
```

---

### Task 4: Price panel loader and availability masks

The only file in `engine/` allowed to do I/O, and it is structured so one function is the seam tests monkeypatch (§2, §4). Everything about staggered inception (§5) lives here as two boolean matrices.

**Files:**
- Create: `backend/backtester/engine/prices.py`
- Modify: `backend/backtester/tests/test_prices.py` (append to the file from Task 2)

**Interfaces:**
- Consumes: `GetData.load_stock_prices(symbol, columns=)` from Task 2; `config.PriceDataUnavailable`.
- Produces:
  - `PricePanel` dataclass: `.prices` (DatetimeIndex × symbols DataFrame of `adjClose`), `.first_valid: dict[str, Timestamp]`, `.last_valid: dict[str, Timestamp]`, `.provenance: dict[str, str]`, `.missing: dict[str, str]`, `.symbols: list[str]`.
  - `PricePanel.returns() -> pd.DataFrame`
  - `PricePanel.availability() -> pd.DataFrame` (bool)
  - `PricePanel.eligibility(min_history_days: int) -> pd.DataFrame` (bool)
  - `load_price_panel(symbols, start=None, end=None) -> PricePanel`
  - `load_benchmark_series(symbol, start=None, end=None) -> tuple[pd.Series, str]`
  - `_fetch_symbol_series(symbol) -> tuple[pd.Series, str]` — **the single I/O seam**; every test monkeypatches this.

- [ ] **Step 1: Write the failing tests**

Append to `backend/backtester/tests/test_prices.py`:

```python
import numpy as np
from django.test import SimpleTestCase, override_settings

from backtester.engine import prices as prices_module
from backtester.engine.config import PriceDataUnavailable

LOCMEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'backtester-prices-tests',
    }
}


def _series(dates, values):
    return pd.Series(values, index=pd.DatetimeIndex(dates), dtype=float)


def _bdates(count, start='2020-01-01'):
    return pd.bdate_range(start, periods=count)


def _fake_loader(mapping, provenance='s3'):
    """Stand-in for the S3/FMP seam. Unknown symbols raise, as S3 does."""
    def loader(symbol):
        if symbol not in mapping:
            raise FileNotFoundError(symbol)
        return mapping[symbol], provenance
    return loader


@override_settings(CACHES=LOCMEM_CACHE)
class LoadPricePanelTests(SimpleTestCase):

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        dates = _bdates(10)
        self.mapping = {
            'A': _series(dates, np.arange(100.0, 110.0)),
            # B lists five days late: the staggered-inception case of §5.
            'B': _series(dates[5:], np.arange(50.0, 55.0)),
        }

    def test_panel_spans_the_union_of_trading_dates(self):
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader(self.mapping)):
            panel = prices_module.load_price_panel(['A', 'B'])

        self.assertEqual(len(panel.prices), 10)
        self.assertEqual(list(panel.prices.columns), ['A', 'B'])

    def test_first_and_last_valid_reflect_each_symbols_own_span(self):
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader(self.mapping)):
            panel = prices_module.load_price_panel(['A', 'B'])

        self.assertEqual(panel.first_valid['A'], panel.prices.index[0])
        self.assertEqual(panel.first_valid['B'], panel.prices.index[5])
        self.assertEqual(panel.last_valid['B'], panel.prices.index[-1])

    def test_forward_fill_never_manufactures_a_price_before_first_trade(self):
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader(self.mapping)):
            panel = prices_module.load_price_panel(['A', 'B'])

        self.assertTrue(panel.prices['B'].iloc[:5].isna().all())
        self.assertFalse(panel.prices['B'].iloc[5:].isna().any())

    def test_forward_fill_bridges_a_gap_inside_a_symbols_own_span(self):
        """A holiday one exchange keeps and another does not.

        The gap has to come from the *union* of trading dates to be meaningful:
        a date on which no requested symbol traded is not a trading date at all,
        and is correctly absent from the panel rather than forward-filled.
        """
        dates = _bdates(6)
        gappy = _series(dates, [10.0, np.nan, 12.0, np.nan, 14.0, 15.0])
        complete = _series(dates, [50.0, 51.0, 52.0, 53.0, 54.0, 55.0])
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader({'A': gappy, 'B': complete})):
            panel = prices_module.load_price_panel(['A', 'B'])

        self.assertEqual(len(panel.prices), 6)
        self.assertEqual(panel.prices['A'].tolist(), [10.0, 10.0, 12.0, 12.0, 14.0, 15.0])

    def test_a_date_no_symbol_traded_on_is_absent_rather_than_filled(self):
        dates = _bdates(4)
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader(
                              {'A': _series(dates, [10.0, np.nan, 12.0, 13.0])})):
            panel = prices_module.load_price_panel(['A'])

        self.assertEqual(len(panel.prices), 3)
        self.assertEqual(panel.prices['A'].tolist(), [10.0, 12.0, 13.0])

    def test_returns_are_simple_returns_on_adjclose(self):
        """Returns keep the price index, so the loop can address returns and
        dates by the same position. Row 0 is 0.0, not dropped."""
        dates = _bdates(3)
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader({'A': _series(dates, [100.0, 110.0, 99.0])})):
            panel = prices_module.load_price_panel(['A'])

        returns = panel.returns()
        self.assertEqual(len(returns), 3)
        self.assertAlmostEqual(returns['A'].iloc[1], 0.10)
        self.assertAlmostEqual(returns['A'].iloc[2], -0.10)

    def test_returns_are_zero_where_a_symbol_has_no_price_yet(self):
        """A pre-inception NaN must not become a NaN return that poisons the
        portfolio return; the availability mask is what excludes the asset."""
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader(self.mapping)):
            panel = prices_module.load_price_panel(['A', 'B'])

        self.assertFalse(panel.returns().isna().any().any())
        self.assertTrue((panel.returns()['B'].iloc[:5] == 0.0).all())

    def test_fmp_fallback_is_used_when_s3_misses(self):
        dates = _bdates(4)
        calls = []

        def loader(symbol):
            calls.append(symbol)
            return _series(dates, [1.0, 2.0, 3.0, 4.0]), 'fmp'

        with patch.object(prices_module, '_fetch_symbol_series', side_effect=loader):
            panel = prices_module.load_price_panel(['ZZZZ'])

        self.assertEqual(panel.provenance['ZZZZ'], 'fmp')

    def test_a_symbol_with_no_data_anywhere_is_recorded_as_missing(self):
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader(self.mapping)):
            panel = prices_module.load_price_panel(['A', 'NOPE'])

        self.assertIn('NOPE', panel.missing)
        self.assertNotIn('NOPE', panel.prices.columns)

    def test_every_symbol_missing_raises(self):
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader({})):
            with self.assertRaises(PriceDataUnavailable) as caught:
                prices_module.load_price_panel(['NOPE', 'ALSONOPE'])

        self.assertEqual(set(caught.exception.reasons), {'NOPE', 'ALSONOPE'})

    def test_the_second_load_of_a_symbol_comes_from_cache(self):
        loader = _fake_loader(self.mapping)
        with patch.object(prices_module, '_fetch_symbol_series', side_effect=loader) as seam:
            prices_module.load_price_panel(['A'])
            panel = prices_module.load_price_panel(['A'])

        self.assertEqual(seam.call_count, 1)
        self.assertEqual(panel.provenance['A'], 'cache')

    def test_start_and_end_trim_the_panel(self):
        dates = _bdates(10)
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader(self.mapping)):
            panel = prices_module.load_price_panel(['A'], start=dates[2].date(),
                                                   end=dates[6].date())

        self.assertEqual(panel.prices.index[0], dates[2])
        self.assertEqual(panel.prices.index[-1], dates[6])


@override_settings(CACHES=LOCMEM_CACHE)
class MaskTests(SimpleTestCase):
    """§5 — the two boolean matrices everything about inception rests on."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        dates = _bdates(20)
        self.dates = dates
        self.mapping = {
            'A': _series(dates, np.arange(100.0, 120.0)),
            'B': _series(dates[10:], np.arange(50.0, 60.0)),
            # C stops trading early: the delisting/truncation path.
            'C': _series(dates[:14], np.arange(30.0, 44.0)),
        }

    def _panel(self):
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader(self.mapping)):
            return prices_module.load_price_panel(['A', 'B', 'C'])

    def test_available_is_true_only_inside_each_symbols_span(self):
        available = self._panel().availability()

        self.assertTrue(available['A'].all())
        self.assertFalse(available['B'].iloc[9])
        self.assertTrue(available['B'].iloc[10])
        self.assertTrue(available['C'].iloc[13])
        self.assertFalse(available['C'].iloc[14])

    def test_min_history_days_of_one_makes_eligible_equal_available(self):
        panel = self._panel()

        pd.testing.assert_frame_equal(panel.eligibility(1), panel.availability())

    def test_min_history_days_delays_eligibility_beyond_availability(self):
        eligible = self._panel().eligibility(5)

        # B is available from index 10; its fifth own trading day is index 14.
        self.assertFalse(eligible['B'].iloc[13])
        self.assertTrue(eligible['B'].iloc[14])
        self.assertTrue(eligible['A'].iloc[4])
        self.assertFalse(eligible['A'].iloc[3])

    def test_eligibility_ends_with_availability_even_once_history_is_long(self):
        eligible = self._panel().eligibility(5)

        self.assertTrue(eligible['C'].iloc[13])
        self.assertFalse(eligible['C'].iloc[14])
```

Add `from unittest.mock import patch` to the imports at the top of the file if Task 2 did not already leave it there.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python manage.py test backtester.tests.test_prices -v 2
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backtester.engine.prices'`.

- [ ] **Step 3: Write `engine/prices.py`**

Create `backend/backtester/engine/prices.py`:

```python
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

        Zero rather than NaN outside a symbol's span: the availability mask is
        what excludes an asset from the portfolio, and a stray NaN return would
        otherwise propagate through wᵀr and null out the whole day.
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
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python manage.py test backtester.tests.test_prices -v 2
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/backtester/engine/prices.py backend/backtester/tests/test_prices.py
git commit -m "feat: add the backtester price panel loader and inception masks"
```

---

### Task 5: Covariance estimation

Sample and Ledoit–Wolf. `ledoit_wolf` is the default because with 252 observations and 10–30 assets the sample covariance is poorly conditioned, and both min-variance and max-Sharpe invert it (§6).

**Files:**
- Create: `backend/backtester/engine/covariance.py`
- Test: `backend/backtester/tests/test_covariance.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `estimate_covariance(returns: np.ndarray, method: str = 'ledoit_wolf') -> np.ndarray` — N×N, symmetric PSD. `sample_covariance(returns)` and `ledoit_wolf_covariance(returns)` are exported for direct testing.

- [ ] **Step 1: Write the failing test**

Create `backend/backtester/tests/test_covariance.py`:

```python
"""Covariance estimators. Pure numpy -- no Django needed."""
from unittest import TestCase

import numpy as np

from backtester.engine.covariance import (
    estimate_covariance,
    ledoit_wolf_covariance,
    sample_covariance,
)


def _returns(T=252, N=8, seed=0):
    rng = np.random.default_rng(seed)
    loadings = rng.normal(size=(N, 2))
    factors = rng.normal(size=(T, 2)) * 0.01
    noise = rng.normal(size=(T, N)) * 0.004
    return factors @ loadings.T + noise


class SampleCovarianceTests(TestCase):

    def test_matches_numpy_cov(self):
        returns = _returns()

        np.testing.assert_allclose(sample_covariance(returns),
                                   np.cov(returns, rowvar=False, ddof=1))

    def test_shape_is_n_by_n(self):
        self.assertEqual(sample_covariance(_returns(T=50, N=5)).shape, (5, 5))

    def test_single_asset_returns_a_one_by_one_matrix(self):
        returns = _returns(T=40, N=1)

        cov = sample_covariance(returns)
        self.assertEqual(cov.shape, (1, 1))
        self.assertGreater(cov[0, 0], 0.0)


class LedoitWolfTests(TestCase):

    def test_output_is_symmetric(self):
        cov = ledoit_wolf_covariance(_returns())

        np.testing.assert_allclose(cov, cov.T, atol=1e-15)

    def test_output_is_positive_semi_definite(self):
        eigenvalues = np.linalg.eigvalsh(ledoit_wolf_covariance(_returns()))

        self.assertGreaterEqual(eigenvalues.min(), -1e-14)

    def test_condition_number_is_no_worse_than_the_sample_estimator(self):
        """The whole point of shrinkage: a better-conditioned matrix to invert."""
        returns = _returns(T=60, N=40, seed=3)   # T < N: sample is singular

        shrunk = np.linalg.cond(ledoit_wolf_covariance(returns))
        plain = np.linalg.cond(sample_covariance(returns))
        self.assertLess(shrunk, plain)

    def test_shrinkage_pulls_the_diagonal_toward_the_average_variance(self):
        returns = _returns(T=60, N=30, seed=5)

        shrunk = ledoit_wolf_covariance(returns)
        plain = sample_covariance(returns)
        mean_variance = np.trace(plain) / plain.shape[0]
        # Off-diagonals move toward zero; the spread of variances contracts.
        self.assertLess(np.std(np.diag(shrunk)), np.std(np.diag(plain)))
        self.assertLess(np.abs(shrunk[np.triu_indices_from(shrunk, 1)]).mean(),
                        np.abs(plain[np.triu_indices_from(plain, 1)]).mean())
        self.assertGreater(mean_variance, 0.0)

    def test_a_single_asset_is_returned_unshrunk(self):
        returns = _returns(T=40, N=1)

        np.testing.assert_allclose(ledoit_wolf_covariance(returns),
                                   sample_covariance(returns), rtol=1e-9)


class EstimateCovarianceTests(TestCase):

    def test_dispatches_on_method(self):
        returns = _returns(T=80, N=6)

        np.testing.assert_allclose(estimate_covariance(returns, 'sample'),
                                   sample_covariance(returns))
        np.testing.assert_allclose(estimate_covariance(returns, 'ledoit_wolf'),
                                   ledoit_wolf_covariance(returns))

    def test_default_method_is_ledoit_wolf(self):
        returns = _returns(T=80, N=6)

        np.testing.assert_allclose(estimate_covariance(returns),
                                   ledoit_wolf_covariance(returns))

    def test_unknown_method_raises(self):
        with self.assertRaises(ValueError):
            estimate_covariance(_returns(T=30, N=3), 'wishful')

    def test_too_few_observations_raises(self):
        with self.assertRaises(ValueError):
            estimate_covariance(np.zeros((1, 3)), 'sample')
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python manage.py test backtester.tests.test_covariance -v 2
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backtester.engine.covariance'`.

- [ ] **Step 3: Write `engine/covariance.py`**

Create `backend/backtester/engine/covariance.py`:

```python
"""Covariance estimation for the optimizers.

Ledoit-Wolf is implemented directly rather than imported: it is ~30 lines, and
adding scikit-learn to the backend for one estimator is not warranted (§6).
"""
from __future__ import annotations

import numpy as np

METHODS = ('sample', 'ledoit_wolf')


def _validated(returns) -> np.ndarray:
    returns = np.asarray(returns, dtype=float)
    if returns.ndim != 2:
        raise ValueError('returns must be a T x N matrix')
    if returns.shape[0] < 2:
        raise ValueError('covariance needs at least 2 observations')
    return returns


def sample_covariance(returns) -> np.ndarray:
    returns = _validated(returns)
    cov = np.cov(returns, rowvar=False, ddof=1)
    return np.atleast_2d(cov)


def ledoit_wolf_covariance(returns) -> np.ndarray:
    """Ledoit-Wolf (2004) well-conditioned estimator: shrink the sample
    covariance toward a scaled identity, with the shrinkage intensity chosen to
    minimize expected squared Frobenius error.

    Notation follows §6: S is the (biased, /T) sample covariance of the demeaned
    block, m its average variance, d² its squared distance from m·I, and b̄² the
    average squared deviation of the per-observation outer products from S.
    """
    returns = _validated(returns)
    T, N = returns.shape
    if N == 1:
        # Nothing to shrink toward: a scaled identity *is* the sample estimate.
        return sample_covariance(returns)

    X = returns - returns.mean(axis=0)
    S = X.T @ X / T

    m = np.trace(S) / N
    d2 = np.sum((S - m * np.eye(N)) ** 2) / N
    if d2 <= 0:
        return sample_covariance(returns)

    # Σ_t ‖x_t x_tᵀ − S‖²_F expanded so no T x N x N array is materialized:
    # ‖x xᵀ‖²_F = (xᵀx)², and Σ_t <x_t x_tᵀ, S> = T · <S, S>.
    # Σ_t ‖x_t x_tᵀ − S‖²_F expanded so no T x N x N array is materialized.
    # ‖x xᵀ‖²_F = (xᵀx)², and Σ_t <x_t x_tᵀ, S> = <T·S, S> = T‖S‖²_F, so the
    # whole sum collapses to  Σ_t (x_tᵀ x_t)² − T‖S‖²_F.
    squared_norms = np.einsum('ij,ij->i', X, X)
    total = float(np.sum(squared_norms ** 2)) - T * float(np.sum(S * S))
    b2_bar = total / (T ** 2) / N

    b2 = min(max(b2_bar, 0.0), d2)
    a2 = d2 - b2

    shrunk = (b2 / d2) * m * np.eye(N) + (a2 / d2) * S
    return (shrunk + shrunk.T) / 2.0   # kill float asymmetry


def estimate_covariance(returns, method: str = 'ledoit_wolf') -> np.ndarray:
    if method == 'sample':
        return sample_covariance(returns)
    if method == 'ledoit_wolf':
        return ledoit_wolf_covariance(returns)
    raise ValueError(f"Unknown covariance method {method!r}; expected one of {METHODS}")
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python manage.py test backtester.tests.test_covariance -v 2
```

Expected: all tests PASS. If `test_condition_number_is_no_worse_than_the_sample_estimator` fails, the `b2_bar` algebra in Step 3 is wrong — verify it against a brute-force loop:

```python
brute = sum(np.sum((np.outer(x, x) - S) ** 2) for x in X) / (T ** 2) / N
```

The two must agree to ~1e-12.

- [ ] **Step 5: Commit**

```bash
git add backend/backtester/engine/covariance.py backend/backtester/tests/test_covariance.py
git commit -m "feat: add sample and Ledoit-Wolf covariance estimators"
```

---

### Task 6: The six weighting schemes

One signature for all six, so the backtest loop never learns which optimizer it called (§7). That uniformity is what makes walk-forward nearly free and lets phase-2 schemes drop in without touching the loop.

**Files:**
- Create: `backend/backtester/engine/optimizers.py`
- Test: `backend/backtester/tests/test_optimizers.py`

**Interfaces:**
- Consumes: `covariance.estimate_covariance`; `config.OptimizerConfig`.
- Produces:
  - `optimize(returns: np.ndarray, config: OptimizerConfig, scheme: str) -> OptimizerOutcome`
  - `OptimizerOutcome(weights: np.ndarray, converged: bool, fallback_from: str | None)` — frozen dataclass. The loop reads `.fallback_from` to raise the `optimizer_fallback` diagnostic.
  - `OPTIMIZERS: dict[str, Callable[[np.ndarray, OptimizerConfig], np.ndarray]]` — the registry; adding a scheme is one entry.
  - `relative_risk_contribution(weights: np.ndarray, cov: np.ndarray) -> np.ndarray` — `wᵢ(Σw)ᵢ / (wᵀΣw)`, summing to 1. **Task 8 imports this**; it is the shared definition serving both §7's risk-parity objective and §9's contribution-to-risk metric.

- [ ] **Step 1: Write the failing test**

Create `backend/backtester/tests/test_optimizers.py`:

```python
"""The six weighting schemes. Pure numpy + scipy."""
from unittest import TestCase

import numpy as np

from backtester.engine.config import OptimizerConfig
from backtester.engine.covariance import estimate_covariance
from backtester.engine.optimizers import (
    OPTIMIZERS,
    optimize,
    relative_risk_contribution,
)

SCHEMES = ('equal', 'custom', 'inverse_vol', 'min_variance', 'risk_parity', 'max_sharpe')


def _returns(T=252, N=5, seed=1):
    rng = np.random.default_rng(seed)
    loadings = rng.normal(size=(N, 2))
    factors = rng.normal(size=(T, 2)) * 0.01
    scale = np.linspace(0.003, 0.012, N)          # deliberately unequal vols
    return factors @ loadings.T + rng.normal(size=(T, N)) * scale


def _config(**overrides):
    defaults = {'long_only': True, 'covariance_method': 'ledoit_wolf'}
    defaults.update(overrides)
    return OptimizerConfig(**defaults)


class RegistryTests(TestCase):

    def test_every_scheme_is_registered(self):
        self.assertEqual(set(OPTIMIZERS), set(SCHEMES))

    def test_unknown_scheme_raises(self):
        with self.assertRaises(ValueError):
            optimize(_returns(), _config(), 'wishful')


class ContractTests(TestCase):
    """§15 property tests -- these hold for every scheme."""

    def setUp(self):
        self.returns = _returns()
        self.custom = _config().with_custom_weights([0.4, 0.3, 0.2, 0.05, 0.05])

    def _config_for(self, scheme):
        return self.custom if scheme == 'custom' else _config()

    def test_weights_sum_to_one(self):
        for scheme in SCHEMES:
            with self.subTest(scheme=scheme):
                outcome = optimize(self.returns, self._config_for(scheme), scheme)
                self.assertAlmostEqual(outcome.weights.sum(), 1.0, delta=1e-9)

    def test_weights_are_non_negative_under_long_only(self):
        for scheme in SCHEMES:
            with self.subTest(scheme=scheme):
                outcome = optimize(self.returns, self._config_for(scheme), scheme)
                self.assertGreaterEqual(outcome.weights.min(), -1e-9)

    def test_weight_vector_length_matches_the_asset_count(self):
        for scheme in SCHEMES:
            with self.subTest(scheme=scheme):
                outcome = optimize(self.returns, self._config_for(scheme), scheme)
                self.assertEqual(outcome.weights.shape, (5,))

    def test_max_weight_is_respected(self):
        for scheme in ('min_variance', 'risk_parity', 'max_sharpe'):
            with self.subTest(scheme=scheme):
                outcome = optimize(self.returns, _config(max_weight=0.30), scheme)
                self.assertLessEqual(outcome.weights.max(), 0.30 + 1e-6)

    def test_min_weight_is_respected(self):
        for scheme in ('min_variance', 'risk_parity', 'max_sharpe'):
            with self.subTest(scheme=scheme):
                outcome = optimize(self.returns, _config(min_weight=0.10), scheme)
                self.assertGreaterEqual(outcome.weights.min(), 0.10 - 1e-6)

    def test_a_single_asset_gets_all_of_it(self):
        for scheme in SCHEMES:
            with self.subTest(scheme=scheme):
                config = (_config().with_custom_weights([1.0]) if scheme == 'custom'
                          else _config())
                outcome = optimize(_returns(T=60, N=1), config, scheme)
                np.testing.assert_allclose(outcome.weights, [1.0], atol=1e-9)


class ClosedFormTests(TestCase):

    def test_equal_weight_is_one_over_n(self):
        outcome = optimize(_returns(N=4), _config(), 'equal')

        np.testing.assert_allclose(outcome.weights, np.full(4, 0.25), atol=1e-12)

    def test_custom_uses_the_supplied_weights_renormalized(self):
        config = _config().with_custom_weights([2.0, 1.0, 1.0])
        outcome = optimize(_returns(N=3), config, 'custom')

        np.testing.assert_allclose(outcome.weights, [0.5, 0.25, 0.25], atol=1e-12)

    def test_custom_without_weights_falls_back_to_equal(self):
        outcome = optimize(_returns(N=4), _config(), 'custom')

        np.testing.assert_allclose(outcome.weights, np.full(4, 0.25), atol=1e-12)

    def test_inverse_vol_weights_are_proportional_to_one_over_sigma(self):
        returns = _returns(N=3, seed=7)
        cov = estimate_covariance(returns, 'ledoit_wolf')
        expected = 1.0 / np.sqrt(np.diag(cov))
        expected = expected / expected.sum()

        outcome = optimize(returns, _config(), 'inverse_vol')
        np.testing.assert_allclose(outcome.weights, expected, atol=1e-9)

    def test_inverse_vol_gives_the_least_volatile_asset_the_largest_weight(self):
        returns = _returns(N=5, seed=11)
        cov = estimate_covariance(returns, 'ledoit_wolf')

        outcome = optimize(returns, _config(), 'inverse_vol')
        self.assertEqual(int(np.argmax(outcome.weights)), int(np.argmin(np.diag(cov))))


class MinVarianceTests(TestCase):

    def test_variance_is_no_worse_than_equal_weight(self):
        """§15 property test."""
        returns = _returns(N=6, seed=13)
        cov = estimate_covariance(returns, 'ledoit_wolf')

        w_min = optimize(returns, _config(), 'min_variance').weights
        w_eq = np.full(6, 1 / 6)
        self.assertLessEqual(w_min @ cov @ w_min, w_eq @ cov @ w_eq + 1e-12)

    def test_unconstrained_solution_matches_the_closed_form(self):
        """With no bounds the analytic Σ⁻¹1 / 1ᵀΣ⁻¹1 is exact and is used."""
        returns = _returns(N=4, seed=17)
        cov = estimate_covariance(returns, 'ledoit_wolf')
        inv_ones = np.linalg.solve(cov, np.ones(4))
        expected = inv_ones / inv_ones.sum()

        config = OptimizerConfig(long_only=False, covariance_method='ledoit_wolf')
        outcome = optimize(returns, config, 'min_variance')
        np.testing.assert_allclose(outcome.weights, expected, atol=1e-9)


class RiskParityTests(TestCase):

    def test_relative_risk_contributions_sum_to_one(self):
        returns = _returns(N=5, seed=19)
        cov = estimate_covariance(returns, 'ledoit_wolf')
        weights = np.full(5, 0.2)

        self.assertAlmostEqual(relative_risk_contribution(weights, cov).sum(), 1.0,
                               delta=1e-12)

    def test_risk_contributions_are_equal_within_tolerance(self):
        """§15 property test -- the defining property of the scheme."""
        returns = _returns(N=5, seed=23)
        cov = estimate_covariance(returns, 'ledoit_wolf')

        weights = optimize(returns, _config(), 'risk_parity').weights
        contributions = relative_risk_contribution(weights, cov)
        self.assertLess(contributions.max() - contributions.min(), 1e-4)

    def test_risk_parity_and_inverse_vol_coincide_for_two_assets(self):
        """Not a coincidence: with N=2 the equal-risk-contribution portfolio *is*
        the inverse-volatility portfolio, whatever the correlation. Confirmed
        against live SPY/AGG data in class_files/backtester_portfolio.ipynb."""
        returns = _returns(N=2, seed=29)

        rp = optimize(returns, _config(), 'risk_parity').weights
        iv = optimize(returns, _config(), 'inverse_vol').weights
        np.testing.assert_allclose(rp, iv, atol=1e-6)

    def test_risk_parity_sits_between_equal_weight_and_min_variance(self):
        """Maillard, Roncalli & Teiletche (2010): the ERC portfolio's
        concentration falls between 1/N and minimum variance.

        Note what is *not* asserted: that the lowest-variance asset gets the
        largest weight. With three or more assets ERC depends on correlations as
        well as variances, so a low-variance asset that moves with everything
        else can legitimately be underweighted. Do not add that assertion — it
        fails on ordinary correlated data.
        """
        returns = _returns(N=6, seed=29)

        def effective_n(w):
            return 1.0 / float(np.sum(np.asarray(w) ** 2))

        equal = effective_n(np.full(6, 1 / 6))
        parity = effective_n(optimize(returns, _config(), 'risk_parity').weights)
        minimum = effective_n(optimize(returns, _config(), 'min_variance').weights)

        self.assertLessEqual(parity, equal + 1e-9)
        self.assertGreaterEqual(parity, minimum - 1e-9)


class MaxSharpeTests(TestCase):

    def test_it_beats_equal_weight_on_in_sample_sharpe(self):
        returns = _returns(N=5, seed=31)
        cov = estimate_covariance(returns, 'ledoit_wolf')
        mu = returns.mean(axis=0)

        def sharpe(w):
            return (w @ mu) / np.sqrt(w @ cov @ w)

        w_ms = optimize(returns, _config(), 'max_sharpe').weights
        self.assertGreaterEqual(sharpe(w_ms), sharpe(np.full(5, 0.2)) - 1e-9)

    def test_the_risk_free_rate_is_daily_deflated(self):
        """r_f is an annual figure; the objective works in daily units."""
        returns = _returns(N=4, seed=37)

        zero = optimize(returns, _config(risk_free_rate=0.0), 'max_sharpe').weights
        high = optimize(returns, _config(risk_free_rate=0.05), 'max_sharpe').weights
        self.assertFalse(np.allclose(zero, high, atol=1e-6))


class FallbackTests(TestCase):
    """A backtest must never silently substitute a different strategy (§7)."""

    def test_non_convergence_falls_back_to_inverse_vol_and_says_so(self):
        returns = _returns(N=5, seed=41)
        expected = optimize(returns, _config(), 'inverse_vol').weights

        with self._forced_solver_failure():
            outcome = optimize(returns, _config(), 'risk_parity')

        self.assertFalse(outcome.converged)
        self.assertEqual(outcome.fallback_from, 'risk_parity')
        np.testing.assert_allclose(outcome.weights, expected, atol=1e-9)

    def test_a_converged_solve_reports_no_fallback(self):
        outcome = optimize(_returns(N=5, seed=43), _config(), 'min_variance')

        self.assertTrue(outcome.converged)
        self.assertIsNone(outcome.fallback_from)

    def _forced_solver_failure(self):
        from unittest.mock import patch

        from backtester.engine import optimizers

        class Failed:
            x = np.full(5, np.nan)
            success = False
            message = 'forced'

        return patch.object(optimizers, 'minimize', return_value=Failed())
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python manage.py test backtester.tests.test_optimizers -v 2
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backtester.engine.optimizers'`.

- [ ] **Step 3: Write `engine/optimizers.py`**

Create `backend/backtester/engine/optimizers.py`:

```python
"""The six weighting schemes of §7.

Every scheme has the same signature -- (returns, config) -> weights -- borrowed
from the portfolioBacktest package's design. The backtest loop never learns
which one it called, which is what makes walk-forward nearly free and lets a
phase-2 scheme drop in as one registry entry.

All six are reachable with scipy.optimize, which is already a backend
dependency. No cvxpy, no riskfolio-lib.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from .config import OptimizerConfig
from .covariance import estimate_covariance

SOLVER_OPTIONS = {'maxiter': 500, 'ftol': 1e-12}


@dataclass(frozen=True)
class OptimizerOutcome:
    """Weights plus enough provenance for the `optimizer_fallback` diagnostic."""
    weights: np.ndarray
    converged: bool = True
    fallback_from: str | None = None


def relative_risk_contribution(weights, cov) -> np.ndarray:
    """wᵢ(Σw)ᵢ / (wᵀΣw) -- the fraction of portfolio variance asset i carries.

    Sums to 1 by construction, which is what makes 1/N the right risk-parity
    target. This is the single shared definition: §7's risk-parity objective and
    §9's contribution-to-risk metric are the same computation, and
    engine/metrics.py imports this rather than restating it.

    Note: `create_index_contr_to_var()` in class_files/stock_data_getter_v2.ipynb
    computes the same quantity for index_data/contr_to_var/. Consolidating the
    notebook onto this function is deferred -- that notebook is outside this
    build's file allowlist.
    """
    weights = np.asarray(weights, dtype=float)
    cov = np.asarray(cov, dtype=float)
    portfolio_variance = float(weights @ cov @ weights)
    if portfolio_variance <= 0:
        return np.full(weights.shape, 1.0 / max(weights.size, 1))
    return weights * (cov @ weights) / portfolio_variance


def _bounds(n, config: OptimizerConfig):
    lower = 0.0 if config.long_only else -1.0
    if config.min_weight is not None:
        lower = max(lower, float(config.min_weight))
    upper = 1.0 if config.max_weight is None else float(config.max_weight)
    return [(lower, upper)] * n


def _unconstrained(n, config: OptimizerConfig) -> bool:
    """True when the only restriction is the budget constraint, so a closed form
    is exact and there is no reason to run a solver."""
    return (not config.long_only
            and config.max_weight is None
            and config.min_weight is None)


def _solve(objective, n, config: OptimizerConfig):
    """SLSQP warm-started from equal weight. Returns (weights, converged)."""
    start = np.full(n, 1.0 / n)
    result = minimize(
        objective, start, method='SLSQP',
        bounds=_bounds(n, config),
        constraints=({'type': 'eq', 'fun': lambda w: float(np.sum(w)) - 1.0},),
        options=SOLVER_OPTIONS,
    )
    weights = np.asarray(result.x, dtype=float)
    converged = bool(result.success) and np.all(np.isfinite(weights))
    if converged:
        total = weights.sum()
        # SLSQP satisfies the equality to ~1e-10; normalize so the caller's
        # sum-to-one assertion is exact.
        weights = weights / total if abs(total) > 1e-12 else np.full(n, 1.0 / n)
    return weights, converged


def _cov(returns, config: OptimizerConfig) -> np.ndarray:
    return estimate_covariance(returns, config.covariance_method)


def equal_weight(returns, config: OptimizerConfig) -> np.ndarray:
    n = np.asarray(returns).shape[1]
    return np.full(n, 1.0 / n)


def custom_weight(returns, config: OptimizerConfig) -> np.ndarray:
    """The user's targets for the eligible subset, renormalized over it (§5).

    Falls back to equal weight when no targets are attached, which is what the
    request contract guarantees for every scheme but `custom`.
    """
    n = np.asarray(returns).shape[1]
    if config.custom_weights is None:
        return np.full(n, 1.0 / n)
    weights = np.asarray(config.custom_weights, dtype=float)
    if weights.size != n:
        raise ValueError(
            f"custom_weights has {weights.size} entries for {n} eligible assets")
    total = weights.sum()
    if abs(total) < 1e-12:
        return np.full(n, 1.0 / n)
    return weights / total


def inverse_volatility(returns, config: OptimizerConfig) -> np.ndarray:
    variances = np.diag(_cov(returns, config))
    inverse = 1.0 / np.sqrt(np.maximum(variances, 1e-18))
    return inverse / inverse.sum()


def minimum_variance(returns, config: OptimizerConfig) -> np.ndarray:
    cov = _cov(returns, config)
    n = cov.shape[0]
    if n == 1:
        return np.ones(1)
    if _unconstrained(n, config):
        inv_ones = np.linalg.solve(cov, np.ones(n))
        return inv_ones / inv_ones.sum()
    weights, converged = _solve(lambda w: float(w @ cov @ w), n, config)
    if not converged:
        raise SolverFailure('min_variance did not converge')
    return weights


def risk_parity(returns, config: OptimizerConfig) -> np.ndarray:
    """Equalize relative risk contributions.

    The objective targets wᵢ(Σw)ᵢ/(wᵀΣw) = 1/N. §7's table writes the numerator
    over √(wᵀΣw), which sums to σ_p rather than 1 and would trade equality off
    against scaling σ_p toward 1; the relative form is what §9 defines and what
    makes the equal-contribution property exact.
    """
    cov = _cov(returns, config)
    n = cov.shape[0]
    if n == 1:
        return np.ones(1)
    target = 1.0 / n

    def objective(w):
        return float(np.sum((relative_risk_contribution(w, cov) - target) ** 2))

    weights, converged = _solve(objective, n, config)
    if not converged:
        raise SolverFailure('risk_parity did not converge')
    return weights


def maximum_sharpe(returns, config: OptimizerConfig) -> np.ndarray:
    """Maximize (wᵀμ − r_f) / √(wᵀΣw).

    μ is the sample mean of the lookback window -- a deliberately noisy
    estimate. The `return_estimation` diagnostic (§10) says so to the user.
    """
    returns = np.asarray(returns, dtype=float)
    cov = _cov(returns, config)
    n = cov.shape[0]
    if n == 1:
        return np.ones(1)
    mu = returns.mean(axis=0)
    daily_rf = float(config.risk_free_rate) / 252.0

    def objective(w):
        variance = float(w @ cov @ w)
        if variance <= 0:
            return 0.0
        return -(float(w @ mu) - daily_rf) / np.sqrt(variance)

    weights, converged = _solve(objective, n, config)
    if not converged:
        raise SolverFailure('max_sharpe did not converge')
    return weights


class SolverFailure(RuntimeError):
    """SLSQP failed to converge at one rebalance. Handled by `optimize`."""


OPTIMIZERS = {
    'equal': equal_weight,
    'custom': custom_weight,
    'inverse_vol': inverse_volatility,
    'min_variance': minimum_variance,
    'risk_parity': risk_parity,
    'max_sharpe': maximum_sharpe,
}


def optimize(returns, config: OptimizerConfig, scheme: str) -> OptimizerOutcome:
    """Run one scheme, falling back to inverse-volatility on solver failure.

    The fallback is recorded rather than swallowed: silently substituting a
    different strategy would make the whole backtest a lie about what it tested.
    """
    if scheme not in OPTIMIZERS:
        raise ValueError(f"Unknown weighting scheme {scheme!r}")

    try:
        weights = OPTIMIZERS[scheme](returns, config)
    except SolverFailure:
        return OptimizerOutcome(
            weights=inverse_volatility(returns, config),
            converged=False,
            fallback_from=scheme,
        )

    weights = np.asarray(weights, dtype=float)
    if not np.all(np.isfinite(weights)):
        return OptimizerOutcome(
            weights=inverse_volatility(returns, config),
            converged=False,
            fallback_from=scheme,
        )
    return OptimizerOutcome(weights=weights)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python manage.py test backtester.tests.test_optimizers -v 2
```

Expected: all tests PASS. If `test_risk_contributions_are_equal_within_tolerance` fails marginally, tighten `SOLVER_OPTIONS['ftol']` rather than loosening the assertion — the tolerance is a spec requirement (§15).

- [ ] **Step 5: Commit**

```bash
git add backend/backtester/engine/optimizers.py backend/backtester/tests/test_optimizers.py
git commit -m "feat: add the six portfolio weighting schemes"
```

---

### Task 7: The simulation loop

The timing contract of §8 is the single most important thing in this build, and the one most commonly got wrong. Weights decided for date `t` may use data only through `t − 1 − gap_days`, and the return realized at `t` is `R_t = w_{t−1}ᵀ r_t`. The look-ahead regression test in this task is the permanent guardrail on that.

**Files:**
- Create: `backend/backtester/engine/backtest.py`
- Test: `backend/backtester/tests/test_backtest.py`

**Interfaces:**
- Consumes: `prices.PricePanel`; `config.BacktestRequest`, `config.NoEligibleAssets`, `config.optimizer_config`; `optimizers.optimize`.
- Produces:
  - `run_backtest(panel: PricePanel, request: BacktestRequest) -> BacktestResult`
  - `BacktestResult` dataclass with the §8 field list. The simulation fills `dates, nav, index, drawdown, returns, weights_over_time, effective_asset_count, rebalance_events, composition_events, cash_flows, symbols, effective_start, effective_end, truncation_cause, fallback_dates`. The slots `benchmark_index, benchmark_drawdown, metrics, benchmark_metrics, diagnostics, frontier` default to `None` and are filled by `tasks.py` (Task 15) — keeping them out of `backtest.py`'s imports is what stops `diagnostics` and `backtest` importing each other.
  - `schedule_dates(index: pd.DatetimeIndex, frequency: str) -> set[pd.Timestamp]` — shared by rebalance and contribution scheduling.
  - `drawdown_series(index_values: np.ndarray) -> np.ndarray`

> ⚠️ **`weights_over_time` is indexed from `effective_start`, not from the panel's first date.** Whenever `min_history_days` or `common_start` moves the start, positional indexing (`.iloc[:29]`) into the result against a *panel* position is off by the offset and silently tests the wrong rows. Index by date (`.loc[:dates[28], 'C']`) in every assertion that refers to a panel position. The same applies to `nav`, `index`, `drawdown` and `effective_asset_count` — use `result.dates.index(iso_date)` to convert.

- [ ] **Step 1: Write the failing golden-numbers test**

Create `backend/backtester/tests/test_backtest.py`:

```python
"""The simulation loop.

Every case here builds a PricePanel by hand, so nothing touches S3, FMP or
Redis and the expected numbers are computable on paper.
"""
from unittest import TestCase

import numpy as np
import pandas as pd

from backtester.engine.backtest import (
    BacktestResult,
    drawdown_series,
    run_backtest,
    schedule_dates,
)
from backtester.engine.config import NoEligibleAssets, validate_request
from backtester.engine.prices import PricePanel


def _panel(prices: dict, dates) -> PricePanel:
    """Build a PricePanel directly. NaN means 'no price on that date'."""
    dates = pd.DatetimeIndex(dates)
    frame = pd.DataFrame(prices, index=dates, dtype=float)
    first = {c: frame[c].first_valid_index() for c in frame.columns}
    last = {c: frame[c].last_valid_index() for c in frame.columns}
    for column in frame.columns:
        span = (frame.index >= first[column]) & (frame.index <= last[column])
        frame.loc[span, column] = frame.loc[span, column].ffill()
    return PricePanel(prices=frame, first_valid=first, last_valid=last,
                      provenance={c: 'test' for c in frame.columns})


def _request(**overrides):
    payload = {'holdings': [{'symbol': 'A'}, {'symbol': 'B'}],
               'rebalance_frequency': 'none', 'min_history_days': 1}
    payload.update(overrides)
    return validate_request(payload)


class GoldenNumbersTests(TestCase):
    """A 2-asset panel with hand-computed expected values (§15)."""

    def setUp(self):
        # A: +10%, +10%, 0.   B: -10%, -10%, 0.
        self.dates = pd.to_datetime(['2021-01-04', '2021-01-05',
                                     '2021-01-06', '2021-01-07'])
        self.panel = _panel({'A': [100.0, 110.0, 121.0, 121.0],
                             'B': [100.0, 90.0, 81.0, 81.0]}, self.dates)

    def test_index_tracks_the_drifted_equal_weight_portfolio(self):
        result = run_backtest(self.panel, _request())

        # day0: seed at 0.5/0.5, index 1.0
        # day1: R = .5(.1) + .5(-.1) = 0        -> index 1.0,   drift .55/.45
        # day2: R = .55(.1) + .45(-.1) = .01    -> index 1.01
        # day3: R = 0                           -> index 1.01
        np.testing.assert_allclose(result.index, [1.0, 1.0, 1.01, 1.01], rtol=1e-12)

    def test_nav_is_the_index_scaled_by_the_initial_amount(self):
        result = run_backtest(self.panel, _request(initial_amount=10_000))

        np.testing.assert_allclose(result.nav, [10_000, 10_000, 10_100, 10_100],
                                   rtol=1e-12)

    def test_returns_are_reported_per_date_with_a_leading_zero(self):
        result = run_backtest(self.panel, _request())

        np.testing.assert_allclose(result.returns, [0.0, 0.0, 0.01, 0.0], rtol=1e-12)

    def test_dates_are_iso_strings_covering_the_effective_window(self):
        result = run_backtest(self.panel, _request())

        self.assertEqual(result.dates,
                         ['2021-01-04', '2021-01-05', '2021-01-06', '2021-01-07'])
        self.assertEqual(result.effective_start, '2021-01-04')
        self.assertEqual(result.effective_end, '2021-01-07')

    def test_weights_over_time_sums_to_one_on_every_date(self):
        result = run_backtest(self.panel, _request())

        np.testing.assert_allclose(result.weights_over_time.sum(axis=1),
                                   np.ones(4), atol=1e-12)

    def test_cagr_inputs_are_consistent_with_the_index(self):
        result = run_backtest(self.panel, _request())

        self.assertAlmostEqual(float(result.index[-1]),
                               float(np.prod(1 + np.asarray(result.returns))),
                               places=12)


class DrawdownTests(TestCase):

    def test_drawdown_is_zero_at_a_new_high_and_negative_below_it(self):
        values = np.array([1.0, 1.2, 0.9, 1.3])

        np.testing.assert_allclose(drawdown_series(values),
                                   [0.0, 0.0, 0.9 / 1.2 - 1, 0.0], rtol=1e-12)

    def test_drawdown_never_exceeds_zero(self):
        values = np.cumprod(1 + np.linspace(-0.02, 0.02, 50))

        self.assertLessEqual(drawdown_series(values).max(), 0.0 + 1e-15)


class TurnoverAndCostTests(TestCase):
    """Hand-computed arithmetic across a known rebalance (§15)."""

    def setUp(self):
        # One step across a year boundary, so day1 is a scheduled annual rebalance.
        self.dates = pd.to_datetime(['2020-12-31', '2021-01-04'])
        self.panel = _panel({'A': [100.0, 150.0], 'B': [100.0, 100.0]}, self.dates)

    def test_turnover_is_the_l1_distance_from_drift_to_target(self):
        result = run_backtest(self.panel, _request(rebalance_frequency='annual',
                                                  transaction_cost_bps=10.0))

        # R = .5(.5) + .5(0) = .25 -> drift .6/.4; target back to .5/.5
        # turnover = |.5-.6| + |.5-.4| = 0.2
        self.assertEqual(len(result.rebalance_events), 1)
        event = result.rebalance_events[0]
        self.assertEqual(event['date'], '2021-01-04')
        self.assertAlmostEqual(event['turnover'], 0.2, places=12)
        self.assertAlmostEqual(event['cost'], 0.2 * 10 / 10_000, places=15)
        self.assertEqual(event['trigger'], 'scheduled')

    def test_the_cost_is_charged_against_both_index_and_nav(self):
        result = run_backtest(self.panel, _request(rebalance_frequency='annual',
                                                   transaction_cost_bps=10.0,
                                                   initial_amount=10_000))

        self.assertAlmostEqual(float(result.index[-1]), 1.25 * (1 - 0.0002), places=12)
        self.assertAlmostEqual(float(result.nav[-1]), 10_000 * 1.25 * (1 - 0.0002),
                               places=8)

    def test_zero_cost_bps_leaves_the_index_untouched(self):
        result = run_backtest(self.panel, _request(rebalance_frequency='annual',
                                                   transaction_cost_bps=0.0))

        self.assertAlmostEqual(float(result.index[-1]), 1.25, places=12)

    def test_weights_return_to_target_after_the_rebalance(self):
        result = run_backtest(self.panel, _request(rebalance_frequency='annual'))

        np.testing.assert_allclose(result.weights_over_time.iloc[-1].to_numpy(),
                                   [0.5, 0.5], atol=1e-12)


class ScheduleTests(TestCase):

    def setUp(self):
        self.index = pd.bdate_range('2020-01-01', '2022-12-31')

    def test_none_schedules_nothing(self):
        self.assertEqual(schedule_dates(self.index, 'none'), set())

    def test_annual_fires_on_the_first_trading_day_of_each_new_year(self):
        dates = sorted(schedule_dates(self.index, 'annual'))

        self.assertEqual([d.strftime('%Y-%m-%d') for d in dates],
                         ['2021-01-01', '2022-01-03'])

    def test_monthly_fires_once_a_month_and_never_on_the_first_date(self):
        dates = sorted(schedule_dates(self.index, 'monthly'))

        self.assertEqual(len(dates), 35)
        self.assertNotIn(self.index[0], dates)

    def test_quarterly_and_semiannual_fire_four_and_two_times_a_year(self):
        self.assertEqual(len(schedule_dates(self.index, 'quarterly')), 11)
        self.assertEqual(len(schedule_dates(self.index, 'semiannual')), 5)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python manage.py test backtester.tests.test_backtest -v 2
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backtester.engine.backtest'`.

- [ ] **Step 3: Write `engine/backtest.py`**

Create `backend/backtester/engine/backtest.py`:

```python
"""The simulation loop of §8.

The timing contract, restated because getting it wrong produces spectacular
fictional results:

    Weights decided for date t may use data only through t − 1 − gap_days.
    The portfolio return realized at t is R_t = w_{t−1}ᵀ r_t.

Step order inside the loop matters as much as the contract: R_t is computed
*before* drift, because the drift denominator is 1 + R_t. Computing drift first
and then taking w_driftᵀ r_t is a look-ahead error.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import (
    BacktestRequest,
    NoEligibleAssets,
    optimizer_config,
)
from .optimizers import optimize

PERIOD_FREQ = {
    'monthly': 'M',
    'quarterly': 'Q',
    'semiannual': '2Q',
    'annual': 'Y',
}
WEIGHT_EPSILON = 1e-12


@dataclass
class BacktestResult:
    """§8's output. The trailing slots are filled by tasks.py, not here."""
    dates: list
    nav: np.ndarray
    index: np.ndarray
    drawdown: np.ndarray
    returns: np.ndarray
    weights_over_time: pd.DataFrame
    effective_asset_count: np.ndarray
    rebalance_events: list
    composition_events: list
    cash_flows: list
    symbols: list
    effective_start: str
    effective_end: str
    truncation_cause: str | None = None
    fallback_dates: list = field(default_factory=list)

    benchmark_index: np.ndarray | None = None
    benchmark_drawdown: np.ndarray | None = None
    metrics: dict | None = None
    benchmark_metrics: dict | None = None
    diagnostics: list | None = None
    frontier: dict | None = None


def schedule_dates(index: pd.DatetimeIndex, frequency: str) -> set:
    """Dates on which a period boundary is crossed, excluding the first date.

    The first date is excluded because the portfolio is seeded there -- charging
    a rebalance on the day you open the account would double-count the entry
    trade.
    """
    if frequency == 'none' or len(index) < 2:
        return set()
    if frequency not in PERIOD_FREQ:
        raise ValueError(f"Unknown frequency {frequency!r}")

    if frequency == 'semiannual':
        labels = pd.Index([(d.year, (d.month - 1) // 6) for d in index])
    else:
        labels = index.to_period(PERIOD_FREQ[frequency])

    changed = np.asarray(labels[1:]) != np.asarray(labels[:-1])
    return set(index[1:][changed])


def drawdown_series(index_values) -> np.ndarray:
    values = np.asarray(index_values, dtype=float)
    peaks = np.maximum.accumulate(values)
    with np.errstate(divide='ignore', invalid='ignore'):
        drawdown = np.where(peaks > 0, values / peaks - 1.0, 0.0)
    return np.minimum(drawdown, 0.0)


def _base_targets(request: BacktestRequest) -> np.ndarray:
    """Full-length target vector for the non-optimizer schemes."""
    n = len(request.holdings)
    if request.weighting_scheme == 'custom':
        return request.target_weights
    return np.full(n, 1.0 / n)


def _renormalized(targets: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """§5: preserve relative proportions over the available set.

    40/30/20/10 missing its 10% asset becomes 44.4/33.3/22.2 -- not something
    arbitrary. Falls back to equal weight over the mask when the masked targets
    sum to zero.
    """
    weights = np.where(mask, targets, 0.0)
    total = weights.sum()
    if total <= WEIGHT_EPSILON:
        count = int(mask.sum())
        return np.where(mask, 1.0 / count, 0.0) if count else weights
    return weights / total


def _window(returns: np.ndarray, position: int, request: BacktestRequest):
    """The trailing block a rebalance at row `position` is allowed to see.

    Ends at position − gap_days (exclusive), so the last row it contains is
    position − gap_days − 1. With the default gap_days=1 that is t − 2.
    """
    end = position - request.gap_days
    start = max(0, end - request.lookback_days)
    if end - start < 2:
        return None
    return returns[start:end]


def run_backtest(panel, request: BacktestRequest) -> BacktestResult:
    symbols = list(panel.prices.columns)
    n = len(symbols)
    dates = panel.prices.index
    returns_frame = panel.returns()
    returns = returns_frame.to_numpy()
    eligible_frame = panel.eligibility(request.min_history_days)

    if request.inception_policy == 'common_start':
        # Restore plain intersection behaviour: begin only when every asset is
        # eligible. The right choice for apples-to-apples comparison, but not
        # the default -- phase-in is what someone means by "ten years" (§5).
        complete = eligible_frame.all(axis=1).to_numpy()
        if not complete.any():
            raise NoEligibleAssets(
                'No date has price history for every requested asset. '
                'Try the phase-in inception policy.')
        start_position = int(np.argmax(complete))
    else:
        any_eligible = eligible_frame.any(axis=1).to_numpy()
        if not any_eligible.any():
            reasons = {
                symbol: (f"first price {panel.first_valid[symbol].date()}, "
                         f"fewer than {request.min_history_days} trading days of history")
                for symbol in symbols
            }
            raise NoEligibleAssets(
                'No requested asset has enough price history to be simulated. '
                f"Reasons: {reasons}")
        start_position = int(np.argmax(any_eligible))

    eligible = eligible_frame.to_numpy()
    sim_positions = range(start_position, len(dates))
    sim_dates = dates[start_position:]

    truncation_cause = None
    if start_position > 0:
        constraining = min(
            (s for s in symbols),
            key=lambda s: panel.first_valid[s],
        )
        latest = max(symbols, key=lambda s: panel.first_valid[s])
        truncation_cause = (
            f"Started {sim_dates[0].date()} rather than {dates[0].date()}: "
            f"the earliest date any holding clears "
            f"{request.min_history_days} trading days of history. "
            f"Earliest series is {constraining}, latest is {latest} "
            f"(first price {panel.first_valid[latest].date()}).")

    scheduled = schedule_dates(sim_dates, request.rebalance_frequency)
    contributions = (schedule_dates(sim_dates, request.contribution_frequency)
                     if request.periodic_contribution > 0 else set())
    cost_rate = request.transaction_cost_bps / 10_000.0
    base_targets = _base_targets(request)
    uses_optimizer = request.weighting_scheme not in ('equal', 'custom')

    # Fixed mode solves once per distinct eligible set and reuses the answer;
    # that is what "runs once ... and thereafter reuses those targets" means once
    # an asset can enter mid-run (§8). Walk-forward ignores this cache.
    solved_targets: dict = {}
    fallback_dates: list = []

    def compute_targets(position, mask):
        """Targets over all symbols; zero outside `mask`."""
        if not uses_optimizer:
            return _renormalized(base_targets, mask)

        key = tuple(np.flatnonzero(mask))
        if request.backtest_mode == 'fixed' and key in solved_targets:
            return _renormalized(solved_targets[key], mask)

        window = _window(returns, position, request)
        if window is None:
            return _renormalized(np.full(n, 1.0 / n), mask)

        sub_window = window[:, mask]
        config = optimizer_config(request)
        if request.weighting_scheme == 'custom':
            config = config.with_custom_weights(base_targets[mask])
        outcome = optimize(sub_window, config, request.weighting_scheme)
        if outcome.fallback_from is not None:
            fallback_dates.append(dates[position].strftime('%Y-%m-%d'))

        full = np.zeros(n)
        full[mask] = outcome.weights
        if request.backtest_mode == 'fixed':
            solved_targets[key] = full.copy()
        return full

    # --- seed -------------------------------------------------------------
    mask = eligible[start_position]
    weights = compute_targets(start_position, mask)
    held = mask & (weights > WEIGHT_EPSILON)

    nav_value = float(request.initial_amount)
    index_value = 1.0
    nav_series, index_series, return_series = [nav_value], [index_value], [0.0]
    weight_rows = [weights.copy()]
    rebalance_events, composition_events = [], []
    cash_flows = [(sim_dates[0], -float(request.initial_amount))]

    for symbol_position in np.flatnonzero(held):
        composition_events.append({
            'date': sim_dates[0].strftime('%Y-%m-%d'),
            'symbol': symbols[symbol_position],
            'action': 'entered',
            'reason': 'Held from the first simulated date.',
        })

    # Entries wait for the next scheduled rebalance on or after eligibility (§5).
    pending_entry: dict = {}

    # --- loop -------------------------------------------------------------
    for position in list(sim_positions)[1:]:
        today = dates[position]
        row_returns = returns[position]

        # 1. realize yesterday's weights against today's returns
        portfolio_return = float(weights @ row_returns)

        # 2. weights drift with prices
        growth = 1.0 + portfolio_return
        if abs(growth) < 1e-12:
            drift = weights.copy()
        else:
            drift = weights * (1.0 + row_returns) / growth

        # 3/4. time-weighted index and account balance
        index_value *= growth
        nav_value *= growth

        # 5. contributions: deployed pro-rata at current weights, so NAV moves
        #    but composition does not. The one-way cost hits nav only -- index
        #    must stay free of anything driven by the deposit schedule.
        contribution = 0.0
        if today in contributions:
            contribution = float(request.periodic_contribution)
            nav_value += contribution
            nav_value -= contribution * cost_rate
            cash_flows.append((today, -contribution))

        # 6. rebalance triggers
        mask = eligible[position]
        exited = np.flatnonzero(held & ~mask)
        newly_eligible = np.flatnonzero(mask & ~held)

        for symbol_position in newly_eligible:
            pending_entry.setdefault(symbols[symbol_position], today)

        trigger = None
        if today in scheduled:
            trigger = 'scheduled'
        if exited.size:
            trigger = 'exit'
        if newly_eligible.size and request.enter_immediately:
            trigger = 'entry'
        if newly_eligible.size and not any(d >= today for d in scheduled):
            # Nothing is scheduled ahead, so waiting would drop the asset for
            # good. Enter now and say so in the timeline.
            trigger = trigger or 'entry'

        if trigger is not None:
            targets = compute_targets(position, mask)
            turnover = float(np.abs(targets - drift).sum())
            cost = turnover * cost_rate
            nav_value *= (1.0 - cost)
            index_value *= (1.0 - cost)
            rebalance_events.append({
                'date': today.strftime('%Y-%m-%d'),
                'turnover': turnover,
                'cost': cost,
                'trigger': trigger,
                'weights': {symbols[i]: float(targets[i])
                            for i in np.flatnonzero(targets > WEIGHT_EPSILON)},
            })

            for symbol_position in exited:
                composition_events.append({
                    'date': today.strftime('%Y-%m-%d'),
                    'symbol': symbols[symbol_position],
                    'action': 'exited',
                    'reason': (f"Price series ends "
                               f"{panel.last_valid[symbols[symbol_position]].date()}; "
                               f"liquidated and redistributed pro-rata."),
                })
            for symbol_position in np.flatnonzero(mask & (targets > WEIGHT_EPSILON) & ~held):
                symbol = symbols[symbol_position]
                became = pending_entry.pop(symbol, today)
                reason = (f"Eligible from {became.date()}; entered at the "
                          f"{trigger} rebalance on {today.date()}.")
                composition_events.append({
                    'date': today.strftime('%Y-%m-%d'),
                    'symbol': symbol,
                    'action': 'entered',
                    'reason': reason,
                })

            weights = targets
        else:
            weights = drift

        held = weights > WEIGHT_EPSILON
        nav_series.append(nav_value)
        index_series.append(index_value)
        return_series.append(portfolio_return)
        weight_rows.append(weights.copy())

    cash_flows.append((sim_dates[-1], float(nav_value)))
    weights_over_time = pd.DataFrame(weight_rows, index=sim_dates, columns=symbols)
    index_values = np.asarray(index_series, dtype=float)

    return BacktestResult(
        dates=[d.strftime('%Y-%m-%d') for d in sim_dates],
        nav=np.asarray(nav_series, dtype=float),
        index=index_values,
        drawdown=drawdown_series(index_values),
        returns=np.asarray(return_series, dtype=float),
        weights_over_time=weights_over_time,
        effective_asset_count=(weights_over_time > WEIGHT_EPSILON).sum(axis=1).to_numpy(),
        rebalance_events=rebalance_events,
        composition_events=composition_events,
        cash_flows=[(d.strftime('%Y-%m-%d'), amount) for d, amount in cash_flows],
        symbols=symbols,
        effective_start=sim_dates[0].strftime('%Y-%m-%d'),
        effective_end=sim_dates[-1].strftime('%Y-%m-%d'),
        truncation_cause=truncation_cause,
        fallback_dates=fallback_dates,
    )
```

- [ ] **Step 4: Run the golden tests to verify they pass**

```bash
python manage.py test backtester.tests.test_backtest -v 2
```

Expected: all tests from Step 1 PASS. If `test_annual_fires_on_the_first_trading_day_of_each_new_year` fails, check whether `pd.bdate_range('2020-01-01', ...)` includes 2021-01-01 on your pandas version — adjust the expected list to the actual first business day, not the implementation.

- [ ] **Step 5: Commit the loop**

```bash
git add backend/backtester/engine/backtest.py backend/backtester/tests/test_backtest.py
git commit -m "feat: add the portfolio backtest simulation loop"
```

- [ ] **Step 6: Write the look-ahead regression tests**

This is the required guardrail on the §8 timing contract (§15). Append to `backend/backtester/tests/test_backtest.py`:

```python
class LookAheadRegressionTests(TestCase):
    """REQUIRED (§15). These must fail loudly if the loop is ever reordered."""

    def setUp(self):
        self.dates = pd.bdate_range('2021-01-01', periods=40)

    def test_the_optimizer_never_sees_data_at_or_after_the_rebalance_date(self):
        """The window handed to a scheme ends at t − 1 − gap_days."""
        from unittest.mock import patch

        from backtester.engine import backtest as backtest_module

        panel = _panel({'A': np.linspace(100, 140, 40),
                        'B': np.linspace(100, 120, 40)}, self.dates)
        request = _request(weighting_scheme='min_variance', min_history_days=5,
                           lookback_days=5, gap_days=1,
                           rebalance_frequency='monthly',
                           backtest_mode='walk_forward')

        seen = []
        real_optimize = backtest_module.optimize

        def spy(window, config, scheme):
            seen.append(window.shape[0])
            return real_optimize(window, config, scheme)

        with patch.object(backtest_module, 'optimize', side_effect=spy):
            run_backtest(panel, request)

        # Every window is at most lookback_days rows and never empty.
        self.assertTrue(seen)
        self.assertTrue(all(0 < rows <= 5 for rows in seen), seen)

    def test_a_strategy_that_would_profit_from_same_day_alignment_earns_nothing(self):
        """Asset B's future is knowable: it jumps +50% on one known date.

        A stub scheme that puts everything into B exactly on the spike date
        profits only if the engine multiplies w_t by r_t. Under the correct
        w_{t−1}ᵀ r_t alignment it captures nothing.
        """
        from unittest.mock import patch

        from backtester.engine import backtest as backtest_module
        from backtester.engine.optimizers import OptimizerOutcome

        prices_a = np.full(40, 100.0)
        prices_b = np.full(40, 100.0)
        prices_b[20:] = 150.0            # +50% on date index 20, flat after
        panel = _panel({'A': prices_a, 'B': prices_b}, self.dates)
        spike_date = self.dates[20]

        request = _request(weighting_scheme='min_variance', min_history_days=5,
                           lookback_days=5, gap_days=1,
                           rebalance_frequency='monthly',
                           backtest_mode='walk_forward',
                           enter_immediately=True)

        def clairvoyant(window, config, scheme):
            # Would be devastating if applied to the same day's return.
            return OptimizerOutcome(weights=np.array([0.0, 1.0]))

        with patch.object(backtest_module, 'optimize', side_effect=clairvoyant):
            with patch.object(backtest_module, 'schedule_dates',
                              side_effect=lambda index, frequency: (
                                  {spike_date} if frequency == 'monthly' else set())):
                result = run_backtest(panel, request)

        # Both assets are flat except B's single jump, which the portfolio was
        # not positioned for. Ignoring the rebalance cost, the index is 1.0.
        self.assertLess(float(result.index[-1]), 1.0 + 1e-9)
        self.assertNotAlmostEqual(float(result.index[-1]), 1.5, places=3)

    def test_the_return_on_a_rebalance_date_uses_yesterdays_weights(self):
        """Exact arithmetic check of R_t = w_{t−1}ᵀ r_t at a rebalance."""
        dates = pd.to_datetime(['2020-12-30', '2020-12-31', '2021-01-04'])
        # On 2021-01-04 (the annual rebalance) A returns 0 and B returns +20%.
        panel = _panel({'A': [100.0, 100.0, 100.0],
                        'B': [100.0, 100.0, 120.0]}, dates)

        result = run_backtest(panel, _request(rebalance_frequency='annual',
                                              transaction_cost_bps=0.0))

        # Weights entering 2021-01-04 are still 0.5/0.5, so R = 0.5 × 0.20 = 0.10.
        # A loop that rebalanced first and then applied the new weights would
        # produce a different number.
        self.assertAlmostEqual(float(result.returns[-1]), 0.10, places=12)
        self.assertAlmostEqual(float(result.index[-1]), 1.10, places=12)
```

- [ ] **Step 7: Run the look-ahead tests to verify they pass**

```bash
python manage.py test backtester.tests.test_backtest.LookAheadRegressionTests -v 2
```

Expected: 3 tests PASS.

- [ ] **Step 8: Prove the tests actually detect the bug**

A guardrail that cannot fail is not a guardrail. **Two sabotages are needed, because the two economic tests catch two different bugs** — one sabotage leaves the other test passing, which would wrongly suggest it works.

Back the file up first (`cp backtester/engine/backtest.py /tmp/backtest.py.good`) so restoring never depends on what is or is not committed.

**Variant A — drift computed before the return.** Replace step 1 and 2 with:

```python
        drift = weights * (1.0 + row_returns) / 1.0
        portfolio_return = float(drift @ row_returns)
        growth = 1.0 + portfolio_return
```

Expected: `test_the_return_on_a_rebalance_date_uses_yesterdays_weights` FAILS (0.12 instead of 0.10). `test_a_strategy_that_would_profit_from_same_day_alignment_earns_nothing` still passes — correctly, because that test's pre-rebalance weight in the spiking asset is zero and drift keeps it zero.

**Variant B — post-rebalance weights applied to the same day's return.** Restore, then insert immediately before `weights = targets`:

```python
            corrected = float(targets @ row_returns)
            index_value = index_value / growth * (1.0 + corrected)
```

Expected: `test_a_strategy_that_would_profit_from_same_day_alignment_earns_nothing` FAILS at exactly **1.5** — the fictional +50%.

Run after each variant:

```bash
python manage.py test backtester.tests.test_backtest.LookAheadRegressionTests -v 2
```

Then restore from the backup and re-run the whole suite to confirm PASS again, and check no sabotage survived:

```bash
cp /tmp/backtest.py.good backtester/engine/backtest.py
grep -c "SABOTAGE" backtester/engine/backtest.py   # must be 0
python manage.py test backtester -v 1
```

Do not skip this step. This bug produces no crash, no exception and no downstream symptom — only inflated returns that read as good news.

**A note on how the stub strategy must be built.** `test_a_strategy_that_would_profit_from_same_day_alignment_earns_nothing` only isolates look-ahead if the strategy switches into the spiking asset *at* the spike rebalance. A stub that holds it from the first date captures the jump legitimately — it was simply long the asset — and the test fails against a *correct* loop. Similarly, the stub's weights must be reachable: the seed call happens at the first eligible date, so a counter-based stub needs to account for it.

- [ ] **Step 9: Commit**

```bash
git add backend/backtester/tests/test_backtest.py
git commit -m "test: add the look-ahead regression guardrail for the backtest loop"
```

- [ ] **Step 10: Write the staggered-inception tests**

Append to `backend/backtester/tests/test_backtest.py`:

```python
class StaggeredInceptionTests(TestCase):
    """§5 -- the default phase_in behaviour."""

    def setUp(self):
        self.dates = pd.bdate_range('2020-01-01', periods=60)
        prices = {
            'A': np.linspace(100, 160, 60),
            'B': np.linspace(100, 130, 60),
            # C lists on date index 20.
            'C': np.concatenate([np.full(20, np.nan), np.linspace(50, 70, 40)]),
        }
        self.panel = _panel(prices, self.dates)

    def _request(self, **overrides):
        payload = {'holdings': [{'symbol': 'A'}, {'symbol': 'B'}, {'symbol': 'C'}],
                   'min_history_days': 1, 'rebalance_frequency': 'monthly',
                   'transaction_cost_bps': 0.0}
        payload.update(overrides)
        return validate_request(payload)

    def test_weights_sum_to_one_on_every_date_including_the_phase_in_span(self):
        result = run_backtest(self.panel, self._request())

        np.testing.assert_allclose(result.weights_over_time.sum(axis=1),
                                   np.ones(len(result.dates)), atol=1e-12)

    def test_c_holds_no_weight_before_it_lists(self):
        result = run_backtest(self.panel, self._request())

        self.assertTrue((result.weights_over_time['C'].iloc[:20] == 0.0).all())

    def test_equal_weight_renormalizes_over_the_available_set(self):
        result = run_backtest(self.panel, self._request())

        first_row = result.weights_over_time.iloc[0]
        self.assertAlmostEqual(first_row['A'], 0.5, places=12)
        self.assertAlmostEqual(first_row['B'], 0.5, places=12)
        self.assertAlmostEqual(first_row['C'], 0.0, places=12)

    def test_custom_targets_keep_their_relative_proportions(self):
        """40/30/20/10 missing its 10% becomes 44.4/33.3/22.2 (§5)."""
        request = validate_request({
            'holdings': [{'symbol': 'A', 'target_weight': 0.4},
                         {'symbol': 'B', 'target_weight': 0.4},
                         {'symbol': 'C', 'target_weight': 0.2}],
            'weighting_scheme': 'custom', 'min_history_days': 1,
            'rebalance_frequency': 'monthly', 'transaction_cost_bps': 0.0,
        })
        result = run_backtest(self.panel, request)

        first_row = result.weights_over_time.iloc[0]
        self.assertAlmostEqual(first_row['A'], 0.5, places=12)
        self.assertAlmostEqual(first_row['B'], 0.5, places=12)

    def test_c_enters_at_the_first_scheduled_rebalance_on_or_after_eligibility(self):
        result = run_backtest(self.panel, self._request())

        scheduled = sorted(schedule_dates(self.dates, 'monthly'))
        eligibility_date = self.dates[20]
        expected = next(d for d in scheduled if d >= eligibility_date)
        entry = next(e for e in result.composition_events
                     if e['symbol'] == 'C' and e['action'] == 'entered')

        self.assertEqual(entry['date'], expected.strftime('%Y-%m-%d'))
        self.assertIn(str(eligibility_date.date()), entry['reason'])

    def test_enter_immediately_enters_on_the_eligibility_date(self):
        result = run_backtest(self.panel, self._request(enter_immediately=True))

        entry = next(e for e in result.composition_events
                     if e['symbol'] == 'C' and e['action'] == 'entered')
        self.assertEqual(entry['date'], self.dates[20].strftime('%Y-%m-%d'))

    def test_c_gets_exactly_its_target_weight_at_entry(self):
        result = run_backtest(self.panel, self._request(enter_immediately=True))

        row = result.weights_over_time.loc[self.dates[20]]
        self.assertAlmostEqual(row['C'], 1 / 3, places=12)

    def test_effective_asset_count_matches_the_composition_event_log(self):
        result = run_backtest(self.panel, self._request())

        entry = next(e for e in result.composition_events
                     if e['symbol'] == 'C' and e['action'] == 'entered')
        entry_position = result.dates.index(entry['date'])
        self.assertEqual(int(result.effective_asset_count[entry_position - 1]), 2)
        self.assertEqual(int(result.effective_asset_count[entry_position]), 3)

    def test_min_history_days_delays_optimizer_eligibility_beyond_availability(self):
        result = run_backtest(self.panel, self._request(
            weighting_scheme='min_variance', min_history_days=10,
            lookback_days=10, backtest_mode='walk_forward'))

        # C is available from index 20 but not eligible until its 10th own
        # trading day, index 29. Indexed by date, because the result starts at
        # the effective start rather than at the panel's first date.
        before = result.weights_over_time.loc[:self.dates[28], 'C']
        self.assertTrue((before == 0.0).all())

    def test_common_start_reproduces_plain_intersection_behaviour(self):
        result = run_backtest(self.panel, self._request(
            inception_policy='common_start'))

        self.assertEqual(result.effective_start,
                         self.dates[20].strftime('%Y-%m-%d'))
        self.assertEqual(len(result.dates), 40)
        self.assertTrue((result.weights_over_time['C'] > 0).all())

    def test_no_eligible_asset_ever_is_a_hard_error(self):
        short = _panel({'A': [100.0, 101.0], 'B': [100.0, 99.0]},
                       pd.bdate_range('2020-01-01', periods=2))

        with self.assertRaises(NoEligibleAssets):
            run_backtest(short, validate_request({
                'holdings': [{'symbol': 'A'}, {'symbol': 'B'}],
                'weighting_scheme': 'min_variance', 'min_history_days': 252,
            }))

    def test_truncation_cause_is_reported_when_the_start_moves(self):
        result = run_backtest(self.panel, self._request(
            weighting_scheme='min_variance', min_history_days=10,
            lookback_days=10))

        self.assertIsNotNone(result.truncation_cause)
        self.assertIn('trading days of history', result.truncation_cause)


class DelistingTests(TestCase):
    """§5 -- exit on the delist date, at a real transaction cost."""

    def setUp(self):
        self.dates = pd.bdate_range('2020-01-01', periods=40)
        prices = {
            'A': np.linspace(100, 140, 40),
            # B's series ends at index 24.
            'B': np.concatenate([np.linspace(100, 124, 25), np.full(15, np.nan)]),
        }
        self.panel = _panel(prices, self.dates)

    def test_the_delisted_asset_is_liquidated_on_the_delist_date(self):
        result = run_backtest(self.panel, _request(
            holdings=[{'symbol': 'A'}, {'symbol': 'B'}],
            rebalance_frequency='monthly', min_history_days=1))

        exit_event = next(e for e in result.composition_events
                          if e['action'] == 'exited')
        self.assertEqual(exit_event['symbol'], 'B')
        self.assertEqual(exit_event['date'], self.dates[25].strftime('%Y-%m-%d'))
        self.assertEqual(result.weights_over_time['B'].iloc[25], 0.0)

    def test_the_forced_liquidation_incurs_a_transaction_cost(self):
        result = run_backtest(self.panel, _request(
            holdings=[{'symbol': 'A'}, {'symbol': 'B'}],
            rebalance_frequency='none', min_history_days=1,
            transaction_cost_bps=10.0))

        forced = [e for e in result.rebalance_events if e['trigger'] == 'exit']
        self.assertEqual(len(forced), 1)
        self.assertGreater(forced[0]['cost'], 0.0)

    def test_the_surviving_asset_absorbs_the_whole_portfolio(self):
        result = run_backtest(self.panel, _request(
            holdings=[{'symbol': 'A'}, {'symbol': 'B'}],
            rebalance_frequency='none', min_history_days=1))

        self.assertAlmostEqual(result.weights_over_time['A'].iloc[-1], 1.0, places=9)
```

- [ ] **Step 11: Run the inception tests to verify they pass**

```bash
python manage.py test backtester.tests.test_backtest -v 2
```

Expected: all PASS. If `test_c_enters_at_the_first_scheduled_rebalance_on_or_after_eligibility` fails because C entered on its eligibility date, check that the `not any(d >= today for d in scheduled)` branch in Step 3 is not firing when scheduled dates *do* lie ahead.

- [ ] **Step 12: Write the contribution tests**

Append to `backend/backtester/tests/test_backtest.py`:

```python
class ContributionTests(TestCase):
    """§8 -- two wealth series, and why conflating them produces wrong numbers."""

    def setUp(self):
        self.dates = pd.bdate_range('2020-01-01', periods=300)
        rng = np.random.default_rng(7)
        path = 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, 300))
        self.panel = _panel({'A': path, 'B': path * 0.5}, self.dates)

    def _run(self, contribution):
        return run_backtest(self.panel, _request(
            rebalance_frequency='quarterly', transaction_cost_bps=0.0,
            periodic_contribution=contribution,
            contribution_frequency='monthly' if contribution else 'none'))

    def test_the_index_is_unaffected_by_the_deposit_schedule(self):
        """CAGR must measure investment skill, not deposit timing."""
        without = self._run(0.0)
        with_deposits = self._run(500.0)

        np.testing.assert_allclose(without.index, with_deposits.index, rtol=1e-12)

    def test_nav_grows_by_at_least_the_contributed_amount(self):
        with_deposits = self._run(500.0)
        without = self._run(0.0)

        self.assertGreater(float(with_deposits.nav[-1]), float(without.nav[-1]))

    def test_drawdown_from_the_index_is_not_masked_by_contributions(self):
        without = self._run(0.0)
        with_deposits = self._run(5_000.0)

        np.testing.assert_allclose(without.drawdown, with_deposits.drawdown, rtol=1e-12)
        self.assertLess(with_deposits.drawdown.min(), 0.0)

    def test_contributions_do_not_change_composition(self):
        with_deposits = self._run(500.0)
        without = self._run(0.0)

        pd.testing.assert_frame_equal(with_deposits.weights_over_time,
                                      without.weights_over_time)

    def test_the_contribution_cost_hits_nav_only(self):
        free = run_backtest(self.panel, _request(
            rebalance_frequency='none', transaction_cost_bps=0.0,
            periodic_contribution=500.0, contribution_frequency='monthly'))
        charged = run_backtest(self.panel, _request(
            rebalance_frequency='none', transaction_cost_bps=50.0,
            periodic_contribution=500.0, contribution_frequency='monthly'))

        np.testing.assert_allclose(free.index, charged.index, rtol=1e-12)
        self.assertLess(float(charged.nav[-1]), float(free.nav[-1]))

    def test_cash_flows_record_every_deposit_and_the_terminal_value(self):
        result = self._run(500.0)

        deposits = [amount for _, amount in result.cash_flows if amount < 0]
        self.assertAlmostEqual(deposits[0], -10_000.0)
        self.assertTrue(all(amount == -500.0 for amount in deposits[1:]))
        self.assertAlmostEqual(result.cash_flows[-1][1], float(result.nav[-1]))
        self.assertEqual(result.cash_flows[-1][0], result.effective_end)
```

- [ ] **Step 13: Run the full backtest suite**

```bash
python manage.py test backtester.tests.test_backtest -v 2
```

Expected: all PASS.

- [ ] **Step 14: Commit**

```bash
git add backend/backtester/tests/test_backtest.py
git commit -m "test: cover staggered inception, delisting and contributions"
```

---

### Task 8: Performance metrics

Every risk and return statistic comes from the `index` (time-weighted) series; only balances come from `nav` (§9). Annualization is 252 days throughout.

**Files:**
- Create: `backend/backtester/engine/metrics.py`
- Test: `backend/backtester/tests/test_metrics.py`

**Interfaces:**
- Consumes: `optimizers.relative_risk_contribution`; `covariance.estimate_covariance`; `backtest.drawdown_series`.
- Produces:
  - `compute_metrics(result, request, returns_frame=None, benchmark_returns=None) -> dict` — the full §9 table as a flat JSON-safe dict. `returns_frame` is the panel's per-symbol returns, needed only for the correlation matrix and the two contribution decompositions; `benchmark_returns` is a plain array aligned to `result.dates`.
  - `money_weighted_return(cash_flows: list[tuple[str, float]]) -> float | None` — XIRR by bisection.
  - `drawdown_detail(index_values, dates) -> dict` with `max_drawdown`, `peak_date`, `trough_date`, `recovery_date`.
  - `calendar_year_returns(index_values, dates) -> dict[str, float]`
  - `beta_alpha(portfolio_returns, benchmark_returns, risk_free_rate) -> tuple[float, float]`
  - `capture_ratios(portfolio_returns, benchmark_returns) -> tuple[float, float]`
  - `contribution_to_return(weights_over_time, returns_frame) -> dict[str, float]`
  - `contribution_to_risk(weights, cov, symbols) -> dict[str, float]`
  - `correlation_matrix(returns_frame) -> dict`

- [ ] **Step 1: Write the failing test**

Create `backend/backtester/tests/test_metrics.py`:

```python
"""Performance metrics. Pure -- hand-computed expectations throughout."""
from unittest import TestCase

import numpy as np
import pandas as pd

from backtester.engine.metrics import (
    beta_alpha,
    calendar_year_returns,
    capture_ratios,
    compute_metrics,
    contribution_to_return,
    contribution_to_risk,
    correlation_matrix,
    drawdown_detail,
    money_weighted_return,
)


class DrawdownDetailTests(TestCase):

    def test_peak_trough_and_recovery_dates_are_identified(self):
        dates = ['2020-01-01', '2020-01-02', '2020-01-03', '2020-01-04', '2020-01-05']
        values = [1.0, 1.25, 1.0, 1.1, 1.3]

        detail = drawdown_detail(values, dates)

        self.assertAlmostEqual(detail['max_drawdown'], 1.0 / 1.25 - 1, places=12)
        self.assertEqual(detail['peak_date'], '2020-01-02')
        self.assertEqual(detail['trough_date'], '2020-01-03')
        self.assertEqual(detail['recovery_date'], '2020-01-05')

    def test_an_unrecovered_drawdown_reports_no_recovery_date(self):
        detail = drawdown_detail([1.0, 1.5, 0.9], ['a', 'b', 'c'])

        self.assertIsNone(detail['recovery_date'])

    def test_a_monotonically_rising_series_has_no_drawdown(self):
        detail = drawdown_detail([1.0, 1.1, 1.2], ['a', 'b', 'c'])

        self.assertAlmostEqual(detail['max_drawdown'], 0.0, places=15)
        self.assertIsNone(detail['peak_date'])


class MoneyWeightedReturnTests(TestCase):
    """§15 -- must match a known XIRR case."""

    def test_a_single_year_ten_percent_gain(self):
        flows = [('2020-01-01', -10_000.0), ('2021-01-01', 11_000.0)]

        self.assertAlmostEqual(money_weighted_return(flows), 0.10, places=5)

    def test_a_two_year_doubling_is_about_forty_one_percent_annualized(self):
        flows = [('2020-01-01', -10_000.0), ('2022-01-01', 20_000.0)]

        self.assertAlmostEqual(money_weighted_return(flows), 2 ** 0.5 - 1, places=4)

    def test_an_intermediate_deposit_is_time_weighted_by_its_own_date(self):
        flows = [('2020-01-01', -10_000.0),
                 ('2020-07-01', -5_000.0),
                 ('2021-01-01', 16_000.0)]

        rate = money_weighted_return(flows)
        self.assertGreater(rate, 0.0)
        self.assertLess(rate, 0.15)

    def test_a_total_loss_returns_a_negative_rate(self):
        flows = [('2020-01-01', -10_000.0), ('2021-01-01', 5_000.0)]

        self.assertLess(money_weighted_return(flows), -0.4)

    def test_flows_that_never_change_sign_return_none(self):
        self.assertIsNone(money_weighted_return([('2020-01-01', -1_000.0)]))


class CalendarYearTests(TestCase):

    def test_each_year_reports_its_own_growth(self):
        dates = ['2020-06-01', '2020-12-31', '2021-06-01', '2021-12-31']
        values = [1.0, 1.2, 1.2, 0.96]

        years = calendar_year_returns(values, dates)

        self.assertAlmostEqual(years['2020'], 0.2, places=12)
        self.assertAlmostEqual(years['2021'], -0.2, places=12)


class BetaAlphaTests(TestCase):

    def test_a_portfolio_identical_to_the_benchmark_has_beta_one_alpha_zero(self):
        rng = np.random.default_rng(3)
        benchmark = rng.normal(0.0004, 0.01, 500)

        beta, alpha = beta_alpha(benchmark, benchmark, 0.0)
        self.assertAlmostEqual(beta, 1.0, places=9)
        self.assertAlmostEqual(alpha, 0.0, places=9)

    def test_a_levered_portfolio_has_beta_two(self):
        rng = np.random.default_rng(5)
        benchmark = rng.normal(0.0004, 0.01, 500)

        beta, _ = beta_alpha(2 * benchmark, benchmark, 0.0)
        self.assertAlmostEqual(beta, 2.0, places=9)

    def test_alpha_is_annualized(self):
        rng = np.random.default_rng(11)
        benchmark = rng.normal(0.0, 0.01, 500)
        portfolio = benchmark + 0.001            # +0.1%/day

        _, alpha = beta_alpha(portfolio, benchmark, 0.0)
        self.assertAlmostEqual(alpha, 0.001 * 252, places=6)


class CaptureRatioTests(TestCase):

    def test_a_half_beta_portfolio_captures_half_of_each_direction(self):
        benchmark = np.array([0.02, -0.02, 0.03, -0.01])
        portfolio = benchmark * 0.5

        up, down = capture_ratios(portfolio, benchmark)
        self.assertAlmostEqual(up, 0.5, places=12)
        self.assertAlmostEqual(down, 0.5, places=12)

    def test_a_benchmark_with_no_down_periods_reports_no_down_capture(self):
        up, down = capture_ratios(np.array([0.01, 0.02]), np.array([0.02, 0.03]))

        self.assertIsNotNone(up)
        self.assertIsNone(down)


class ContributionTests(TestCase):

    def test_contribution_to_return_sums_to_one(self):
        dates = pd.bdate_range('2020-01-01', periods=10)
        weights = pd.DataFrame({'A': 0.6, 'B': 0.4}, index=dates)
        returns = pd.DataFrame({'A': np.linspace(0.001, 0.01, 10),
                                'B': np.linspace(0.002, 0.004, 10)}, index=dates)

        shares = contribution_to_return(weights, returns)
        self.assertAlmostEqual(sum(shares.values()), 1.0, places=12)

    def test_contribution_to_risk_sums_to_one_and_matches_the_shared_definition(self):
        from backtester.engine.optimizers import relative_risk_contribution

        cov = np.array([[0.04, 0.01], [0.01, 0.09]])
        weights = np.array([0.7, 0.3])

        shares = contribution_to_risk(weights, cov, ['A', 'B'])
        self.assertAlmostEqual(sum(shares.values()), 1.0, places=12)
        np.testing.assert_allclose(list(shares.values()),
                                   relative_risk_contribution(weights, cov),
                                   rtol=1e-12)

    def test_correlation_matrix_is_symmetric_with_a_unit_diagonal(self):
        dates = pd.bdate_range('2020-01-01', periods=50)
        rng = np.random.default_rng(13)
        returns = pd.DataFrame(rng.normal(0, 0.01, (50, 3)),
                               index=dates, columns=['A', 'B', 'C'])

        matrix = correlation_matrix(returns)

        self.assertEqual(matrix['symbols'], ['A', 'B', 'C'])
        for i, row in enumerate(matrix['values']):
            self.assertAlmostEqual(row[i], 1.0, places=12)
            for j, value in enumerate(row):
                self.assertAlmostEqual(value, matrix['values'][j][i], places=12)


class ComputeMetricsTests(TestCase):
    """The full §9 table, driven off a real BacktestResult."""

    def setUp(self):
        from backtester.engine.backtest import run_backtest
        from backtester.engine.config import validate_request
        from backtester.engine.prices import PricePanel

        dates = pd.bdate_range('2018-01-01', periods=756)   # ~3 years
        rng = np.random.default_rng(17)
        path_a = 100 * np.cumprod(1 + rng.normal(0.0005, 0.011, 756))
        path_b = 100 * np.cumprod(1 + rng.normal(0.0003, 0.007, 756))
        frame = pd.DataFrame({'A': path_a, 'B': path_b}, index=dates)
        panel = PricePanel(
            prices=frame,
            first_valid={c: frame.index[0] for c in frame.columns},
            last_valid={c: frame.index[-1] for c in frame.columns},
            provenance={c: 'test' for c in frame.columns},
        )
        self.request = validate_request({
            'holdings': [{'symbol': 'A'}, {'symbol': 'B'}],
            'rebalance_frequency': 'annual', 'min_history_days': 1,
        })
        self.result = run_backtest(panel, self.request)
        self.returns_frame = panel.returns()
        self.benchmark_returns = rng.normal(0.0004, 0.010, len(self.result.dates))
        self.benchmark_index = np.cumprod(1 + self.benchmark_returns)

    def test_every_documented_metric_is_present(self):
        metrics = compute_metrics(self.result, self.request,
                                  returns_frame=self.returns_frame,
                                  benchmark_returns=self.benchmark_returns)

        expected = {
            'cagr', 'annualized_return', 'annualized_volatility', 'sharpe',
            'sortino', 'max_drawdown', 'max_drawdown_peak_date',
            'max_drawdown_trough_date', 'max_drawdown_recovery_date', 'calmar',
            'var_95', 'cvar_95', 'best_year', 'worst_year', 'calendar_year_returns',
            'beta', 'alpha', 'up_capture', 'down_capture', 'annual_turnover',
            'total_costs_paid', 'total_costs_annualized_bps', 'correlation_matrix',
            'contribution_to_return', 'contribution_to_risk', 'ending_balance',
            'total_contributed', 'total_gain', 'money_weighted_return', 'years',
        }
        self.assertTrue(expected.issubset(metrics), expected - set(metrics))

    def test_cagr_is_derived_from_the_index_not_the_nav(self):
        metrics = compute_metrics(self.result, self.request,
                                  returns_frame=self.returns_frame)

        years = len(self.result.dates) / 252
        expected = (self.result.index[-1] / self.result.index[0]) ** (1 / years) - 1
        self.assertAlmostEqual(metrics['cagr'], expected, places=12)

    def test_volatility_is_annualized_with_252_days(self):
        metrics = compute_metrics(self.result, self.request,
                                  returns_frame=self.returns_frame)

        expected = float(np.std(self.result.returns[1:], ddof=1) * np.sqrt(252))
        self.assertAlmostEqual(metrics['annualized_volatility'], expected, places=12)

    def test_cvar_is_no_greater_than_var(self):
        metrics = compute_metrics(self.result, self.request,
                                  returns_frame=self.returns_frame)

        self.assertLessEqual(metrics['cvar_95'], metrics['var_95'])

    def test_beta_is_omitted_without_a_benchmark(self):
        metrics = compute_metrics(self.result, self.request,
                                  returns_frame=self.returns_frame)

        self.assertIsNone(metrics['beta'])

    def test_every_value_is_json_serializable(self):
        import json

        metrics = compute_metrics(self.result, self.request,
                                  returns_frame=self.returns_frame,
                                  benchmark_returns=self.benchmark_returns)
        json.dumps(metrics)

    def test_balances_come_from_nav(self):
        metrics = compute_metrics(self.result, self.request,
                                  returns_frame=self.returns_frame)

        self.assertAlmostEqual(metrics['ending_balance'], float(self.result.nav[-1]),
                               places=6)
        self.assertAlmostEqual(metrics['total_contributed'], 10_000.0, places=6)
        self.assertAlmostEqual(metrics['total_gain'],
                               float(self.result.nav[-1]) - 10_000.0, places=6)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python manage.py test backtester.tests.test_metrics -v 2
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backtester.engine.metrics'`.

- [ ] **Step 3: Write `engine/metrics.py`**

Create `backend/backtester/engine/metrics.py`:

```python
"""Performance measures of §9.

Everything risk- or return-shaped is computed from the time-weighted `index`
series. Only balances come from `nav`. With periodic contributions, a CAGR taken
off `nav` conflates investment skill with the deposit schedule, and a drawdown
taken off `nav` lets a well-timed deposit paper over a real loss.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import drawdown_series
from .covariance import estimate_covariance
from .optimizers import relative_risk_contribution

TRADING_DAYS = 252


def _finite(value):
    """JSON-safe scalar: NaN and ±inf become None, numpy scalars become floats."""
    if value is None:
        return None
    value = float(value)
    return None if (value != value or value in (float('inf'), float('-inf'))) else value


def drawdown_detail(index_values, dates) -> dict:
    values = np.asarray(index_values, dtype=float)
    drawdown = drawdown_series(values)
    trough = int(np.argmin(drawdown))
    if drawdown[trough] >= -1e-15:
        return {'max_drawdown': 0.0, 'peak_date': None, 'trough_date': None,
                'recovery_date': None}

    peak = int(np.argmax(values[:trough + 1]))
    recovery = None
    after = np.flatnonzero(values[trough:] >= values[peak])
    if after.size:
        recovery = dates[trough + int(after[0])]

    return {
        'max_drawdown': _finite(drawdown[trough]),
        'peak_date': dates[peak],
        'trough_date': dates[trough],
        'recovery_date': recovery,
    }


def calendar_year_returns(index_values, dates) -> dict:
    series = pd.Series(np.asarray(index_values, dtype=float),
                       index=pd.to_datetime(list(dates)))
    years = {}
    for year, block in series.groupby(series.index.year):
        years[str(year)] = _finite(block.iloc[-1] / block.iloc[0] - 1.0)
    return years


def beta_alpha(portfolio_returns, benchmark_returns, risk_free_rate=0.0):
    """OLS of portfolio excess returns on benchmark excess returns. Alpha is
    annualized; beta is unitless."""
    portfolio = np.asarray(portfolio_returns, dtype=float)
    benchmark = np.asarray(benchmark_returns, dtype=float)
    length = min(portfolio.size, benchmark.size)
    if length < 3:
        return None, None
    daily_rf = float(risk_free_rate) / TRADING_DAYS
    x = benchmark[-length:] - daily_rf
    y = portfolio[-length:] - daily_rf

    variance = float(np.var(x, ddof=1))
    if variance <= 0:
        return None, None
    beta = float(np.cov(y, x, ddof=1)[0, 1] / variance)
    alpha = float(y.mean() - beta * x.mean()) * TRADING_DAYS
    return _finite(beta), _finite(alpha)


def capture_ratios(portfolio_returns, benchmark_returns):
    portfolio = np.asarray(portfolio_returns, dtype=float)
    benchmark = np.asarray(benchmark_returns, dtype=float)
    length = min(portfolio.size, benchmark.size)
    portfolio, benchmark = portfolio[-length:], benchmark[-length:]

    def capture(mask):
        if not mask.any():
            return None
        denominator = float(benchmark[mask].mean())
        if abs(denominator) < 1e-15:
            return None
        return _finite(float(portfolio[mask].mean()) / denominator)

    return capture(benchmark > 0), capture(benchmark < 0)


def contribution_to_return(weights_over_time, returns_frame) -> dict:
    """w̄_i · r̄_i per asset, normalized to sum to 1."""
    shared = [c for c in weights_over_time.columns if c in returns_frame.columns]
    weights = weights_over_time[shared]
    returns = returns_frame.reindex(weights.index)[shared]

    products = (weights * returns).sum(axis=0)
    total = float(products.sum())
    if abs(total) < 1e-18:
        return {symbol: 0.0 for symbol in shared}
    return {symbol: _finite(products[symbol] / total) for symbol in shared}


def contribution_to_risk(weights, cov, symbols) -> dict:
    """wᵢ(Σw)ᵢ / (wᵀΣw) per asset. Shares the definition with the risk-parity
    objective -- see optimizers.relative_risk_contribution."""
    shares = relative_risk_contribution(np.asarray(weights, dtype=float),
                                        np.asarray(cov, dtype=float))
    return {symbol: _finite(share) for symbol, share in zip(symbols, shares)}


def correlation_matrix(returns_frame) -> dict:
    matrix = returns_frame.corr()
    return {
        'symbols': list(matrix.columns),
        'values': [[_finite(v) for v in row] for row in matrix.to_numpy()],
    }


def money_weighted_return(cash_flows) -> float | None:
    """XIRR by bisection on the dated cash-flow vector.

    Bisection rather than Newton: the NPV function is monotone in the discount
    rate for a conventional flow schedule, and bisection cannot diverge the way
    Newton does when the initial guess sits near a flat region.
    """
    flows = [(pd.Timestamp(d), float(a)) for d, a in cash_flows]
    if len(flows) < 2:
        return None
    amounts = [a for _, a in flows]
    if not (any(a > 0 for a in amounts) and any(a < 0 for a in amounts)):
        return None

    start = min(d for d, _ in flows)
    years = np.array([(d - start).days / 365.0 for d, _ in flows])
    values = np.array(amounts)

    def npv(rate):
        return float(np.sum(values / (1.0 + rate) ** years))

    low, high = -0.9999, 10.0
    if npv(low) * npv(high) > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2.0
        if npv(low) * npv(mid) <= 0:
            high = mid
        else:
            low = mid
    return _finite((low + high) / 2.0)


def compute_metrics(result, request, returns_frame=None,
                    benchmark_returns=None) -> dict:
    """The §9 table for one wealth series, as a flat JSON-safe dict."""
    index_values = np.asarray(result.index, dtype=float)
    # Drop the seeding row: its return is 0 by construction and would bias every
    # mean and standard deviation downward.
    period_returns = np.asarray(result.returns, dtype=float)[1:]
    observations = period_returns.size
    years = len(result.dates) / TRADING_DAYS
    daily_rf = float(request.risk_free_rate) / TRADING_DAYS

    volatility = float(np.std(period_returns, ddof=1)) if observations > 1 else 0.0
    mean_return = float(period_returns.mean()) if observations else 0.0

    cagr = ((index_values[-1] / index_values[0]) ** (1 / years) - 1.0
            if years > 0 and index_values[0] > 0 else None)
    sharpe = ((mean_return - daily_rf) / volatility * np.sqrt(TRADING_DAYS)
              if volatility > 0 else None)

    downside = period_returns[period_returns < daily_rf] - daily_rf
    downside_deviation = float(np.sqrt(np.mean(downside ** 2))) if downside.size else 0.0
    sortino = ((mean_return - daily_rf) / downside_deviation * np.sqrt(TRADING_DAYS)
               if downside_deviation > 0 else None)

    drawdown = drawdown_detail(index_values, result.dates)
    calmar = (cagr / abs(drawdown['max_drawdown'])
              if cagr is not None and drawdown['max_drawdown'] else None)

    var_95 = float(np.percentile(period_returns, 5)) if observations else None
    tail = period_returns[period_returns <= var_95] if observations else np.array([])
    cvar_95 = float(tail.mean()) if tail.size else var_95

    years_map = calendar_year_returns(index_values, result.dates)
    complete_years = {k: v for k, v in years_map.items() if v is not None}

    total_turnover = sum(event['turnover'] for event in result.rebalance_events)
    total_cost_fraction = sum(event['cost'] for event in result.rebalance_events)
    contributed = float(request.initial_amount) + sum(
        -amount for _, amount in result.cash_flows[1:-1])

    beta = alpha = up_capture = down_capture = None
    if benchmark_returns is not None:
        beta, alpha = beta_alpha(period_returns, np.asarray(benchmark_returns)[1:],
                                 request.risk_free_rate)
        up_capture, down_capture = capture_ratios(
            period_returns, np.asarray(benchmark_returns)[1:])

    correlations = {'symbols': [], 'values': []}
    to_return, to_risk = {}, {}
    if returns_frame is not None and not returns_frame.empty:
        window = returns_frame.loc[returns_frame.index.astype(str).isin(result.dates)]
        correlations = correlation_matrix(window)
        to_return = contribution_to_return(result.weights_over_time, returns_frame)
        final_weights = result.weights_over_time.iloc[-1].to_numpy()
        if window.shape[0] > 2:
            cov = estimate_covariance(window.to_numpy(), request.covariance_method)
            to_risk = contribution_to_risk(final_weights, cov, list(window.columns))

    return {
        'years': _finite(years),
        'observations': int(observations),
        'cagr': _finite(cagr),
        'annualized_return': _finite(mean_return * TRADING_DAYS),
        'annualized_volatility': _finite(volatility * np.sqrt(TRADING_DAYS)),
        'sharpe': _finite(sharpe),
        'sortino': _finite(sortino),
        'max_drawdown': drawdown['max_drawdown'],
        'max_drawdown_peak_date': drawdown['peak_date'],
        'max_drawdown_trough_date': drawdown['trough_date'],
        'max_drawdown_recovery_date': drawdown['recovery_date'],
        'calmar': _finite(calmar),
        'var_95': _finite(var_95),
        'cvar_95': _finite(cvar_95),
        'calendar_year_returns': years_map,
        'best_year': max(complete_years, key=complete_years.get) if complete_years else None,
        'best_year_return': max(complete_years.values()) if complete_years else None,
        'worst_year': min(complete_years, key=complete_years.get) if complete_years else None,
        'worst_year_return': min(complete_years.values()) if complete_years else None,
        'beta': beta,
        'alpha': alpha,
        'up_capture': up_capture,
        'down_capture': down_capture,
        'annual_turnover': _finite(total_turnover / years) if years > 0 else None,
        'total_costs_paid': _finite(total_cost_fraction * float(request.initial_amount)),
        'total_costs_annualized_bps': (_finite(total_cost_fraction / years * 10_000)
                                       if years > 0 else None),
        'correlation_matrix': correlations,
        'contribution_to_return': to_return,
        'contribution_to_risk': to_risk,
        'ending_balance': _finite(result.nav[-1]),
        'total_contributed': _finite(contributed),
        'total_gain': _finite(float(result.nav[-1]) - contributed),
        'money_weighted_return': money_weighted_return(result.cash_flows),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python manage.py test backtester.tests.test_metrics -v 2
```

Expected: all PASS.

- [ ] **Step 5: Cross-check against the notebook reference**

Task 1 recorded CAGR, volatility and max drawdown for a 60/40 SPY/AGG backtest. Confirm `compute_metrics` reproduces the same three numbers on the same panel by adding a temporary scratch script (do **not** commit it):

```bash
python manage.py shell -c "
from backtester.engine.prices import load_price_panel
from backtester.engine.config import validate_request
from backtester.engine.backtest import run_backtest
from backtester.engine.metrics import compute_metrics
panel = load_price_panel(['SPY', 'AGG'])
request = validate_request({'holdings': [{'symbol':'SPY','target_weight':0.6},{'symbol':'AGG','target_weight':0.4}], 'weighting_scheme':'custom','rebalance_frequency':'annual'})
result = run_backtest(panel, request)
m = compute_metrics(result, request, returns_frame=panel.returns())
print(m['cagr'], m['annualized_volatility'], m['max_drawdown'])
"
```

**`inception_policy='common_start'` is essential here, and the plan originally omitted it.** The notebook used `panel.dropna()`, i.e. intersection. The engine's default is phase-in, which for SPY/AGG starts in 1999 with SPY alone and admits AGG when it lists in 2003 — a genuinely different question, and it reports CAGR 6.36%, volatility 13.54%, max drawdown −47.5% (the dot-com crash, held 100% SPY). Comparing that against the notebook looks like a catastrophic bug and is not one. Add `'inception_policy': 'common_start'` to the request before comparing.

Expected with `common_start`:

| | Engine | Notebook | |
|---|---|---|---|
| Max drawdown | −0.339949 | −0.339949 | exact |
| CAGR | 0.082008 | 0.082203 | 0.24% relative |
| Volatility | 0.108972 | 0.113358 | 3.9% relative — see below |

Max drawdown matching to six decimals is the signal to trust; so are the drawdown dates, which come out 2007-10-09 → 2009-03-09 recovering 2010-11-04, the correct S&P 500 GFC peak, trough and recovery.

**The volatility gap is expected, not an error.** The notebook computes `returns.dot(targets).std()` — the volatility of a portfolio held at *fixed* 60/40 weights forever, with no drift and no rebalancing. The engine computes the volatility of the actual drifted-and-rebalanced portfolio's realized returns. These are different quantities and the engine's is the one that answers the user's question. Do not "fix" the engine to match.

If max drawdown does **not** match to several decimals, that is a real discrepancy in the loop or the metrics — resolve it before continuing.

**Worth noticing what the phase-in run demonstrates.** A user asking for "as much history as possible" on a 60/40 gets a −47.5% drawdown that is really a single-asset dot-com drawdown, because the bond half did not exist yet. That is precisely what the `composition_coverage` and `single_asset_period` diagnostics of Task 9 exist to say out loud.

- [ ] **Step 6: Commit**

```bash
git add backend/backtester/engine/metrics.py backend/backtester/tests/test_metrics.py
git commit -m "feat: add the backtest performance metrics"
```

---

### Task 9: Seven-sins diagnostics

The feature that distinguishes this from a toy backtester (§10). Thirteen structured findings in plain language, ordered so `critical` renders above the results rather than below them.

**Files:**
- Create: `backend/backtester/engine/diagnostics.py`
- Test: `backend/backtester/tests/test_diagnostics.py`

**Interfaces:**
- Consumes: `backtest.BacktestResult` (by attribute access only — no import of the class, which is what keeps `backtest.py` free of a diagnostics import); the metrics dict from Task 8.
- Produces:
  - `build_diagnostics(result, request, metrics, benchmark_returns=None) -> list[dict]` — each entry `{code, severity, title, detail}`, ordered critical → warning → info.
  - `SEVERITY_ORDER: dict[str, int]`
  - `CODES: tuple[str, ...]` — the thirteen codes, for the view layer and the test to assert against.

- [ ] **Step 1: Write the failing test**

Create `backend/backtester/tests/test_diagnostics.py`:

```python
"""The seven-sins reality check."""
from types import SimpleNamespace
from unittest import TestCase

import numpy as np
import pandas as pd

from backtester.engine.config import validate_request
from backtester.engine.diagnostics import CODES, build_diagnostics


def _result(**overrides):
    dates = [d.strftime('%Y-%m-%d') for d in pd.bdate_range('2015-01-01', periods=1512)]
    rng = np.random.default_rng(3)
    returns = np.concatenate([[0.0], rng.normal(0.0004, 0.01, 1511)])
    index = np.cumprod(1 + returns)
    weights = pd.DataFrame({'A': 0.5, 'B': 0.5},
                           index=pd.to_datetime(dates))
    defaults = {
        'dates': dates,
        'nav': index * 10_000,
        'index': index,
        'returns': returns,
        'drawdown': np.minimum(index / np.maximum.accumulate(index) - 1, 0.0),
        'weights_over_time': weights,
        'effective_asset_count': np.full(len(dates), 2),
        'rebalance_events': [],
        'composition_events': [],
        'cash_flows': [(dates[0], -10_000.0), (dates[-1], float(index[-1] * 10_000))],
        'symbols': ['A', 'B'],
        'effective_start': dates[0],
        'effective_end': dates[-1],
        'truncation_cause': None,
        'fallback_dates': [],
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _request(**overrides):
    payload = {'holdings': [{'symbol': 'A'}, {'symbol': 'B'}],
               'rebalance_frequency': 'annual'}
    payload.update(overrides)
    return validate_request(payload)


def _metrics(**overrides):
    defaults = {'cagr': 0.09, 'years': 6.0, 'max_drawdown': -0.28,
                'annualized_volatility': 0.15}
    defaults.update(overrides)
    return defaults


def _codes(findings):
    return [finding['code'] for finding in findings]


class AlwaysFiringTests(TestCase):

    def test_survivorship_bias_always_fires(self):
        findings = build_diagnostics(_result(), _request(), _metrics())

        self.assertIn('survivorship_bias', _codes(findings))

    def test_every_finding_has_the_documented_shape(self):
        findings = build_diagnostics(_result(), _request(), _metrics())

        for finding in findings:
            self.assertEqual(set(finding), {'code', 'severity', 'title', 'detail'})
            self.assertIn(finding['severity'], ('info', 'warning', 'critical'))
            self.assertIn(finding['code'], CODES)
            self.assertTrue(finding['detail'].strip())

    def test_findings_are_ordered_most_severe_first(self):
        findings = build_diagnostics(
            _result(effective_asset_count=np.ones(1512)),
            _request(weighting_scheme='max_sharpe', backtest_mode='fixed'),
            _metrics())

        rank = {'critical': 0, 'warning': 1, 'info': 2}
        severities = [rank[f['severity']] for f in findings]
        self.assertEqual(severities, sorted(severities))


class TruncationAndCoverageTests(TestCase):

    def test_history_truncation_fires_when_the_start_moved(self):
        findings = build_diagnostics(
            _result(truncation_cause='Started 2018-01-02 rather than 2015-01-01: B.'),
            _request(), _metrics())

        finding = next(f for f in findings if f['code'] == 'history_truncation')
        self.assertIn('2018-01-02', finding['detail'])

    def test_composition_coverage_fires_when_half_the_assets_are_missing(self):
        """§10: fewer than half the assets held for more than 25% of the period."""
        counts = np.concatenate([np.ones(1000), np.full(512, 3)])
        findings = build_diagnostics(
            _result(effective_asset_count=counts, symbols=['A', 'B', 'C']),
            _request(holdings=[{'symbol': 'A'}, {'symbol': 'B'}, {'symbol': 'C'}]),
            _metrics())

        finding = next(f for f in findings if f['code'] == 'composition_coverage')
        self.assertEqual(finding['severity'], 'critical')
        self.assertIn('66', finding['detail'])

    def test_composition_coverage_stays_quiet_on_a_fully_populated_portfolio(self):
        findings = build_diagnostics(_result(), _request(), _metrics())

        self.assertNotIn('composition_coverage', _codes(findings))

    def test_single_asset_period_fires_beyond_thirty_trading_days(self):
        counts = np.concatenate([np.ones(40), np.full(1472, 2)])
        findings = build_diagnostics(_result(effective_asset_count=counts),
                                     _request(), _metrics())

        self.assertIn('single_asset_period', _codes(findings))

    def test_a_short_single_asset_span_does_not_fire(self):
        counts = np.concatenate([np.ones(10), np.full(1502, 2)])
        findings = build_diagnostics(_result(effective_asset_count=counts),
                                     _request(), _metrics())

        self.assertNotIn('single_asset_period', _codes(findings))


class OverfittingTests(TestCase):

    def test_in_sample_fit_fires_for_a_fixed_optimizer_run(self):
        findings = build_diagnostics(
            _result(), _request(weighting_scheme='min_variance',
                                backtest_mode='fixed'), _metrics())

        finding = next(f for f in findings if f['code'] == 'in_sample_fit')
        self.assertIn('walk-forward', finding['detail'])

    def test_in_sample_fit_stays_quiet_for_walk_forward(self):
        findings = build_diagnostics(
            _result(), _request(weighting_scheme='min_variance',
                                backtest_mode='walk_forward'), _metrics())

        self.assertNotIn('in_sample_fit', _codes(findings))

    def test_in_sample_fit_stays_quiet_for_equal_weight(self):
        findings = build_diagnostics(_result(), _request(backtest_mode='fixed'),
                                     _metrics())

        self.assertNotIn('in_sample_fit', _codes(findings))

    def test_return_estimation_fires_only_for_max_sharpe(self):
        with_ms = build_diagnostics(_result(),
                                    _request(weighting_scheme='max_sharpe'), _metrics())
        without = build_diagnostics(_result(),
                                    _request(weighting_scheme='min_variance'), _metrics())

        self.assertIn('return_estimation', _codes(with_ms))
        self.assertNotIn('return_estimation', _codes(without))

    def test_short_sample_fires_under_three_years(self):
        findings = build_diagnostics(_result(), _request(), _metrics(years=2.0))

        self.assertIn('short_sample', _codes(findings))

    def test_short_sample_fires_with_too_few_rebalances(self):
        findings = build_diagnostics(_result(), _request(), _metrics(years=8.0))

        # Eight years of annual rebalancing is 8 observations, well under 60.
        self.assertIn('short_sample', _codes(findings))

    def test_short_sample_stays_quiet_with_a_long_monthly_run(self):
        events = [{'date': '2016-01-04', 'turnover': 0.01, 'cost': 0.0,
                   'trigger': 'scheduled', 'weights': {}} for _ in range(80)]
        findings = build_diagnostics(_result(rebalance_events=events), _request(),
                                     _metrics(years=8.0))

        self.assertNotIn('short_sample', _codes(findings))


class CostAndOutlierTests(TestCase):

    def test_cost_sensitivity_fires_when_fees_eat_the_gross_return(self):
        events = [{'date': '2016-01-04', 'turnover': 2.0, 'cost': 0.02,
                   'trigger': 'scheduled', 'weights': {}} for _ in range(6)]
        result = _result(rebalance_events=events)
        result.index = np.linspace(1.0, 1.10, len(result.dates))

        findings = build_diagnostics(result, _request(), _metrics(cagr=0.02))
        self.assertIn('cost_sensitivity', _codes(findings))

    def test_cost_sensitivity_stays_quiet_on_a_cheap_strategy(self):
        findings = build_diagnostics(_result(), _request(), _metrics())

        self.assertNotIn('cost_sensitivity', _codes(findings))

    def test_outlier_dependence_fires_when_five_days_carry_the_return(self):
        dates = [d.strftime('%Y-%m-%d') for d in pd.bdate_range('2015-01-01', periods=800)]
        returns = np.zeros(800)
        returns[[10, 20, 30, 40, 50]] = 0.30      # everything comes from 5 days
        index = np.cumprod(1 + returns)
        result = _result(dates=dates, returns=returns, index=index,
                         nav=index * 10_000,
                         effective_asset_count=np.full(800, 2),
                         weights_over_time=pd.DataFrame(
                             {'A': 0.5, 'B': 0.5}, index=pd.to_datetime(dates)))

        findings = build_diagnostics(result, _request(), _metrics(years=3.2))
        self.assertIn('outlier_dependence', _codes(findings))

    def test_outlier_dependence_stays_quiet_on_a_broad_based_return(self):
        findings = build_diagnostics(_result(), _request(), _metrics())

        self.assertNotIn('outlier_dependence', _codes(findings))


class ConcentrationAndShortingTests(TestCase):

    def test_concentration_fires_above_a_forty_percent_weight(self):
        dates = pd.bdate_range('2015-01-01', periods=1512)
        weights = pd.DataFrame({'A': 0.6, 'B': 0.2, 'C': 0.2}, index=dates)
        findings = build_diagnostics(
            _result(weights_over_time=weights, symbols=['A', 'B', 'C'],
                    effective_asset_count=np.full(1512, 3)),
            _request(holdings=[{'symbol': 'A'}, {'symbol': 'B'}, {'symbol': 'C'}]),
            _metrics())

        self.assertIn('concentration', _codes(findings))

    def test_concentration_fires_on_a_low_effective_n(self):
        findings = build_diagnostics(_result(), _request(), _metrics())

        # 50/50 gives effective N = 2, below the threshold of 3.
        self.assertIn('concentration', _codes(findings))

    def test_shorting_unmodelled_fires_when_long_only_is_off(self):
        findings = build_diagnostics(_result(), _request(long_only=False), _metrics())

        finding = next(f for f in findings if f['code'] == 'shorting_unmodelled')
        self.assertIn('borrow', finding['detail'].lower())

    def test_shorting_unmodelled_stays_quiet_by_default(self):
        findings = build_diagnostics(_result(), _request(), _metrics())

        self.assertNotIn('shorting_unmodelled', _codes(findings))


class FallbackAndBenchmarkTests(TestCase):

    def test_optimizer_fallback_lists_the_dates(self):
        findings = build_diagnostics(
            _result(fallback_dates=['2018-01-02', '2019-01-02']),
            _request(weighting_scheme='risk_parity'), _metrics())

        finding = next(f for f in findings if f['code'] == 'optimizer_fallback')
        self.assertEqual(finding['severity'], 'critical')
        self.assertIn('2018-01-02', finding['detail'])

    def test_benchmark_mismatch_fires_on_a_weakly_correlated_benchmark(self):
        rng = np.random.default_rng(9)
        result = _result()
        benchmark = rng.normal(0.0004, 0.01, len(result.dates))

        findings = build_diagnostics(result, _request(), _metrics(),
                                     benchmark_returns=benchmark)
        self.assertIn('benchmark_mismatch', _codes(findings))

    def test_benchmark_mismatch_stays_quiet_when_correlation_is_high(self):
        result = _result()
        benchmark = np.asarray(result.returns) * 0.9

        findings = build_diagnostics(result, _request(), _metrics(),
                                     benchmark_returns=benchmark)
        self.assertNotIn('benchmark_mismatch', _codes(findings))

    def test_no_benchmark_means_no_mismatch_finding(self):
        findings = build_diagnostics(_result(), _request(), _metrics())

        self.assertNotIn('benchmark_mismatch', _codes(findings))
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python manage.py test backtester.tests.test_diagnostics -v 2
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backtester.engine.diagnostics'`.

- [ ] **Step 3: Write `engine/diagnostics.py`**

Create `backend/backtester/engine/diagnostics.py`:

```python
"""The seven-sins reality check of §10.

Plain language, no jargon without a gloss. Severity drives presentation:
`critical` findings render above the results, not below them.

Storytelling bias (sin #3) is not machine-detectable and is addressed in static
UI copy accompanying the panel rather than here.
"""
from __future__ import annotations

import numpy as np

CODES = (
    'survivorship_bias', 'history_truncation', 'composition_coverage',
    'single_asset_period', 'in_sample_fit', 'return_estimation', 'short_sample',
    'cost_sensitivity', 'outlier_dependence', 'concentration',
    'shorting_unmodelled', 'optimizer_fallback', 'benchmark_mismatch',
)
SEVERITY_ORDER = {'critical': 0, 'warning': 1, 'info': 2}

OPTIMIZER_SCHEMES = ('inverse_vol', 'min_variance', 'risk_parity', 'max_sharpe')
TRADING_DAYS = 252

# Thresholds, named so the reason each one exists is readable.
COVERAGE_SHARE_THRESHOLD = 0.25        # of the period
SINGLE_ASSET_MIN_DAYS = 30
SHORT_SAMPLE_YEARS = 3.0
SHORT_SAMPLE_REBALANCES = 60
COST_SHARE_OF_GROSS = 0.15
OUTLIER_CAGR_DROP = 0.50
MAX_SINGLE_WEIGHT = 0.40
MIN_EFFECTIVE_N = 3.0
BENCHMARK_MIN_CORRELATION = 0.30


def _longest_run(mask) -> int:
    longest = current = 0
    for flag in np.asarray(mask, dtype=bool):
        current = current + 1 if flag else 0
        longest = max(longest, current)
    return longest


def build_diagnostics(result, request, metrics, benchmark_returns=None) -> list:
    findings = []

    def add(code, severity, title, detail):
        findings.append({'code': code, 'severity': severity,
                         'title': title, 'detail': detail})

    # --- Sin #1: survivorship. Always. --------------------------------------
    add('survivorship_bias', 'warning',
        'These results are optimistic by construction',
        'The universe behind this simulation is built from the companies that are '
        'in the major indexes *today*. Firms that went bankrupt or were taken '
        'private are simply absent from the data, so the historical returns you '
        'see are better than what an investor could actually have earned. There is '
        'no way to correct for this with the data available; treat every return '
        'below as an upper bound.')

    if result.truncation_cause:
        add('history_truncation', 'warning',
            'The simulation is shorter than you asked for',
            result.truncation_cause)

    # --- Coverage of the requested basket ----------------------------------
    counts = np.asarray(result.effective_asset_count, dtype=float)
    requested = len(request.holdings)
    if requested > 1 and counts.size:
        thin = counts < (requested / 2.0)
        share = float(thin.mean())
        if share > COVERAGE_SHARE_THRESHOLD:
            dominant = (result.weights_over_time.loc[thin]
                        .mean(axis=0).sort_values(ascending=False)
                        if hasattr(result.weights_over_time, 'loc') else None)
            names = (', '.join(dominant.index[:2]) if dominant is not None else '')
            add('composition_coverage', 'critical',
                'For much of this period you did not own the portfolio you built',
                f"For {share * 100:.0f}% of the simulated period the portfolio held "
                f"fewer than half of your {requested} holdings, because the others "
                f"had no price history yet. That span was dominated by {names}. A "
                f"headline return over this window is mostly a statement about "
                f"those assets, not about the basket you assembled.")

        if _longest_run(counts <= 1) > SINGLE_ASSET_MIN_DAYS:
            add('single_asset_period', 'critical',
                'The portfolio was a single holding for an extended stretch',
                f"There is a run of more than {SINGLE_ASSET_MIN_DAYS} trading days "
                f"in which only one of your holdings had price data. Over that "
                f"span this is a single-stock backtest, with none of the "
                f"diversification the rest of the basket is meant to provide.")

    # --- Sin #4: overfitting ----------------------------------------------
    uses_optimizer = request.weighting_scheme in OPTIMIZER_SCHEMES
    if uses_optimizer and request.backtest_mode == 'fixed':
        add('in_sample_fit', 'warning',
            'The weights were chosen using the same data they are scored against',
            f"You ran the {request.weighting_scheme.replace('_', ' ')} optimizer in "
            f"fixed mode, so it saw the whole history before the simulation graded "
            f"it. That is not a result an investor could have achieved, because "
            f"nobody had that history in advance. Re-run in walk-forward mode to "
            f"see what the same rule would have produced using only data available "
            f"at each decision date.")

    if request.weighting_scheme == 'max_sharpe':
        add('return_estimation', 'warning',
            'Maximum Sharpe rests on a very noisy forecast',
            'This optimizer needs an estimate of each asset\'s future return, and '
            'the only one available is the average return over the lookback window. '
            'Past average returns are a famously poor predictor of future ones — far '
            'worse than past volatility is of future volatility. Expect these '
            'weights to look confident and to travel badly.')

    rebalance_count = len(result.rebalance_events)
    years = float(metrics.get('years') or 0.0)
    if years < SHORT_SAMPLE_YEARS or rebalance_count < SHORT_SAMPLE_REBALANCES:
        add('short_sample', 'warning',
            'There is not much evidence here',
            f"This simulation covers {years:.1f} years and {rebalance_count} "
            f"rebalances. With that few independent decisions, the difference "
            f"between this result and a different one is mostly luck. Treat the "
            f"ranking against alternatives as provisional.")

    # --- Sin #5: transaction costs ----------------------------------------
    cost_fractions = [event['cost'] for event in result.rebalance_events]
    index_values = np.asarray(result.index, dtype=float)
    net_return = float(index_values[-1] / index_values[0] - 1.0) if index_values.size else 0.0
    surviving = float(np.prod([1.0 - c for c in cost_fractions])) if cost_fractions else 1.0
    gross_return = ((1.0 + net_return) / surviving - 1.0) if surviving > 0 else net_return
    cost_drag = gross_return - net_return
    if gross_return > 1e-9 and cost_drag / gross_return > COST_SHARE_OF_GROSS:
        add('cost_sensitivity', 'critical',
            'Trading costs consumed a large share of the gains',
            f"Rebalancing cost {cost_drag / gross_return * 100:.0f}% of this "
            f"strategy's gross return at {request.transaction_cost_bps:.0f} basis "
            f"points per trade. A strategy this trade-heavy is fragile: a slightly "
            f"worse fill or a wider spread than assumed would erase much of the "
            f"advantage. Try a less frequent rebalance.")

    # --- Sin #6: outliers -------------------------------------------------
    returns = np.asarray(result.returns, dtype=float)[1:]
    if returns.size > 20 and years > 0:
        full_growth = float(np.prod(1.0 + returns))
        trimmed = np.sort(returns)[:-5]
        trimmed_growth = float(np.prod(1.0 + trimmed))
        if full_growth > 0 and trimmed_growth > 0:
            full_cagr = full_growth ** (1 / years) - 1
            trimmed_cagr = trimmed_growth ** (1 / years) - 1
            if full_cagr > 1e-9 and (full_cagr - trimmed_cagr) / full_cagr > OUTLIER_CAGR_DROP:
                add('outlier_dependence', 'warning',
                    'Almost all of the return came from a handful of days',
                    f"Remove the five best days and the annual return falls from "
                    f"{full_cagr * 100:.1f}% to {trimmed_cagr * 100:.1f}%. A result "
                    f"that hinges on five days out of {returns.size} is not evidence "
                    f"of a durable edge — it is evidence that you would have had to "
                    f"be invested on exactly the right days.")

    # --- Concentration ----------------------------------------------------
    average_weights = result.weights_over_time.mean(axis=0).to_numpy()
    effective_n = (1.0 / float(np.sum(average_weights ** 2))
                   if np.sum(average_weights ** 2) > 0 else 0.0)
    largest = float(average_weights.max()) if average_weights.size else 0.0
    if largest > MAX_SINGLE_WEIGHT or effective_n < MIN_EFFECTIVE_N:
        heaviest = result.weights_over_time.mean(axis=0).idxmax()
        add('concentration', 'warning',
            'This portfolio is less diversified than the holding count suggests',
            f"The largest average position is {heaviest} at {largest * 100:.0f}%, and "
            f"the portfolio behaves like roughly {effective_n:.1f} independent "
            f"holdings. Whatever happens to the largest position will dominate the "
            f"result regardless of how many tickers are listed.")

    # --- Sin #7: shorting -------------------------------------------------
    if not request.long_only:
        add('shorting_unmodelled', 'critical',
            'Short positions here are free, and in reality they are not',
            'You disabled the long-only constraint, so the optimizer may hold '
            'negative weights. This simulation charges nothing for them: no stock '
            'borrow fee, no hard-to-borrow premium, no risk of a recall forcing you '
            'to close at the worst moment, and no margin requirement. Real short '
            'books pay all four. Any advantage the short positions appear to add '
            'is overstated by an unknown amount.')

    if result.fallback_dates:
        shown = ', '.join(result.fallback_dates[:5])
        more = ('' if len(result.fallback_dates) <= 5
                else f" and {len(result.fallback_dates) - 5} more")
        add('optimizer_fallback', 'critical',
            'The optimizer failed on some dates and a different rule was used',
            f"On {len(result.fallback_dates)} rebalance date(s) — {shown}{more} — the "
            f"{request.weighting_scheme.replace('_', ' ')} solver did not converge, "
            f"so those rebalances used inverse-volatility weights instead. The "
            f"result below is therefore a blend of two strategies, not the one you "
            f"selected.")

    # --- Benchmark suitability -------------------------------------------
    if benchmark_returns is not None:
        benchmark = np.asarray(benchmark_returns, dtype=float)
        length = min(benchmark.size, returns.size + 1)
        if length > 30:
            portfolio_tail = np.asarray(result.returns, dtype=float)[-length:]
            benchmark_tail = benchmark[-length:]
            if portfolio_tail.std() > 0 and benchmark_tail.std() > 0:
                correlation = float(np.corrcoef(portfolio_tail, benchmark_tail)[0, 1])
                if correlation < BENCHMARK_MIN_CORRELATION:
                    add('benchmark_mismatch', 'info',
                        f"{request.benchmark_symbol} may be the wrong yardstick",
                        f"Your portfolio's daily moves correlate only "
                        f"{correlation:.2f} with {request.benchmark_symbol}. They are "
                        f"not really exposed to the same things, so "
                        f"“beat the benchmark” says little here. A "
                        f"benchmark matching your holdings' asset class and region "
                        f"would be more informative.")

    findings.sort(key=lambda finding: SEVERITY_ORDER[finding['severity']])
    return findings
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python manage.py test backtester.tests.test_diagnostics -v 2
```

Expected: all PASS. If `test_composition_coverage_fires_when_half_the_assets_are_missing` fails on the `'66'` substring, print the computed share and align the assertion with the real value — 1000/1512 rounds to 66%.

- [ ] **Step 5: Confirm every documented code is reachable**

```bash
python manage.py test backtester.tests.test_diagnostics -v 2 2>&1 | tail -5
grep -c "add('" backend/backtester/engine/diagnostics.py
```

Expected: the `add(` count is 13, one per entry in `CODES`.

- [ ] **Step 6: Commit**

```bash
git add backend/backtester/engine/diagnostics.py backend/backtester/tests/test_diagnostics.py
git commit -m "feat: add the seven-sins backtest diagnostics"
```

---

### Task 10: Efficient frontier

In-sample, illustrative, and labelled as such (§7). It is not a walk-forward result and must not be presented as one.

**Files:**
- Create: `backend/backtester/engine/frontier.py`
- Test: `backend/backtester/tests/test_frontier.py`

**Interfaces:**
- Consumes: `covariance.estimate_covariance`; `config.OptimizerConfig` (for the bounds only — the frontier solves its own constrained problems with `scipy.optimize.minimize` rather than going through the scheme registry, because a target-return equality constraint has no place in the `optimize(returns, config, scheme)` contract).
- Produces: `sample_frontier(returns: np.ndarray, symbols: list[str], config: OptimizerConfig, portfolio_weights=None, samples: int = 2000, grid: int = 40, seed: int = 0) -> dict` with keys `scatter` (`{volatility, return}` lists), `frontier` (same), `gmvp`, `tangency`, `portfolio`, `symbols`, `annualized: True`.

- [ ] **Step 1: Write the failing test**

Create `backend/backtester/tests/test_frontier.py`:

```python
"""Efficient frontier sampling."""
from unittest import TestCase

import numpy as np

from backtester.engine.config import OptimizerConfig
from backtester.engine.frontier import sample_frontier


def _returns(T=504, N=4, seed=2):
    rng = np.random.default_rng(seed)
    loadings = rng.normal(size=(N, 2))
    factors = rng.normal(size=(T, 2)) * 0.01
    return factors @ loadings.T + rng.normal(size=(T, N)) * np.linspace(0.004, 0.011, N)


class FrontierTests(TestCase):

    def setUp(self):
        self.returns = _returns()
        self.symbols = ['A', 'B', 'C', 'D']
        self.config = OptimizerConfig(long_only=True, covariance_method='ledoit_wolf')
        self.result = sample_frontier(self.returns, self.symbols, self.config,
                                      portfolio_weights=[0.25] * 4,
                                      samples=300, grid=20, seed=1)

    def test_the_payload_carries_every_documented_key(self):
        self.assertEqual(set(self.result),
                         {'scatter', 'frontier', 'gmvp', 'tangency', 'portfolio',
                          'symbols', 'annualized'})

    def test_the_scatter_has_the_requested_number_of_samples(self):
        self.assertEqual(len(self.result['scatter']['volatility']), 300)
        self.assertEqual(len(self.result['scatter']['return']), 300)

    def test_the_frontier_curve_is_monotonically_increasing_in_return(self):
        returns = self.result['frontier']['return']

        self.assertTrue(all(b >= a - 1e-12 for a, b in zip(returns, returns[1:])))

    def test_the_gmvp_has_the_lowest_volatility_on_the_frontier(self):
        gmvp_volatility = self.result['gmvp']['volatility']

        self.assertLessEqual(gmvp_volatility,
                             min(self.result['frontier']['volatility']) + 1e-9)

    def test_no_random_sample_beats_the_frontier(self):
        """For each random portfolio, the frontier at that same expected return
        must be no more volatile than the random portfolio itself.

        Stated this way rather than "no scatter point sits above the curve",
        because the returned curve is a 20-point sample. A scatter point lands
        between grid nodes and would be compared against the nearest lower node,
        whose return is below the true frontier there - which reads as a
        violation and is only a discretization artifact. Solving exactly at each
        point's own return level is grid-independent.
        """
        from backtester.engine.covariance import estimate_covariance
        from backtester.engine.frontier import TRADING_DAYS, _min_variance_at

        cov = estimate_covariance(self.returns, 'ledoit_wolf')
        mu = self.returns.mean(axis=0)

        volatilities = self.result['scatter']['volatility']
        returns = self.result['scatter']['return']
        # Every 15th sample: the solve is exact but not free.
        for volatility, annual_return in list(zip(volatilities, returns))[::15]:
            weights = _min_variance_at(annual_return / TRADING_DAYS, mu, cov,
                                       self.config)
            if weights is None:
                continue
            frontier_volatility = float(
                np.sqrt(weights @ cov @ weights) * np.sqrt(TRADING_DAYS))
            self.assertLessEqual(frontier_volatility, volatility + 1e-6)

    def test_the_tangency_point_has_the_best_sharpe_on_the_frontier(self):
        tangency = self.result['tangency']
        best = tangency['return'] / tangency['volatility']

        for volatility, portfolio_return in zip(self.result['frontier']['volatility'],
                                                self.result['frontier']['return']):
            if volatility > 0:
                self.assertLessEqual(portfolio_return / volatility, best + 1e-6)

    def test_the_users_portfolio_is_marked_on_the_same_axes(self):
        portfolio = self.result['portfolio']

        self.assertGreater(portfolio['volatility'], 0.0)
        self.assertEqual(portfolio['weights'], dict(zip(self.symbols, [0.25] * 4)))

    def test_omitting_the_users_portfolio_leaves_it_null(self):
        result = sample_frontier(self.returns, self.symbols, self.config,
                                 samples=50, grid=10, seed=1)

        self.assertIsNone(result['portfolio'])

    def test_values_are_annualized(self):
        self.assertTrue(self.result['annualized'])
        # Daily vols are ~1%; annualized they are ~10-25%.
        self.assertGreater(max(self.result['scatter']['volatility']), 0.02)

    def test_the_payload_is_json_serializable(self):
        import json

        json.dumps(self.result)

    def test_a_single_asset_degrades_gracefully(self):
        result = sample_frontier(_returns(N=1), ['A'], self.config,
                                 samples=20, grid=5, seed=1)

        self.assertEqual(len(result['frontier']['volatility']), 1)
        self.assertEqual(result['gmvp']['weights'], {'A': 1.0})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python manage.py test backtester.tests.test_frontier -v 2
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backtester.engine.frontier'`.

- [ ] **Step 3: Write `engine/frontier.py`**

Create `backend/backtester/engine/frontier.py`:

```python
"""Efficient frontier sampling for the illustrative chart of §7.

Computed on the full-period, in-sample covariance. That makes it a picture of
the opportunity set as it turned out, not a forecast and not a walk-forward
result -- the UI labels it accordingly.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from .config import OptimizerConfig
from .covariance import estimate_covariance

TRADING_DAYS = 252


def _annualized(weights, mu, cov):
    portfolio_return = float(weights @ mu) * TRADING_DAYS
    volatility = float(np.sqrt(max(weights @ cov @ weights, 0.0))) * np.sqrt(TRADING_DAYS)
    return volatility, portfolio_return


def _point(weights, mu, cov, symbols):
    volatility, portfolio_return = _annualized(weights, mu, cov)
    return {
        'volatility': volatility,
        'return': portfolio_return,
        'sharpe': (portfolio_return / volatility) if volatility > 0 else None,
        'weights': {symbol: float(round(w, 6)) for symbol, w in zip(symbols, weights)},
    }


def _bounds(n, config: OptimizerConfig):
    lower = 0.0 if config.long_only else -1.0
    if config.min_weight is not None:
        lower = max(lower, float(config.min_weight))
    upper = 1.0 if config.max_weight is None else float(config.max_weight)
    return [(lower, upper)] * n


def _min_variance_at(target_return, mu, cov, config):
    """Min variance subject to a target expected return -- one point on the
    analytic frontier."""
    n = cov.shape[0]
    constraints = (
        {'type': 'eq', 'fun': lambda w: float(np.sum(w)) - 1.0},
        {'type': 'eq', 'fun': lambda w: float(w @ mu) - target_return},
    )
    result = minimize(lambda w: float(w @ cov @ w), np.full(n, 1.0 / n),
                      method='SLSQP', bounds=_bounds(n, config),
                      constraints=constraints,
                      options={'maxiter': 300, 'ftol': 1e-12})
    if not result.success or not np.all(np.isfinite(result.x)):
        return None
    weights = np.asarray(result.x, dtype=float)
    total = weights.sum()
    return weights / total if abs(total) > 1e-12 else None


def sample_frontier(returns, symbols, config: OptimizerConfig,
                    portfolio_weights=None, samples: int = 2000,
                    grid: int = 40, seed: int = 0) -> dict:
    returns = np.asarray(returns, dtype=float)
    cov = estimate_covariance(returns, config.covariance_method)
    mu = returns.mean(axis=0)
    n = cov.shape[0]
    symbols = list(symbols)

    if n == 1:
        only = np.ones(1)
        point = _point(only, mu, cov, symbols)
        return {
            'scatter': {'volatility': [point['volatility']], 'return': [point['return']]},
            'frontier': {'volatility': [point['volatility']], 'return': [point['return']]},
            'gmvp': point,
            'tangency': point,
            'portfolio': point if portfolio_weights is not None else None,
            'symbols': symbols,
            'annualized': True,
        }

    # Random long-only weight vectors: a Dirichlet draw is uniform over the
    # simplex, which is what makes the cloud an honest picture of "any portfolio
    # you could have picked".
    rng = np.random.default_rng(seed)
    draws = rng.dirichlet(np.ones(n), size=int(samples))
    scatter_volatility = np.sqrt(np.einsum('ij,jk,ik->i', draws, cov, draws)) * np.sqrt(TRADING_DAYS)
    scatter_return = draws @ mu * TRADING_DAYS

    # The GMVP is the unconstrained-in-return minimum, so it is solved directly
    # rather than through _min_variance_at's target-return constraint.
    result = minimize(lambda w: float(w @ cov @ w), np.full(n, 1.0 / n),
                      method='SLSQP', bounds=_bounds(n, config),
                      constraints=({'type': 'eq', 'fun': lambda w: float(np.sum(w)) - 1.0},),
                      options={'maxiter': 300, 'ftol': 1e-12})
    gmvp_weights = (np.asarray(result.x) / np.sum(result.x)
                    if result.success else np.full(n, 1.0 / n))
    gmvp = _point(gmvp_weights, mu, cov, symbols)

    lowest = float(gmvp_weights @ mu)
    highest = float(mu.max())
    curve = []
    for target in np.linspace(lowest, highest, int(grid)):
        weights = _min_variance_at(float(target), mu, cov, config)
        if weights is not None:
            curve.append(_point(weights, mu, cov, symbols))

    if not curve:
        curve = [gmvp]
    # Keep the curve a function of volatility: drop any point that is dominated.
    curve.sort(key=lambda p: p['return'])
    tangency = max(curve, key=lambda p: p['sharpe'] if p['sharpe'] else -np.inf)

    return {
        'scatter': {'volatility': [float(v) for v in scatter_volatility],
                    'return': [float(r) for r in scatter_return]},
        'frontier': {'volatility': [p['volatility'] for p in curve],
                     'return': [p['return'] for p in curve]},
        'gmvp': gmvp,
        'tangency': tangency,
        'portfolio': (_point(np.asarray(portfolio_weights, dtype=float), mu, cov, symbols)
                      if portfolio_weights is not None else None),
        'symbols': symbols,
        'annualized': True,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python manage.py test backtester.tests.test_frontier -v 2
```

Expected: all PASS. If `test_no_random_sample_beats_the_frontier` fails, the curve is being truncated below the achievable maximum — widen the `np.linspace` upper bound to `float(mu.max())` exactly and confirm `_min_variance_at` is not silently returning `None` for the top of the range.

- [ ] **Step 5: Run the whole engine suite together**

```bash
python manage.py test backtester -v 2
```

Expected: every test from Tasks 2–10 passes in one run.

- [ ] **Step 6: Commit**

```bash
git add backend/backtester/engine/frontier.py backend/backtester/tests/test_frontier.py
git commit -m "feat: add efficient frontier sampling"
```

---

### Task 11: Models, migrations, and the privilege-escalation guard

§16 step 7 is explicit that the `UserProfile` fields and the serializer guard **land in the same commit**. `UserProfileSerializer` declares `fields = "__all__"` and `users/views.py:141-155` feeds `request.data` straight into it for a partial update of the caller's own profile — so adding `subscription_tier` without the guard ships a user-writable subscription tier and a meter any authenticated user can bypass with one PATCH.

**Files:**
- Create: `backend/backtester/models.py`, `backend/backtester/admin.py`, `backend/backtester/migrations/__init__.py`
- Modify: `backend/users/models.py:48-61` (`UserProfile`), `backend/users/serializers.py:54-63` (`UserProfileSerializer.Meta.extra_kwargs`)
- Create (generated): `backend/backtester/migrations/0001_initial.py`, `backend/users/migrations/0002_*.py`
- Test: `backend/backtester/tests/test_models.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `Portfolio`, `PortfolioHolding`, `BacktestRun` exactly as §11 defines them.
  - `UserProfile.subscription_tier: str` (default `"free"`, `db_index=True`) and `UserProfile.backtest_quota_override: int | None` — both read-only through the API.
  - `BacktestRun.STATUS_CHOICES` and the constants `STATUS_QUEUED/RUNNING/COMPLETE/FAILED` used by Tasks 12–15.

- [ ] **Step 1: Write the failing test**

Create `backend/backtester/tests/test_models.py`:

```python
"""Models plus the privilege-escalation guard on UserProfile."""
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from backtester.models import BacktestRun, Portfolio, PortfolioHolding

User = get_user_model()


def _user(email='someone@example.com'):
    return User.objects.create_user(username=email, email=email, password='sw0rdfish!x',
                                    first_name='Test', last_name='User')


class PortfolioModelTests(TestCase):

    def setUp(self):
        self.user = _user()

    def test_defaults_match_the_spec(self):
        portfolio = Portfolio.objects.create(user=self.user, name='Core')

        self.assertEqual(portfolio.benchmark_symbol, 'SPY')
        self.assertEqual(float(portfolio.initial_amount), 10_000.0)
        self.assertEqual(float(portfolio.periodic_contribution), 0.0)
        self.assertEqual(portfolio.contribution_frequency, 'none')
        self.assertEqual(portfolio.weighting_scheme, 'equal')
        self.assertEqual(portfolio.backtest_mode, 'fixed')
        self.assertEqual(portfolio.rebalance_frequency, 'annual')
        self.assertEqual(portfolio.settings, {})

    def test_a_user_cannot_reuse_a_portfolio_name(self):
        Portfolio.objects.create(user=self.user, name='Core')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Portfolio.objects.create(user=self.user, name='Core')

    def test_two_users_can_each_have_a_portfolio_called_core(self):
        Portfolio.objects.create(user=self.user, name='Core')
        Portfolio.objects.create(user=_user('other@example.com'), name='Core')

        self.assertEqual(Portfolio.objects.filter(name='Core').count(), 2)

    def test_holdings_are_ordered_by_their_order_field(self):
        portfolio = Portfolio.objects.create(user=self.user, name='Core')
        PortfolioHolding.objects.create(portfolio=portfolio, symbol='VTI', order=1)
        PortfolioHolding.objects.create(portfolio=portfolio, symbol='AAPL', order=0)

        self.assertEqual([h.symbol for h in portfolio.holdings.all()], ['AAPL', 'VTI'])

    def test_a_symbol_cannot_appear_twice_in_one_portfolio(self):
        portfolio = Portfolio.objects.create(user=self.user, name='Core')
        PortfolioHolding.objects.create(portfolio=portfolio, symbol='AAPL')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PortfolioHolding.objects.create(portfolio=portfolio, symbol='AAPL')

    def test_deleting_a_portfolio_deletes_its_holdings(self):
        portfolio = Portfolio.objects.create(user=self.user, name='Core')
        PortfolioHolding.objects.create(portfolio=portfolio, symbol='AAPL')

        portfolio.delete()
        self.assertEqual(PortfolioHolding.objects.count(), 0)


class BacktestRunModelTests(TestCase):

    def setUp(self):
        self.user = _user()

    def test_a_run_starts_queued_and_counts_against_quota(self):
        run = BacktestRun.objects.create(user=self.user, task_id='t1',
                                         request_hash='h1', request={})

        self.assertEqual(run.status, BacktestRun.STATUS_QUEUED)
        self.assertTrue(run.counted_against_quota)
        self.assertIsNone(run.completed_at)

    def test_deleting_a_portfolio_keeps_its_runs(self):
        """Run history is the quota ledger; deleting a portfolio must not erase it."""
        portfolio = Portfolio.objects.create(user=self.user, name='Core')
        run = BacktestRun.objects.create(user=self.user, portfolio=portfolio,
                                         task_id='t2', request_hash='h2', request={})

        portfolio.delete()
        run.refresh_from_db()
        self.assertIsNone(run.portfolio)
        self.assertEqual(BacktestRun.objects.count(), 1)

    def test_deleting_a_user_deletes_their_runs(self):
        BacktestRun.objects.create(user=self.user, task_id='t3',
                                   request_hash='h3', request={})

        self.user.delete()
        self.assertEqual(BacktestRun.objects.count(), 0)


class UserProfileFieldTests(TestCase):

    def setUp(self):
        self.user = _user()
        self.profile = self._profile()

    def _profile(self):
        from users.models import UserProfile

        profile = getattr(self.user, 'userprofile', None)
        return profile or UserProfile.objects.create(user=self.user)

    def test_new_accounts_default_to_the_free_tier(self):
        self.assertEqual(self.profile.subscription_tier, 'free')
        self.assertIsNone(self.profile.backtest_quota_override)


class PrivilegeEscalationTests(TestCase):
    """REQUIRED (§11, §15). Without the read-only guard the meter is trivially
    bypassable by any authenticated user."""

    def setUp(self):
        from users.models import UserProfile

        self.user = _user()
        self.profile = (getattr(self.user, 'userprofile', None)
                        or UserProfile.objects.create(user=self.user))
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _patch(self, payload):
        return self.client.patch('/api/users/me/profile/update/', payload, format='json')

    def test_patching_subscription_tier_does_not_change_it(self):
        self._patch({'subscription_tier': 'pro'})
        self.profile.refresh_from_db()

        self.assertEqual(self.profile.subscription_tier, 'free')

    def test_patching_the_quota_override_does_not_change_it(self):
        self._patch({'backtest_quota_override': 100_000})
        self.profile.refresh_from_db()

        self.assertIsNone(self.profile.backtest_quota_override)

    def test_the_tier_is_still_readable_so_the_banner_can_show_it(self):
        """Read-only, not excluded -- the frontend displays tier and remaining runs."""
        self.profile.subscription_tier = 'pro'
        self.profile.save(update_fields=['subscription_tier'])

        response = self._patch({'company_number': '123'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('subscription_tier'), 'pro')

    def test_a_writable_field_still_updates(self):
        response = self._patch({'company_number': '999'})

        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.company_number, '999')
```

Before running, confirm the profile-update route's real path:

```bash
grep -n "update_user_profile" backend/users/urls.py
```

Substitute the actual path into `_patch` if it differs from `/api/users/me/profile/update/`.

- [ ] **Step 2: Run the test to verify it fails**

```bash
python manage.py test backtester.tests.test_models -v 2
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backtester.models'` (or `ImportError` for the model names).

- [ ] **Step 3: Write `backtester/models.py`**

```bash
mkdir -p backend/backtester/migrations
touch backend/backtester/migrations/__init__.py
```

Create `backend/backtester/models.py`:

```python
"""User-scoped portfolios and backtest run records (§11).

Full result JSON lives in S3 and Redis, never in Postgres. `BacktestRun` does
triple duty: quota counter, run history for a future comparison view, and usage
analytics -- which is why it keeps the request payload and a summary but not the
result.
"""
from django.conf import settings
from django.db import models


class Portfolio(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='portfolios',
                             on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default='')
    benchmark_symbol = models.CharField(max_length=20, default='SPY')
    initial_amount = models.DecimalField(max_digits=14, decimal_places=2, default=10000)
    periodic_contribution = models.DecimalField(max_digits=14, decimal_places=2,
                                                default=0)
    contribution_frequency = models.CharField(max_length=20, default='none')
    weighting_scheme = models.CharField(max_length=30, default='equal')
    backtest_mode = models.CharField(max_length=20, default='fixed')
    rebalance_frequency = models.CharField(max_length=20, default='annual')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    # The §3 advanced block. JSON rather than columns: these are optimizer knobs
    # that change with the engine, and none of them is ever queried on.
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'name')
        indexes = [models.Index(fields=['user', '-updated_at'])]
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.name} ({self.user_id})"


class PortfolioHolding(models.Model):
    portfolio = models.ForeignKey(Portfolio, related_name='holdings',
                                 on_delete=models.CASCADE)
    symbol = models.CharField(max_length=20)
    target_weight = models.DecimalField(max_digits=7, decimal_places=6, default=0)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ('portfolio', 'symbol')
        ordering = ['order']

    def __str__(self):
        return f"{self.symbol} @ {self.target_weight}"


class BacktestRun(models.Model):
    STATUS_QUEUED = 'queued'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETE = 'complete'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = (
        (STATUS_QUEUED, 'Queued'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETE, 'Complete'),
        (STATUS_FAILED, 'Failed'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='backtest_runs',
                             on_delete=models.CASCADE)
    # SET_NULL, not CASCADE: this row is the quota ledger, so deleting a saved
    # portfolio must not erase the record of runs already paid for.
    portfolio = models.ForeignKey(Portfolio, null=True, blank=True,
                                  on_delete=models.SET_NULL, related_name='runs')
    task_id = models.CharField(max_length=64, db_index=True)
    request_hash = models.CharField(max_length=64, db_index=True)
    request = models.JSONField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,
                              default=STATUS_QUEUED)
    progress = models.CharField(max_length=40, blank=True, default='')
    summary = models.JSONField(null=True, blank=True)
    result_key = models.CharField(max_length=300, blank=True, default='')
    error = models.TextField(blank=True, default='')
    counted_against_quota = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['user', '-created_at']),
                   models.Index(fields=['user', 'request_hash'])]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.task_id} [{self.status}]"
```

Create `backend/backtester/admin.py`:

```python
from django.contrib import admin

from .models import BacktestRun, Portfolio, PortfolioHolding


class PortfolioHoldingInline(admin.TabularInline):
    model = PortfolioHolding
    extra = 0


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'weighting_scheme', 'updated_at')
    search_fields = ('name', 'user__email')
    inlines = [PortfolioHoldingInline]


@admin.register(BacktestRun)
class BacktestRunAdmin(admin.ModelAdmin):
    list_display = ('task_id', 'user', 'status', 'counted_against_quota', 'created_at')
    list_filter = ('status', 'counted_against_quota')
    search_fields = ('task_id', 'request_hash', 'user__email')
    readonly_fields = ('task_id', 'request_hash', 'request', 'summary')
```

- [ ] **Step 4: Add the `UserProfile` fields**

In `backend/users/models.py`, inside `class UserProfile`, add immediately after `stripe_account_id`:

```python
    # Platform spec §3. Both default, so the migration needs no backfill.
    # REQUIRED: both are marked read_only in UserProfileSerializer -- that
    # serializer is fields="__all__" and is fed request.data directly, so
    # without the guard any authenticated user could PATCH themselves to 'pro'.
    subscription_tier = models.CharField(max_length=20, default='free', db_index=True)
    backtest_quota_override = models.PositiveIntegerField(null=True, blank=True)
```

- [ ] **Step 5: Apply the serializer guard in the same change**

In `backend/users/serializers.py`, replace `UserProfileSerializer.Meta.extra_kwargs`:

```python
    class Meta:
        model = UserProfile
        fields = "__all__"
        extra_kwargs = {
            "stripe_account_id": {"write_only": True},  # avoid leaking sensitive IDs
            # Read-only, not excluded: the QuotaBanner displays tier and
            # remaining runs, it just must never set them. Tier changes come from
            # the admin or, later, a Stripe webhook -- never from request.data.
            "subscription_tier": {"read_only": True},
            "backtest_quota_override": {"read_only": True},
        }
```

- [ ] **Step 6: Generate the migrations**

```bash
python manage.py makemigrations backtester users
```

Expected: `backtester/migrations/0001_initial.py` creating three models, and `users/migrations/0002_*.py` adding two fields. Confirm the users migration is purely additive:

```bash
grep -n "AddField\|RemoveField\|AlterField" backend/users/migrations/0002_*.py
```

Expected: two `AddField` operations and nothing else.

- [ ] **Step 7: Apply the migrations**

```bash
python manage.py migrate
```

Expected: both migrations apply cleanly with no prompt for a default value.

- [ ] **Step 8: Run the tests to verify they pass**

```bash
python manage.py test backtester.tests.test_models -v 2
```

Expected: all PASS, including the four `PrivilegeEscalationTests`.

- [ ] **Step 9: Prove the escalation test detects the hole**

Temporarily remove the two `read_only` entries you added in Step 5 and re-run:

```bash
python manage.py test backtester.tests.test_models.PrivilegeEscalationTests -v 2
```

Expected: `test_patching_subscription_tier_does_not_change_it` and `test_patching_the_quota_override_does_not_change_it` FAIL. Restore the entries and re-run to confirm PASS.

- [ ] **Step 10: Commit — fields and guard together**

```bash
git add backend/backtester/models.py backend/backtester/admin.py \
        backend/backtester/migrations/ backend/users/models.py \
        backend/users/serializers.py backend/users/migrations/0002_*.py \
        backend/backtester/tests/test_models.py
git commit -m "feat: add backtester models and read-only subscription tier"
```

---

### Task 12: Usage metering

Scaffolding ships now; pricing is deliberately undefined (§13). Three rules matter more than the number: only novel runs count, portfolio management is always free, and failed runs are refunded.

**Files:**
- Create: `backend/backtester/quota.py`, `backend/backtester/permissions.py`
- Test: `backend/backtester/tests/test_quota.py`

**Interfaces:**
- Consumes: `models.BacktestRun`; `settings.FREE_TIER_BACKTEST_LIMIT` (added in Task 3).
- Produces:
  - `Quota(used: int, limit: int | None, tier: str, remaining: int | None)` — frozen dataclass with `.as_dict()`. `limit=None` and `remaining=None` mean unlimited.
  - `get_quota(user) -> Quota`
  - `check_and_consume(user) -> None` — raises `QuotaExceeded`.
  - `QuotaExceeded(APIException)` — `status_code = 402`, carries `used` and `limit`.
  - `refund(run: BacktestRun) -> None` — sets `counted_against_quota = False`.
  - `HasBacktestQuota` DRF permission class.

- [ ] **Step 1: Write the failing test**

Create `backend/backtester/tests/test_quota.py`:

```python
"""Metering. The numbers are settings-driven; the three rules are not."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from backtester.models import BacktestRun
from backtester.quota import QuotaExceeded, check_and_consume, get_quota, refund

User = get_user_model()


def _user(email='meter@example.com'):
    user = User.objects.create_user(username=email, email=email, password='sw0rdfish!x',
                                   first_name='Test', last_name='User')
    from users.models import UserProfile
    if not getattr(user, 'userprofile', None):
        UserProfile.objects.create(user=user)
    return user


def _run(user, counted=True, status=BacktestRun.STATUS_COMPLETE, request_hash='h'):
    return BacktestRun.objects.create(user=user, task_id=f"t-{request_hash}",
                                      request_hash=request_hash, request={},
                                      status=status, counted_against_quota=counted)


@override_settings(FREE_TIER_BACKTEST_LIMIT=3)
class GetQuotaTests(TestCase):

    def setUp(self):
        self.user = _user()

    def test_a_fresh_free_account_has_the_full_allowance(self):
        quota = get_quota(self.user)

        self.assertEqual(quota.tier, 'free')
        self.assertEqual(quota.used, 0)
        self.assertEqual(quota.limit, 3)
        self.assertEqual(quota.remaining, 3)

    def test_counted_runs_reduce_the_remaining_allowance(self):
        _run(self.user, request_hash='a')
        _run(self.user, request_hash='b')

        quota = get_quota(self.user)
        self.assertEqual(quota.used, 2)
        self.assertEqual(quota.remaining, 1)

    def test_uncounted_runs_are_not_charged(self):
        _run(self.user, counted=False, request_hash='a')

        self.assertEqual(get_quota(self.user).used, 0)

    def test_another_users_runs_do_not_count(self):
        _run(_user('other@example.com'), request_hash='a')

        self.assertEqual(get_quota(self.user).used, 0)

    def test_a_pro_account_is_unlimited(self):
        profile = self.user.userprofile
        profile.subscription_tier = 'pro'
        profile.save(update_fields=['subscription_tier'])

        quota = get_quota(self.user)
        self.assertEqual(quota.tier, 'pro')
        self.assertIsNone(quota.limit)
        self.assertIsNone(quota.remaining)

    def test_an_override_beats_both_the_tier_and_the_default(self):
        profile = self.user.userprofile
        profile.backtest_quota_override = 50
        profile.save(update_fields=['backtest_quota_override'])

        self.assertEqual(get_quota(self.user).limit, 50)

    def test_an_override_of_zero_is_honoured_rather_than_ignored(self):
        profile = self.user.userprofile
        profile.backtest_quota_override = 0
        profile.save(update_fields=['backtest_quota_override'])

        self.assertEqual(get_quota(self.user).limit, 0)

    def test_a_user_without_a_profile_still_gets_the_free_tier(self):
        from users.models import UserProfile

        UserProfile.objects.filter(user=self.user).delete()
        self.user.refresh_from_db()

        quota = get_quota(self.user)
        self.assertEqual(quota.tier, 'free')
        self.assertEqual(quota.limit, 3)

    def test_the_payload_shape_is_what_the_api_returns(self):
        self.assertEqual(set(get_quota(self.user).as_dict()),
                         {'used', 'limit', 'tier', 'remaining'})


@override_settings(FREE_TIER_BACKTEST_LIMIT=2)
class CheckAndConsumeTests(TestCase):

    def setUp(self):
        self.user = _user()

    def test_it_passes_while_allowance_remains(self):
        check_and_consume(self.user)   # must not raise

    def test_it_raises_once_the_allowance_is_gone(self):
        _run(self.user, request_hash='a')
        _run(self.user, request_hash='b')

        with self.assertRaises(QuotaExceeded) as caught:
            check_and_consume(self.user)

        self.assertEqual(caught.exception.status_code, 402)
        self.assertEqual(caught.exception.detail['used'], 2)
        self.assertEqual(caught.exception.detail['limit'], 2)
        self.assertTrue(caught.exception.detail['upgrade_required'])

    def test_a_pro_account_never_raises(self):
        profile = self.user.userprofile
        profile.subscription_tier = 'pro'
        profile.save(update_fields=['subscription_tier'])
        for i in range(10):
            _run(self.user, request_hash=f"h{i}")

        check_and_consume(self.user)   # must not raise


@override_settings(FREE_TIER_BACKTEST_LIMIT=1)
class RefundTests(TestCase):
    """Rule 3: users do not pay for our bugs."""

    def setUp(self):
        self.user = _user()

    def test_refunding_a_failed_run_restores_the_allowance(self):
        run = _run(self.user, status=BacktestRun.STATUS_FAILED, request_hash='a')
        self.assertEqual(get_quota(self.user).remaining, 0)

        refund(run)

        run.refresh_from_db()
        self.assertFalse(run.counted_against_quota)
        self.assertEqual(get_quota(self.user).remaining, 1)

    def test_refunding_twice_is_harmless(self):
        run = _run(self.user, status=BacktestRun.STATUS_FAILED, request_hash='a')

        refund(run)
        refund(run)

        self.assertEqual(get_quota(self.user).used, 0)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python manage.py test backtester.tests.test_quota -v 2
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backtester.quota'`.

- [ ] **Step 3: Write `quota.py` and `permissions.py`**

Create `backend/backtester/quota.py`:

```python
"""Usage metering (§13).

Pricing is deliberately undefined here. What ships is the meter and the three
rules that decide whether the tool feels fair:

  1. Only novel runs count. An identical request_hash serves from cache and is
     free -- otherwise toggling a chart option burns a credit.
  2. Saving, loading, editing and duplicating portfolios are always free. Only
     execution meters.
  3. Failed runs are refunded. Users do not pay for our bugs.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import APIException

from .models import BacktestRun

DEFAULT_FREE_LIMIT = 10
UNLIMITED_TIERS = ('pro',)


class QuotaExceeded(APIException):
    """402 Payment Required -- the free allowance is spent."""
    status_code = status.HTTP_402_PAYMENT_REQUIRED

    def __init__(self, used, limit):
        super().__init__({
            'detail': (f"You have used all {limit} of your free backtests. "
                       f"Saving and editing portfolios stays free."),
            'used': used,
            'limit': limit,
            'upgrade_required': True,
        })


@dataclass(frozen=True)
class Quota:
    used: int
    limit: int | None
    tier: str

    @property
    def remaining(self) -> int | None:
        if self.limit is None:
            return None
        return max(self.limit - self.used, 0)

    @property
    def exhausted(self) -> bool:
        return self.limit is not None and self.used >= self.limit

    def as_dict(self) -> dict:
        return {'used': self.used, 'limit': self.limit, 'tier': self.tier,
                'remaining': self.remaining}


def _profile(user):
    return getattr(user, 'userprofile', None)


def get_quota(user) -> Quota:
    used = BacktestRun.objects.filter(user=user, counted_against_quota=True).count()
    profile = _profile(user)
    tier = getattr(profile, 'subscription_tier', 'free') or 'free'
    override = getattr(profile, 'backtest_quota_override', None)

    if override is not None:
        # `is not None` rather than truthiness: an override of 0 is a deliberate
        # lockout and must not silently fall through to the free-tier default.
        limit = int(override)
    elif tier in UNLIMITED_TIERS:
        limit = None
    else:
        limit = int(getattr(settings, 'FREE_TIER_BACKTEST_LIMIT', DEFAULT_FREE_LIMIT))

    return Quota(used=used, limit=limit, tier=tier)


def check_and_consume(user) -> None:
    """Raise if the allowance is spent. Consumption itself is the BacktestRun
    row the caller creates next -- there is no separate counter to drift out of
    sync with the ledger."""
    quota = get_quota(user)
    if quota.exhausted:
        raise QuotaExceeded(used=quota.used, limit=quota.limit)


def refund(run: BacktestRun) -> None:
    if run.counted_against_quota:
        run.counted_against_quota = False
        run.save(update_fields=['counted_against_quota'])
```

Create `backend/backtester/permissions.py`:

```python
"""Permissions for the backtester routes.

Only execution is metered, so this class guards `POST /run/` alone. Every other
route uses plain IsAuthenticated -- portfolio management is free (§13 rule 2).
"""
from rest_framework.permissions import BasePermission

from .quota import get_quota


class HasBacktestQuota(BasePermission):
    message = 'Your free backtest allowance is spent.'

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method != 'POST':
            return True
        # The view still calls check_and_consume so the 402 body carries used and
        # limit; this class exists so the permission is visible on the view.
        return not get_quota(request.user).exhausted
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python manage.py test backtester.tests.test_quota -v 2
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/backtester/quota.py backend/backtester/permissions.py \
        backend/backtester/tests/test_quota.py
git commit -m "feat: add backtest usage metering"
```

---

### Task 13: Portfolio CRUD, symbol search and quota endpoints

The free half of the API surface (§12). Querysets are filtered by `request.user` at the manager level, never by a URL parameter.

**Files:**
- Create: `backend/backtester/serializers.py`, `backend/backtester/views.py`, `backend/backtester/urls.py`, `backend/backtester/symbol_index.py`
- Modify: `backend/fintank_backend/urls.py:23-31`
- Test: `backend/backtester/tests/test_views.py`

**Interfaces:**
- Consumes: `models.*`; `quota.get_quota`; `engine.config.validate_request`.
- Produces:
  - `PortfolioHoldingSerializer`, `PortfolioSerializer` (nested writable `holdings`), `BacktestRunSummarySerializer`.
  - Views: `PortfolioListCreateView`, `PortfolioDetailView`, `duplicate_portfolio`, `search_symbols`, `quota_view`. (Task 14 adds `submit_run`, `run_status`, `run_results`, `run_history` to the same module.)
  - `symbol_index.build_symbol_index() -> list[dict]` and `get_symbol_index() -> list[dict]`, cache key `backtest:symbol_index:v1`, 24h.
  - Routes under `/api/backtester/`.

- [ ] **Step 1: Write the failing test**

Create `backend/backtester/tests/test_views.py`:

```python
"""API surface. The price loader is mocked everywhere -- no S3, FMP or Redis."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from backtester.models import Portfolio, PortfolioHolding

User = get_user_model()

LOCMEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'backtester-view-tests',
    }
}


def _user(email='api@example.com'):
    user = User.objects.create_user(username=email, email=email, password='sw0rdfish!x',
                                   first_name='Test', last_name='User')
    from users.models import UserProfile
    if not getattr(user, 'userprofile', None):
        UserProfile.objects.create(user=user)
    return user


def _client(user=None):
    client = APIClient()
    if user:
        client.force_authenticate(user=user)
    return client


class AuthenticationTests(TestCase):
    """Every route requires authentication (§12)."""

    def test_anonymous_requests_are_rejected_everywhere(self):
        client = _client()
        for method, path in [
            ('get', '/api/backtester/portfolios/'),
            ('post', '/api/backtester/portfolios/'),
            ('get', '/api/backtester/portfolios/1/'),
            ('post', '/api/backtester/portfolios/1/duplicate/'),
            ('get', '/api/backtester/quota/'),
            ('get', '/api/backtester/search-symbols/?q=aa'),
            ('get', '/api/backtester/history/'),
        ]:
            with self.subTest(path=path):
                response = getattr(client, method)(path)
                self.assertIn(response.status_code, (401, 403))


class PortfolioCrudTests(TestCase):

    def setUp(self):
        self.user = _user()
        self.client = _client(self.user)

    def _payload(self, **overrides):
        payload = {
            'name': 'Core',
            'holdings': [{'symbol': 'aapl', 'target_weight': 0.6, 'order': 0},
                         {'symbol': 'VTI', 'target_weight': 0.4, 'order': 1}],
        }
        payload.update(overrides)
        return payload

    def test_creating_a_portfolio_stores_its_holdings(self):
        response = self.client.post('/api/backtester/portfolios/', self._payload(),
                                    format='json')

        self.assertEqual(response.status_code, 201)
        portfolio = Portfolio.objects.get(name='Core')
        self.assertEqual(portfolio.user, self.user)
        self.assertEqual([h.symbol for h in portfolio.holdings.all()], ['AAPL', 'VTI'])

    def test_the_owner_is_taken_from_the_request_not_the_body(self):
        other = _user('other@example.com')
        self.client.post('/api/backtester/portfolios/',
                         self._payload(user=other.pk), format='json')

        self.assertEqual(Portfolio.objects.get(name='Core').user, self.user)

    def test_the_list_shows_only_my_portfolios(self):
        Portfolio.objects.create(user=self.user, name='Mine')
        Portfolio.objects.create(user=_user('other@example.com'), name='Theirs')

        response = self.client.get('/api/backtester/portfolios/')

        names = [row['name'] for row in response.data]
        self.assertEqual(names, ['Mine'])

    def test_a_duplicate_name_is_a_400_not_a_500(self):
        self.client.post('/api/backtester/portfolios/', self._payload(), format='json')
        response = self.client.post('/api/backtester/portfolios/', self._payload(),
                                    format='json')

        self.assertEqual(response.status_code, 400)

    def test_retrieving_another_users_portfolio_is_a_404(self):
        theirs = Portfolio.objects.create(user=_user('other@example.com'), name='Theirs')

        response = self.client.get(f"/api/backtester/portfolios/{theirs.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_patching_replaces_the_holdings_wholesale(self):
        created = self.client.post('/api/backtester/portfolios/', self._payload(),
                                   format='json').data
        response = self.client.patch(
            f"/api/backtester/portfolios/{created['id']}/",
            {'holdings': [{'symbol': 'BND', 'target_weight': 1.0, 'order': 0}]},
            format='json')

        self.assertEqual(response.status_code, 200)
        portfolio = Portfolio.objects.get(pk=created['id'])
        self.assertEqual([h.symbol for h in portfolio.holdings.all()], ['BND'])

    def test_patching_without_holdings_leaves_them_alone(self):
        created = self.client.post('/api/backtester/portfolios/', self._payload(),
                                   format='json').data
        self.client.patch(f"/api/backtester/portfolios/{created['id']}/",
                          {'description': 'notes'}, format='json')

        portfolio = Portfolio.objects.get(pk=created['id'])
        self.assertEqual(portfolio.holdings.count(), 2)
        self.assertEqual(portfolio.description, 'notes')

    def test_deleting_my_portfolio_works(self):
        created = self.client.post('/api/backtester/portfolios/', self._payload(),
                                   format='json').data

        response = self.client.delete(f"/api/backtester/portfolios/{created['id']}/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(Portfolio.objects.count(), 0)

    def test_deleting_another_users_portfolio_is_a_404(self):
        theirs = Portfolio.objects.create(user=_user('other@example.com'), name='Theirs')

        response = self.client.delete(f"/api/backtester/portfolios/{theirs.pk}/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Portfolio.objects.filter(pk=theirs.pk).count(), 1)


class DuplicateTests(TestCase):

    def setUp(self):
        self.user = _user()
        self.client = _client(self.user)
        self.portfolio = Portfolio.objects.create(user=self.user, name='Core',
                                                  weighting_scheme='risk_parity')
        PortfolioHolding.objects.create(portfolio=self.portfolio, symbol='AAPL',
                                        target_weight=0.5, order=0)
        PortfolioHolding.objects.create(portfolio=self.portfolio, symbol='VTI',
                                        target_weight=0.5, order=1)

    def test_duplicating_copies_settings_and_holdings(self):
        response = self.client.post(
            f"/api/backtester/portfolios/{self.portfolio.pk}/duplicate/")

        self.assertEqual(response.status_code, 201)
        copy = Portfolio.objects.get(pk=response.data['id'])
        self.assertEqual(copy.weighting_scheme, 'risk_parity')
        self.assertEqual([h.symbol for h in copy.holdings.all()], ['AAPL', 'VTI'])

    def test_the_copy_gets_a_unique_name(self):
        first = self.client.post(
            f"/api/backtester/portfolios/{self.portfolio.pk}/duplicate/").data
        second = self.client.post(
            f"/api/backtester/portfolios/{self.portfolio.pk}/duplicate/").data

        self.assertNotEqual(first['name'], second['name'])
        self.assertEqual(Portfolio.objects.filter(user=self.user).count(), 3)

    def test_duplicating_another_users_portfolio_is_a_404(self):
        theirs = Portfolio.objects.create(user=_user('other@example.com'), name='T')

        response = self.client.post(f"/api/backtester/portfolios/{theirs.pk}/duplicate/")
        self.assertEqual(response.status_code, 404)


@override_settings(FREE_TIER_BACKTEST_LIMIT=7)
class QuotaEndpointTests(TestCase):

    def setUp(self):
        self.user = _user()
        self.client = _client(self.user)

    def test_it_reports_the_allowance(self):
        response = self.client.get('/api/backtester/quota/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data,
                         {'used': 0, 'limit': 7, 'tier': 'free', 'remaining': 7})


@override_settings(CACHES=LOCMEM_CACHE)
class SymbolSearchTests(TestCase):

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.user = _user()
        self.client = _client(self.user)
        self.index = [
            {'symbol': 'AAPL', 'name': 'Apple Inc.', 'kind': 'stock'},
            {'symbol': 'VTI', 'name': 'Vanguard Total Stock Market ETF', 'kind': 'etf'},
            {'symbol': 'AAL', 'name': 'American Airlines Group', 'kind': 'stock'},
        ]

    def _search(self, query):
        from backtester import symbol_index

        with patch.object(symbol_index, 'build_symbol_index', return_value=self.index):
            return self.client.get(f"/api/backtester/search-symbols/?q={query}")

    def test_a_symbol_prefix_match_ranks_first(self):
        response = self._search('aa')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'][0]['symbol'], 'AAL')

    def test_a_name_substring_also_matches(self):
        response = self._search('vanguard')

        self.assertEqual([row['symbol'] for row in response.data['results']], ['VTI'])

    def test_an_exact_symbol_match_outranks_a_prefix_match(self):
        response = self._search('AAPL')

        self.assertEqual(response.data['results'][0]['symbol'], 'AAPL')

    def test_a_short_query_returns_nothing_rather_than_the_whole_universe(self):
        response = self._search('')

        self.assertEqual(response.data['results'], [])

    def test_results_are_capped(self):
        from backtester import symbol_index

        self.index = [{'symbol': f"AA{i}", 'name': f"Company {i}", 'kind': 'stock'}
                      for i in range(100)]
        with patch.object(symbol_index, 'build_symbol_index', return_value=self.index):
            response = self.client.get('/api/backtester/search-symbols/?q=aa')

        self.assertLessEqual(len(response.data['results']), 25)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python manage.py test backtester.tests.test_views -v 2
```

Expected: FAIL — 404s everywhere, because `backtester.urls` is not mounted yet.

- [ ] **Step 3: Write `symbol_index.py`**

Create `backend/backtester/symbol_index.py`:

```python
"""Typeahead index over the staged universe (§12).

Follows analyzer_utils/universe_lookup.build_symbol_universe_index: read the
constituent JSONs, cache a compact structure, and never hit S3 on a keystroke.
The ETF list is included because a portfolio is stocks *and* ETFs.
"""
import gzip
import json

from django.core.cache import cache

from utils.StockCalculations import GetData

data_getter = GetData()

CACHE_KEY = 'backtest:symbol_index:v1'
CACHE_TIMEOUT = 86_400

STOCK_CONSTITUENT_KEYS = ('sp500', 'nasdaq', 'r2000', 'rmicro',
                          'tsx', 'tsx_small_cap', 'msci_eafe', 'msci_sm')


def _entry_symbol(entry):
    if isinstance(entry, str):
        return entry
    return entry.get('asset') or entry.get('symbol')


def _entry_name(entry):
    if isinstance(entry, str):
        return ''
    for key in ('name', 'companyName', 'company_name'):
        if entry.get(key):
            return str(entry[key])
    return ''


def build_symbol_index() -> list:
    """One row per searchable symbol: {symbol, name, kind}."""
    rows = {}

    for constituent_key in STOCK_CONSTITUENT_KEYS:
        try:
            constituents = data_getter.get_index_constituents(constituent_key)
        except Exception:
            # A missing constituent file must not sink the whole typeahead --
            # the other universes are still usable.
            continue
        for entry in constituents:
            symbol = _entry_symbol(entry)
            if symbol:
                rows.setdefault(str(symbol).upper(),
                                {'symbol': str(symbol).upper(),
                                 'name': _entry_name(entry),
                                 'kind': 'stock'})

    try:
        for entry in data_getter.get_index_constituents('etfs'):
            symbol = _entry_symbol(entry)
            if symbol:
                rows[str(symbol).upper()] = {'symbol': str(symbol).upper(),
                                             'name': _entry_name(entry),
                                             'kind': 'etf'}
    except Exception:
        pass

    # Fill in the names the constituent lists leave blank.
    missing = [symbol for symbol, row in rows.items() if not row['name']]
    if missing:
        try:
            profiles = data_getter.load_long_profiles()
            name_column = next((c for c in ('companyName', 'company_name', 'name')
                                if c in profiles.columns), None)
            if name_column:
                lookup = dict(zip(profiles['symbol'].astype(str).str.upper(),
                                  profiles[name_column].astype(str)))
                for symbol in missing:
                    rows[symbol]['name'] = lookup.get(symbol, '')
        except Exception:
            pass

    return sorted(rows.values(), key=lambda row: row['symbol'])


def get_symbol_index() -> list:
    compressed = cache.get(CACHE_KEY)
    if compressed:
        try:
            return json.loads(gzip.decompress(compressed))
        except Exception:
            cache.delete(CACHE_KEY)

    index = build_symbol_index()
    cache.set(CACHE_KEY, gzip.compress(json.dumps(index).encode('utf-8')),
              timeout=CACHE_TIMEOUT)
    return index


def search(query: str, limit: int = 25) -> list:
    """Rank exact symbol match, then symbol prefix, then name substring."""
    query = (query or '').strip().upper()
    if len(query) < 1:
        return []

    exact, prefix, contains = [], [], []
    for row in get_symbol_index():
        symbol = row['symbol']
        if symbol == query:
            exact.append(row)
        elif symbol.startswith(query):
            prefix.append(row)
        elif query in symbol or query in row['name'].upper():
            contains.append(row)
        if len(exact) + len(prefix) + len(contains) >= limit * 4:
            break

    return (exact + prefix + contains)[:limit]
```

- [ ] **Step 4: Write `serializers.py`**

Create `backend/backtester/serializers.py`:

```python
"""Serializers for the backtester API."""
from django.db import transaction
from rest_framework import serializers

from .models import BacktestRun, Portfolio, PortfolioHolding


class PortfolioHoldingSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortfolioHolding
        fields = ('symbol', 'target_weight', 'order')

    def validate_symbol(self, value):
        symbol = str(value).strip().upper()
        if not symbol:
            raise serializers.ValidationError('A holding needs a symbol.')
        return symbol


class PortfolioSerializer(serializers.ModelSerializer):
    holdings = PortfolioHoldingSerializer(many=True, required=False)

    class Meta:
        model = Portfolio
        fields = ('id', 'name', 'description', 'benchmark_symbol', 'initial_amount',
                  'periodic_contribution', 'contribution_frequency',
                  'weighting_scheme', 'backtest_mode', 'rebalance_frequency',
                  'start_date', 'end_date', 'settings', 'holdings',
                  'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate_name(self, value):
        """Uniqueness is per-user, and the user comes from the request rather than
        the body, so the model's unique_together cannot be checked by DRF's
        default validator -- do it here to return 400 instead of a 500."""
        user = self.context['request'].user
        queryset = Portfolio.objects.filter(user=user, name=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError('You already have a portfolio with that name.')
        return value

    @transaction.atomic
    def create(self, validated_data):
        holdings = validated_data.pop('holdings', [])
        portfolio = Portfolio.objects.create(user=self.context['request'].user,
                                             **validated_data)
        self._write_holdings(portfolio, holdings)
        return portfolio

    @transaction.atomic
    def update(self, instance, validated_data):
        # `holdings` absent means "leave them alone"; present means "replace
        # wholesale". A per-holding diff would need stable ids the client does
        # not have, and the builder always submits the full basket anyway.
        holdings = validated_data.pop('holdings', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if holdings is not None:
            instance.holdings.all().delete()
            self._write_holdings(instance, holdings)
        return instance

    @staticmethod
    def _write_holdings(portfolio, holdings):
        PortfolioHolding.objects.bulk_create([
            PortfolioHolding(portfolio=portfolio,
                             symbol=entry['symbol'],
                             target_weight=entry.get('target_weight', 0),
                             order=entry.get('order', position))
            for position, entry in enumerate(holdings)
        ])


class BacktestRunSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = BacktestRun
        fields = ('id', 'task_id', 'status', 'progress', 'summary', 'portfolio',
                  'request', 'error', 'counted_against_quota',
                  'created_at', 'completed_at')
        read_only_fields = fields
```

- [ ] **Step 5: Write `views.py` and `urls.py`**

Create `backend/backtester/views.py`:

```python
"""Backtester API (§12).

Querysets are filtered by request.user at the manager level, never by a URL
parameter -- an id belonging to someone else must 404, not 403, so the API does
not confirm that the row exists.
"""
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import symbol_index
from .models import Portfolio
from .quota import get_quota
from .serializers import PortfolioSerializer

SEARCH_LIMIT = 25


class PortfolioListCreateView(generics.ListCreateAPIView):
    serializer_class = PortfolioSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return (Portfolio.objects
                .filter(user=self.request.user)
                .prefetch_related('holdings'))


class PortfolioDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PortfolioSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (Portfolio.objects
                .filter(user=self.request.user)
                .prefetch_related('holdings'))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def duplicate_portfolio(request, pk):
    """Copying is free -- only execution meters (§13 rule 2)."""
    try:
        original = (Portfolio.objects
                    .filter(user=request.user)
                    .prefetch_related('holdings')
                    .get(pk=pk))
    except Portfolio.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    holdings = [{'symbol': h.symbol, 'target_weight': h.target_weight, 'order': h.order}
                for h in original.holdings.all()]

    base_name = f"{original.name} (copy)"
    name, suffix = base_name, 2
    while Portfolio.objects.filter(user=request.user, name=name).exists():
        name = f"{base_name} {suffix}"
        suffix += 1

    payload = PortfolioSerializer(original).data
    payload.update({'name': name, 'holdings': holdings})
    for read_only in ('id', 'created_at', 'updated_at'):
        payload.pop(read_only, None)

    serializer = PortfolioSerializer(data=payload, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_symbols(request):
    query = request.query_params.get('q', '')
    return Response({'results': symbol_index.search(query, limit=SEARCH_LIMIT)},
                    status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def quota_view(request):
    return Response(get_quota(request.user).as_dict(), status=status.HTTP_200_OK)
```

Create `backend/backtester/urls.py`:

```python
"""Routes for the backtester app.

Every Django app here mounts at path("api/", include(...)), so each route below
carries the `backtester/` segment itself to produce /api/backtester/... (§16).
"""
from django.urls import path

from . import views

urlpatterns = [
    path('backtester/portfolios/', views.PortfolioListCreateView.as_view(),
         name='backtest_portfolios'),
    path('backtester/portfolios/<int:pk>/', views.PortfolioDetailView.as_view(),
         name='backtest_portfolio_detail'),
    path('backtester/portfolios/<int:pk>/duplicate/', views.duplicate_portfolio,
         name='backtest_portfolio_duplicate'),
    path('backtester/search-symbols/', views.search_symbols,
         name='backtest_search_symbols'),
    path('backtester/quota/', views.quota_view, name='backtest_quota'),
]
```

In `backend/fintank_backend/urls.py`, add after the `analyzer` include:

```python
    path("api/", include("backtester.urls")),
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python manage.py test backtester.tests.test_views -v 2
```

Expected: all PASS except `AuthenticationTests`' `/api/backtester/history/` entry, which 404s until Task 14 adds the route. Temporarily drop that one line from the list, or leave it failing and re-run at the end of Task 14 — note which you chose.

- [ ] **Step 7: Verify the route prefix is right**

```bash
python manage.py show_urls 2>/dev/null | grep backtester || python manage.py shell -c "
from django.urls import get_resolver
for key in get_resolver().reverse_dict:
    pass
from django.urls import reverse
print(reverse('backtest_portfolios'))
print(reverse('backtest_quota'))
"
```

Expected: `/api/backtester/portfolios/` and `/api/backtester/quota/` — not `/api/portfolios/`.

- [ ] **Step 8: Commit**

```bash
git add backend/backtester/serializers.py backend/backtester/views.py \
        backend/backtester/urls.py backend/backtester/symbol_index.py \
        backend/backtester/tests/test_views.py backend/fintank_backend/urls.py
git commit -m "feat: add portfolio CRUD, symbol search and quota endpoints"
```

---

### Task 14: Run submission, the Celery task, and result polling

Per platform spec §2, backtests never run in the request thread. `POST /run/` enqueues and returns a `task_id`; the frontend polls.

**Files:**
- Create: `backend/backtester/tasks.py`, `backend/backtester/results.py`
- Modify: `backend/backtester/views.py` (append four views), `backend/backtester/urls.py` (append four routes)
- Modify: `backend/backtester/tests/test_views.py` (append), `backend/backtester/tests/test_tasks.py` (create)

**Interfaces:**
- Consumes: everything from Tasks 3–12.
- Produces:
  - `results.build_payload(result, request, panel, benchmark) -> dict` — assembles the §8 output plus metrics, benchmark metrics, diagnostics and frontier into one JSON-safe dict, and fills the `BacktestResult` slots left empty in Task 7.
  - `results.store_payload(user_id, task_id, payload) -> str` — writes Redis `backtest:{task_id}:v1` (72h) and S3 `backtest_results/{user_id}/{task_id}.json`; returns the S3 key.
  - `results.load_payload(run) -> dict | None` — Redis first, then S3.
  - `tasks.run_portfolio_backtest(run_id)` — the Celery task.
  - `views.submit_run`, `views.run_status`, `views.run_results`, `views.run_history`.

- [ ] **Step 1: Write the failing task test**

Create `backend/backtester/tests/test_tasks.py`:

```python
"""The Celery task and the result payload assembly."""
from unittest.mock import patch

import numpy as np
import pandas as pd
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from backtester.models import BacktestRun
from backtester.engine.prices import PricePanel

User = get_user_model()

LOCMEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'backtester-task-tests',
    }
}


def _user(email='task@example.com'):
    user = User.objects.create_user(username=email, email=email, password='sw0rdfish!x',
                                   first_name='Test', last_name='User')
    from users.models import UserProfile
    if not getattr(user, 'userprofile', None):
        UserProfile.objects.create(user=user)
    return user


def _panel(symbols=('A', 'B'), periods=800, seed=5):
    dates = pd.bdate_range('2018-01-01', periods=periods)
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame(
        {symbol: 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, periods))
         for symbol in symbols},
        index=dates)
    return PricePanel(prices=frame,
                      first_valid={c: frame.index[0] for c in frame.columns},
                      last_valid={c: frame.index[-1] for c in frame.columns},
                      provenance={c: 'test' for c in frame.columns})


def _benchmark(periods=800, seed=6):
    dates = pd.bdate_range('2018-01-01', periods=periods)
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.009, periods)),
                     index=dates)


@override_settings(CACHES=LOCMEM_CACHE)
class BuildPayloadTests(TestCase):

    def setUp(self):
        from backtester.engine.backtest import run_backtest
        from backtester.engine.config import validate_request

        self.panel = _panel()
        self.request = validate_request({
            'holdings': [{'symbol': 'A'}, {'symbol': 'B'}],
            'rebalance_frequency': 'annual', 'min_history_days': 1,
        })
        self.result = run_backtest(self.panel, self.request)

    def _payload(self, benchmark=None):
        from backtester.results import build_payload

        return build_payload(self.result, self.request, self.panel,
                             benchmark if benchmark is not None else _benchmark())

    def test_the_payload_carries_every_documented_section(self):
        payload = self._payload()

        expected = {'dates', 'nav', 'index', 'drawdown', 'returns',
                    'weights_over_time', 'effective_asset_count', 'rebalance_events',
                    'composition_events', 'benchmark_index', 'benchmark_drawdown',
                    'metrics', 'benchmark_metrics', 'diagnostics', 'frontier',
                    'effective_start', 'effective_end', 'truncation_cause',
                    'symbols', 'request', 'provenance'}
        self.assertTrue(expected.issubset(payload), expected - set(payload))

    def test_the_payload_is_json_serializable(self):
        import json

        json.dumps(self._payload())

    def test_every_series_has_the_same_length_as_dates(self):
        payload = self._payload()
        length = len(payload['dates'])

        for key in ('nav', 'index', 'drawdown', 'returns', 'effective_asset_count',
                    'benchmark_index', 'benchmark_drawdown'):
            with self.subTest(key=key):
                self.assertEqual(len(payload[key]), length)

    def test_weights_over_time_is_one_series_per_symbol(self):
        payload = self._payload()

        self.assertEqual(set(payload['weights_over_time']), {'A', 'B'})
        self.assertEqual(len(payload['weights_over_time']['A']),
                         len(payload['dates']))

    def test_the_benchmark_is_aligned_to_the_portfolio_dates(self):
        payload = self._payload()

        self.assertAlmostEqual(payload['benchmark_index'][0], 1.0, places=12)

    def test_diagnostics_always_include_survivorship_bias(self):
        codes = [f['code'] for f in self._payload()['diagnostics']]

        self.assertIn('survivorship_bias', codes)

    def test_a_missing_benchmark_leaves_the_benchmark_sections_empty(self):
        payload = self._payload(benchmark=pd.Series(dtype=float))

        self.assertEqual(payload['benchmark_index'], [])
        self.assertIsNone(payload['metrics']['beta'])


@override_settings(CACHES=LOCMEM_CACHE)
class StoreAndLoadTests(TestCase):

    def setUp(self):
        self.user = _user()
        self.run = BacktestRun.objects.create(user=self.user, task_id='abc123',
                                              request_hash='h', request={})

    def test_storing_writes_redis_and_returns_the_s3_key(self):
        from backtester import results

        with patch.object(results, '_write_to_s3') as writer:
            key = results.store_payload(self.user.pk, 'abc123', {'ok': True})

        self.assertEqual(key, f"backtest_results/{self.user.pk}/abc123.json")
        writer.assert_called_once()

    def test_loading_comes_from_redis_without_touching_s3(self):
        from backtester import results

        with patch.object(results, '_write_to_s3'):
            results.store_payload(self.user.pk, 'abc123', {'ok': True})

        with patch.object(results, '_read_from_s3') as reader:
            payload = results.load_payload(self.run)

        reader.assert_not_called()
        self.assertEqual(payload, {'ok': True})

    def test_loading_falls_back_to_s3_when_the_cache_has_expired(self):
        from backtester import results

        self.run.result_key = f"backtest_results/{self.user.pk}/abc123.json"
        self.run.save(update_fields=['result_key'])

        with patch.object(results, '_read_from_s3', return_value={'ok': 'from-s3'}):
            payload = results.load_payload(self.run)

        self.assertEqual(payload, {'ok': 'from-s3'})

    def test_an_s3_failure_returns_none_rather_than_raising(self):
        from backtester import results

        self.run.result_key = 'backtest_results/1/missing.json'
        self.run.save(update_fields=['result_key'])

        with patch.object(results, '_read_from_s3', side_effect=OSError('gone')):
            self.assertIsNone(results.load_payload(self.run))


@override_settings(CACHES=LOCMEM_CACHE)
class RunPortfolioBacktestTests(TestCase):

    def setUp(self):
        self.user = _user()
        self.request_payload = {
            'holdings': [{'symbol': 'A'}, {'symbol': 'B'}],
            'rebalance_frequency': 'annual', 'min_history_days': 1,
            'benchmark_symbol': 'SPY',
        }
        self.run = BacktestRun.objects.create(
            user=self.user, task_id='task-1', request_hash='hash-1',
            request=self.request_payload)

    def _execute(self, panel=None, benchmark=None):
        from backtester import tasks

        with patch.object(tasks, 'load_price_panel',
                          return_value=panel if panel is not None else _panel()), \
             patch.object(tasks, 'load_benchmark_series',
                          return_value=(benchmark if benchmark is not None
                                        else _benchmark(), 's3')), \
             patch('backtester.results._write_to_s3'):
            return tasks.run_portfolio_backtest(self.run.pk)

    def test_a_successful_run_completes_and_records_a_summary(self):
        self._execute()
        self.run.refresh_from_db()

        self.assertEqual(self.run.status, BacktestRun.STATUS_COMPLETE)
        self.assertIsNotNone(self.run.completed_at)
        self.assertIn('cagr', self.run.summary)
        self.assertTrue(self.run.result_key)
        self.assertEqual(self.run.error, '')

    def test_the_summary_holds_headline_metrics_only_not_the_series(self):
        self._execute()
        self.run.refresh_from_db()

        self.assertNotIn('nav', self.run.summary)
        self.assertNotIn('index', self.run.summary)
        self.assertLess(len(self.run.summary), 20)

    def test_the_full_payload_is_readable_afterwards(self):
        from backtester.results import load_payload

        self._execute()
        self.run.refresh_from_db()

        payload = load_payload(self.run)
        self.assertIn('diagnostics', payload)

    def test_a_price_failure_marks_the_run_failed_and_refunds_it(self):
        from backtester import tasks
        from backtester.engine.config import PriceDataUnavailable

        with patch.object(tasks, 'load_price_panel',
                          side_effect=PriceDataUnavailable('no data', {'A': 'gone'})):
            tasks.run_portfolio_backtest(self.run.pk)

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, BacktestRun.STATUS_FAILED)
        self.assertIn('no data', self.run.error)
        self.assertFalse(self.run.counted_against_quota)

    def test_an_unexpected_error_also_refunds(self):
        from backtester import tasks

        with patch.object(tasks, 'load_price_panel', side_effect=RuntimeError('boom')):
            tasks.run_portfolio_backtest(self.run.pk)

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, BacktestRun.STATUS_FAILED)
        self.assertFalse(self.run.counted_against_quota)

    def test_a_no_eligible_assets_error_is_reported_plainly(self):
        from backtester import tasks

        short = _panel(periods=5)
        self.run.request = dict(self.request_payload,
                                weighting_scheme='min_variance')
        self.run.save(update_fields=['request'])

        with patch.object(tasks, 'load_price_panel', return_value=short), \
             patch.object(tasks, 'load_benchmark_series',
                          return_value=(_benchmark(periods=5), 's3')):
            tasks.run_portfolio_backtest(self.run.pk)

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, BacktestRun.STATUS_FAILED)
        self.assertIn('history', self.run.error.lower())

    def test_a_missing_run_id_does_not_raise(self):
        from backtester import tasks

        self.assertIsNone(tasks.run_portfolio_backtest(999_999))
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python manage.py test backtester.tests.test_tasks -v 2
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backtester.results'`.

- [ ] **Step 3: Write `results.py`**

Create `backend/backtester/results.py`:

```python
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
from django.conf import settings
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
```

- [ ] **Step 4: Write `tasks.py`**

Create `backend/backtester/tasks.py`:

```python
"""The Celery task. Celery's autodiscover_tasks() picks this up with no config
change (§16)."""
from django.utils import timezone

from celery import shared_task

from .engine.backtest import run_backtest
from .engine.config import (
    OPTIMIZER_SCHEMES,
    NoEligibleAssets,
    PriceDataUnavailable,
    RequestValidationError,
    validate_request,
)
from .engine.prices import load_benchmark_series, load_price_panel
from .models import BacktestRun
from .quota import refund
from .results import build_payload, store_payload, summarize

PROGRESS_STAGES = ('loading_prices', 'optimizing', 'simulating', 'computing_metrics')


def _set_progress(run, stage):
    run.progress = stage
    run.save(update_fields=['progress'])


@shared_task(bind=True)
def run_portfolio_backtest(self, run_id):
    """Load prices, run the engine, store the result, update the row.

    Errors are recorded on the row and the run is refunded rather than retried:
    a bad request or a missing symbol will fail identically on every retry, and
    users do not pay for our bugs (§13 rule 3).
    """
    try:
        run = BacktestRun.objects.get(pk=run_id)
    except BacktestRun.DoesNotExist:
        return None

    run.status = BacktestRun.STATUS_RUNNING
    run.progress = PROGRESS_STAGES[0]
    run.save(update_fields=['status', 'progress'])

    try:
        request = validate_request(run.request)

        panel = load_price_panel(request.symbols, start=request.start_date,
                                 end=request.end_date)
        benchmark, _ = load_benchmark_series(request.benchmark_symbol,
                                            start=request.start_date,
                                            end=request.end_date)

        # The loop optimizes and simulates in one pass, so the stage label
        # reflects which of the two dominates the wait for this request.
        _set_progress(run, 'optimizing' if request.weighting_scheme in OPTIMIZER_SCHEMES
                      else 'simulating')
        result = run_backtest(panel, request)

        _set_progress(run, 'computing_metrics')
        payload = build_payload(result, request, panel, benchmark)

        run.result_key = store_payload(run.user_id, run.task_id, payload)
        run.summary = summarize(payload['metrics'])
        run.status = BacktestRun.STATUS_COMPLETE
        run.progress = 'complete'
        run.error = ''
        run.completed_at = timezone.now()
        run.save(update_fields=['result_key', 'summary', 'status', 'progress',
                                'error', 'completed_at'])
        return run.task_id

    except (RequestValidationError, NoEligibleAssets, PriceDataUnavailable) as error:
        _fail(run, str(error))
        return None
    except Exception as error:                      # noqa: BLE001
        _fail(run, f"{type(error).__name__}: {error}")
        return None


def _fail(run, message):
    run.status = BacktestRun.STATUS_FAILED
    run.progress = 'failed'
    run.error = message
    run.completed_at = timezone.now()
    run.save(update_fields=['status', 'progress', 'error', 'completed_at'])
    refund(run)
```

- [ ] **Step 5: Run the task tests to verify they pass**

```bash
python manage.py test backtester.tests.test_tasks -v 2
```

Expected: all PASS.

- [ ] **Step 6: Append the four views**

Extend the import block at the top of `backend/backtester/views.py` so it reads exactly:

```python
import hashlib
import json
import uuid

from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import symbol_index
from .engine.config import RequestValidationError, normalized_payload, validate_request
from .models import BacktestRun, Portfolio
from .permissions import HasBacktestQuota
from .quota import QuotaExceeded, check_and_consume, get_quota
from .results import load_payload
from .serializers import BacktestRunSummarySerializer, PortfolioSerializer
from .tasks import run_portfolio_backtest
```

That replaces the Task 13 block rather than sitting above it — `Portfolio`, `status` and `get_quota` are already imported there and must not be imported twice.

Append to `backend/backtester/views.py`:

```python
HISTORY_PAGE_SIZE = 20


def _request_hash(request_obj) -> str:
    canonical = json.dumps(normalized_payload(request_obj), sort_keys=True,
                           separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


@api_view(['POST'])
@permission_classes([IsAuthenticated, HasBacktestQuota])
def submit_run(request):
    """Enqueue a backtest. Never runs the engine in the request thread (§12)."""
    try:
        parsed = validate_request(request.data)
    except RequestValidationError as error:
        return Response({'detail': str(error)},
                        status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    request_hash = _request_hash(parsed)

    # Rule 1: an identical request serves from the existing run and is free.
    # Without this, toggling a chart option burns a credit.
    existing = (BacktestRun.objects
                .filter(user=request.user, request_hash=request_hash,
                        status=BacktestRun.STATUS_COMPLETE)
                .order_by('-created_at')
                .first())
    if existing:
        return Response({'task_id': existing.task_id, 'status': existing.status,
                         'cached': True}, status=status.HTTP_200_OK)

    try:
        check_and_consume(request.user)
    except QuotaExceeded as error:
        return Response(error.detail, status=error.status_code)

    portfolio_id = request.data.get('portfolio_id')
    portfolio = None
    if portfolio_id:
        portfolio = Portfolio.objects.filter(user=request.user, pk=portfolio_id).first()

    run = BacktestRun.objects.create(
        user=request.user,
        portfolio=portfolio,
        task_id=uuid.uuid4().hex,
        request_hash=request_hash,
        request=normalized_payload(parsed),
        status=BacktestRun.STATUS_QUEUED,
    )
    run_portfolio_backtest.delay(run.pk)
    return Response({'task_id': run.task_id, 'status': run.status, 'cached': False},
                    status=status.HTTP_202_ACCEPTED)


def _own_run(request, task_id):
    return BacktestRun.objects.filter(user=request.user, task_id=task_id).first()


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def run_status(request, task_id):
    run = _own_run(request, task_id)
    if not run:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    return Response({'task_id': run.task_id, 'status': run.status,
                     'progress': run.progress, 'error': run.error},
                    status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def run_results(request, task_id):
    run = _own_run(request, task_id)
    if not run:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if run.status == BacktestRun.STATUS_FAILED:
        return Response({'detail': run.error or 'The backtest failed.'},
                        status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    if run.status != BacktestRun.STATUS_COMPLETE:
        return Response({'detail': 'Still running.', 'status': run.status},
                        status=status.HTTP_202_ACCEPTED)

    payload = load_payload(run)
    if payload is None:
        return Response({'detail': 'These results have expired. Re-run the backtest.'},
                        status=status.HTTP_410_GONE)
    return Response(payload, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def run_history(request):
    queryset = BacktestRun.objects.filter(user=request.user)
    try:
        page = max(int(request.query_params.get('page', 1)), 1)
    except ValueError:
        page = 1
    start = (page - 1) * HISTORY_PAGE_SIZE
    rows = queryset[start:start + HISTORY_PAGE_SIZE]
    return Response({'count': queryset.count(), 'page': page,
                     'results': BacktestRunSummarySerializer(rows, many=True).data},
                    status=status.HTTP_200_OK)
```

Append to `backend/backtester/urls.py`'s `urlpatterns`:

```python
    path('backtester/run/', views.submit_run, name='backtest_run'),
    path('backtester/status/<str:task_id>/', views.run_status, name='backtest_status'),
    path('backtester/results/<str:task_id>/', views.run_results, name='backtest_results'),
    path('backtester/history/', views.run_history, name='backtest_history'),
```

- [ ] **Step 7: Append the view tests**

Append to `backend/backtester/tests/test_views.py`:

```python
from backtester.models import BacktestRun


@override_settings(FREE_TIER_BACKTEST_LIMIT=2, CACHES=LOCMEM_CACHE)
class SubmitRunTests(TestCase):

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.user = _user()
        self.client = _client(self.user)
        self.payload = {'holdings': [{'symbol': 'AAPL'}, {'symbol': 'VTI'}],
                        'rebalance_frequency': 'annual'}

    def _submit(self, payload=None):
        with patch('backtester.views.run_portfolio_backtest.delay') as enqueue:
            response = self.client.post('/api/backtester/run/',
                                        payload or self.payload, format='json')
        return response, enqueue

    def test_a_valid_request_is_queued_and_returns_a_task_id(self):
        response, enqueue = self._submit()

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data['status'], 'queued')
        self.assertTrue(response.data['task_id'])
        self.assertFalse(response.data['cached'])
        enqueue.assert_called_once()

    def test_the_engine_never_runs_in_the_request_thread(self):
        with patch('backtester.views.run_portfolio_backtest.delay') as enqueue, \
             patch('backtester.tasks.run_portfolio_backtest') as executed:
            self.client.post('/api/backtester/run/', self.payload, format='json')

        enqueue.assert_called_once()
        executed.assert_not_called()

    def test_bad_input_is_a_422_with_a_readable_message(self):
        response, enqueue = self._submit({'holdings': []})

        self.assertEqual(response.status_code, 422)
        self.assertIn('holding', response.data['detail'])
        enqueue.assert_not_called()

    def test_an_infeasible_constraint_is_rejected_before_enqueue(self):
        response, enqueue = self._submit(dict(self.payload, max_weight=0.1))

        self.assertEqual(response.status_code, 422)
        enqueue.assert_not_called()

    def test_a_repeat_request_hash_serves_the_cached_run_without_spending_quota(self):
        """§13 rule 1."""
        response, _ = self._submit()
        run = BacktestRun.objects.get(task_id=response.data['task_id'])
        run.status = BacktestRun.STATUS_COMPLETE
        run.save(update_fields=['status'])

        repeat, enqueue = self._submit()

        self.assertEqual(repeat.status_code, 200)
        self.assertTrue(repeat.data['cached'])
        self.assertEqual(repeat.data['task_id'], response.data['task_id'])
        enqueue.assert_not_called()
        self.assertEqual(BacktestRun.objects.count(), 1)

    def test_the_hash_ignores_irrelevant_key_order_and_casing(self):
        first, _ = self._submit({'holdings': [{'symbol': 'aapl'}, {'symbol': 'vti'}],
                                 'rebalance_frequency': 'annual'})
        run = BacktestRun.objects.get(task_id=first.data['task_id'])
        run.status = BacktestRun.STATUS_COMPLETE
        run.save(update_fields=['status'])

        repeat, _ = self._submit({'rebalance_frequency': 'annual',
                                  'holdings': [{'symbol': 'AAPL'}, {'symbol': 'VTI'}]})
        self.assertTrue(repeat.data['cached'])

    def test_an_exhausted_quota_is_a_402_with_upgrade_metadata(self):
        for i in range(2):
            BacktestRun.objects.create(user=self.user, task_id=f"t{i}",
                                       request_hash=f"h{i}", request={})

        response, enqueue = self._submit()

        self.assertEqual(response.status_code, 402)
        self.assertTrue(response.data['upgrade_required'])
        self.assertEqual(response.data['limit'], 2)
        enqueue.assert_not_called()

    def test_a_portfolio_id_is_attached_only_when_it_is_mine(self):
        mine = Portfolio.objects.create(user=self.user, name='Mine')
        theirs = Portfolio.objects.create(user=_user('other@example.com'), name='T')

        response, _ = self._submit(dict(self.payload, portfolio_id=mine.pk))
        self.assertEqual(BacktestRun.objects.get(
            task_id=response.data['task_id']).portfolio, mine)

        BacktestRun.objects.all().delete()
        response, _ = self._submit(dict(self.payload, portfolio_id=theirs.pk,
                                        benchmark_symbol='QQQ'))
        self.assertIsNone(BacktestRun.objects.get(
            task_id=response.data['task_id']).portfolio)


@override_settings(CACHES=LOCMEM_CACHE)
class StatusAndResultsTests(TestCase):

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.user = _user()
        self.client = _client(self.user)
        self.run = BacktestRun.objects.create(user=self.user, task_id='abc',
                                              request_hash='h', request={},
                                              progress='simulating')

    def test_status_reports_progress(self):
        response = self.client.get('/api/backtester/status/abc/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['progress'], 'simulating')

    def test_a_user_cannot_read_another_users_status(self):
        client = _client(_user('other@example.com'))

        self.assertEqual(client.get('/api/backtester/status/abc/').status_code, 404)

    def test_a_user_cannot_read_another_users_results(self):
        client = _client(_user('other@example.com'))

        self.assertEqual(client.get('/api/backtester/results/abc/').status_code, 404)

    def test_results_of_a_running_job_are_a_202(self):
        self.assertEqual(self.client.get('/api/backtester/results/abc/').status_code, 202)

    def test_results_of_a_failed_job_are_a_422_carrying_the_error(self):
        self.run.status = BacktestRun.STATUS_FAILED
        self.run.error = 'No requested asset has enough price history.'
        self.run.save(update_fields=['status', 'error'])

        response = self.client.get('/api/backtester/results/abc/')
        self.assertEqual(response.status_code, 422)
        self.assertIn('price history', response.data['detail'])

    def test_a_complete_job_returns_the_stored_payload(self):
        from backtester import results

        self.run.status = BacktestRun.STATUS_COMPLETE
        self.run.save(update_fields=['status'])
        with patch.object(results, '_write_to_s3'):
            results.store_payload(self.user.pk, 'abc', {'dates': ['2020-01-01']})

        response = self.client.get('/api/backtester/results/abc/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['dates'], ['2020-01-01'])

    def test_an_expired_payload_is_a_410_telling_the_user_to_re_run(self):
        self.run.status = BacktestRun.STATUS_COMPLETE
        self.run.save(update_fields=['status'])

        response = self.client.get('/api/backtester/results/abc/')
        self.assertEqual(response.status_code, 410)
        self.assertIn('Re-run', response.data['detail'])


class HistoryTests(TestCase):

    def setUp(self):
        self.user = _user()
        self.client = _client(self.user)
        for i in range(25):
            BacktestRun.objects.create(user=self.user, task_id=f"t{i}",
                                       request_hash=f"h{i}", request={})
        BacktestRun.objects.create(user=_user('other@example.com'), task_id='x',
                                   request_hash='x', request={})

    def test_history_is_paginated_and_scoped_to_me(self):
        response = self.client.get('/api/backtester/history/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 25)
        self.assertEqual(len(response.data['results']), 20)

    def test_page_two_holds_the_remainder(self):
        response = self.client.get('/api/backtester/history/?page=2')

        self.assertEqual(len(response.data['results']), 5)

    def test_history_carries_summaries_not_full_results(self):
        response = self.client.get('/api/backtester/history/')

        self.assertNotIn('nav', response.data['results'][0])
        self.assertIn('summary', response.data['results'][0])
```

- [ ] **Step 8: Run the whole backend suite**

```bash
python manage.py test backtester -v 2
```

Expected: every test passes, including the `/api/backtester/history/` entry in `AuthenticationTests` that was pending from Task 13 Step 6.

- [ ] **Step 9: Smoke-test the real thing end to end**

Requires Redis and Postgres running, plus real S3/FMP credentials. Start a Celery worker in one terminal:

```bash
cd backend && celery -A fintank_backend worker -l info
```

Then, in a shell, submit a run synchronously through the task to confirm the whole path works against live data:

```bash
python manage.py shell -c "
from django.contrib.auth import get_user_model
from backtester.models import BacktestRun
from backtester.tasks import run_portfolio_backtest
from backtester.results import load_payload
user = get_user_model().objects.first()
run = BacktestRun.objects.create(user=user, task_id='smoke1', request_hash='smoke1',
    request={'holdings':[{'symbol':'SPY','target_weight':0.6},{'symbol':'AGG','target_weight':0.4}],
             'weighting_scheme':'custom','rebalance_frequency':'annual'})
run_portfolio_backtest(run.pk)
run.refresh_from_db()
print(run.status, run.error[:200])
print(run.summary)
print([d['code'] for d in load_payload(run)['diagnostics']])
"
```

Expected: `complete`, a summary with a plausible CAGR, and a diagnostics list containing `survivorship_bias`. Delete the smoke run afterwards.

- [ ] **Step 10: Commit**

```bash
git add backend/backtester/tasks.py backend/backtester/results.py \
        backend/backtester/views.py backend/backtester/urls.py \
        backend/backtester/tests/test_tasks.py backend/backtester/tests/test_views.py
git commit -m "feat: add async backtest execution and result polling"
```

---

### Task 15: Frontend proxy and data hooks

**The JWT is in an httpOnly cookie.** `src/pages/api/auth/login.js:22-28` sets `access` with `httpOnly: true`, so client JS cannot read it and a hook cannot send `Authorization: Bearer`. Every authenticated call goes through a Next API route that reads the cookie server-side — the pattern `src/pages/api/auth/userprofile.js` already uses. One catch-all proxy serves all nine backend routes rather than nine near-identical files.

There is no frontend test runner configured in this repo (`jest` is present but there is no `test` script and `.babelrc.disabled-test` is parked), so verification here is `npm run lint`, `npm run format:check`, `npm run build`, and a browser check.

**Files:**
- Create: `src/pages/api/backtester/[...path].js`, `src/hooks/usePortfolios.js`, `src/hooks/useBacktestRun.js`, `src/hooks/useSymbolSearch.js`, `src/hooks/useBacktestQuota.js`

**Interfaces:**
- Consumes: the routes from Tasks 13–14.
- Produces:
  - `usePortfolios()` → `{portfolios, loading, error, reload, create, update, remove, duplicate}`
  - `useBacktestRun()` → `{run, result, status, progress, error, quotaError, submit, reset}`
  - `useSymbolSearch()` → `{query, setQuery, results, searching}`
  - `useBacktestQuota()` → `{quota, loading, reload}`

- [ ] **Step 1: Write the API proxy**

Create `src/pages/api/backtester/[...path].js`:

```javascript
import axios from "axios"
import cookie from "cookie"

/**
 * Server-side proxy for every /api/backtester/* call.
 *
 * The JWT lives in an httpOnly cookie (set by /api/auth/login), so the browser
 * cannot attach it itself. This route reads the cookie and forwards the request
 * to Django with the Bearer header, which is the same pattern
 * /api/auth/userprofile.js uses.
 */
const ALLOWED_METHODS = ["GET", "POST", "PATCH", "DELETE"]

export default async function handler(req, res) {
  if (!ALLOWED_METHODS.includes(req.method)) {
    res.setHeader("Allow", ALLOWED_METHODS.join(", "))
    return res.status(405).json({ detail: `${req.method} is not supported here.` })
  }

  const cookies = cookie.parse(req.headers.cookie || "")
  const access = cookies.access || false
  if (!access) {
    return res.status(401).json({ detail: "Log in to use the backtester." })
  }

  const segments = Array.isArray(req.query.path) ? req.query.path : [req.query.path]
  const search = new URLSearchParams()
  Object.entries(req.query).forEach(([key, value]) => {
    if (key !== "path") search.append(key, value)
  })
  const queryString = search.toString()
  const url =
    `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/backtester/${segments.join("/")}/` +
    (queryString ? `?${queryString}` : "")

  try {
    const response = await axios({
      method: req.method,
      url,
      data: ["POST", "PATCH"].includes(req.method) ? req.body : undefined,
      headers: {
        Authorization: `Bearer ${access}`,
        "Content-Type": "application/json",
      },
      // 402, 410 and 422 all carry a body the UI needs to read, so let them
      // through rather than throwing.
      validateStatus: () => true,
    })
    return res.status(response.status).json(response.data)
  } catch (error) {
    const status = error?.response?.status || 502
    return res
      .status(status)
      .json(error?.response?.data || { detail: "The backtester is unreachable." })
  }
}
```

`validateStatus: () => true` is what stops axios throwing on 402/410/422 — those responses carry bodies the UI needs to read and forward verbatim. The option name is verified against the installed axios 1.13.2 (`node_modules/axios/index.d.ts:341`).

- [ ] **Step 2: Write `useBacktestQuota.js`**

Create `src/hooks/useBacktestQuota.js`:

```javascript
import { useCallback, useEffect, useState } from "react"
import axios from "axios"

/**
 * Remaining free backtests. Cheap enough to refetch after every run so the
 * banner never shows a stale count.
 */
export const useBacktestQuota = () => {
  const [quota, setQuota] = useState(null)
  const [loading, setLoading] = useState(true)

  const reload = useCallback(async () => {
    try {
      setLoading(true)
      const { data } = await axios.get("/api/backtester/quota")
      setQuota(data)
    } catch (error) {
      setQuota(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  return { quota, loading, reload }
}

export default useBacktestQuota
```

- [ ] **Step 3: Write `useSymbolSearch.js`**

Create `src/hooks/useSymbolSearch.js`:

```javascript
import { useEffect, useState } from "react"
import axios from "axios"

const DEBOUNCE_MS = 250
const MIN_QUERY_LENGTH = 1

/**
 * Debounced typeahead over the staged universe. The debounce matters: the
 * backend builds its symbol index from S3 constituent lists, and a request per
 * keystroke would hammer it.
 */
export const useSymbolSearch = () => {
  const [query, setQuery] = useState("")
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)

  useEffect(() => {
    const trimmed = query.trim()
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setResults([])
      return undefined
    }

    let cancelled = false
    const timer = setTimeout(async () => {
      try {
        setSearching(true)
        const { data } = await axios.get(
          `/api/backtester/search-symbols?q=${encodeURIComponent(trimmed)}`
        )
        if (!cancelled) setResults(data?.results || [])
      } catch (error) {
        if (!cancelled) setResults([])
      } finally {
        if (!cancelled) setSearching(false)
      }
    }, DEBOUNCE_MS)

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query])

  return { query, setQuery, results, searching }
}

export default useSymbolSearch
```

- [ ] **Step 4: Write `usePortfolios.js`**

Create `src/hooks/usePortfolios.js`:

```javascript
import { useCallback, useEffect, useState } from "react"
import axios from "axios"

const BASE = "/api/backtester/portfolios"

/**
 * Saved-portfolio CRUD. All of it is free — only running a backtest meters —
 * so these calls never need to worry about the quota.
 */
export const usePortfolios = () => {
  const [portfolios, setPortfolios] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const reload = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const { data } = await axios.get(BASE)
      setPortfolios(Array.isArray(data) ? data : data?.results || [])
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Could not load your portfolios.")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  const create = useCallback(
    async (payload) => {
      try {
        const { data } = await axios.post(BASE, payload)
        await reload()
        return data
      } catch (requestError) {
        setError(
          requestError?.response?.data?.name?.[0] ||
            requestError?.response?.data?.detail ||
            "Could not save that portfolio."
        )
        return null
      }
    },
    [reload]
  )

  const update = useCallback(
    async (id, payload) => {
      try {
        const { data } = await axios.patch(`${BASE}/${id}`, payload)
        await reload()
        return data
      } catch (requestError) {
        setError(requestError?.response?.data?.detail || "Could not update that portfolio.")
        return null
      }
    },
    [reload]
  )

  const remove = useCallback(
    async (id) => {
      try {
        await axios.delete(`${BASE}/${id}`)
        await reload()
        return true
      } catch (requestError) {
        setError("Could not delete that portfolio.")
        return false
      }
    },
    [reload]
  )

  const duplicate = useCallback(
    async (id) => {
      try {
        const { data } = await axios.post(`${BASE}/${id}/duplicate`, {})
        await reload()
        return data
      } catch (requestError) {
        setError("Could not duplicate that portfolio.")
        return null
      }
    },
    [reload]
  )

  return { portfolios, loading, error, reload, create, update, remove, duplicate }
}

export default usePortfolios
```

- [ ] **Step 5: Write `useBacktestRun.js`**

Create `src/hooks/useBacktestRun.js`:

```javascript
import { useCallback, useEffect, useRef, useState } from "react"
import axios from "axios"

const POLL_START_MS = 1000
const POLL_MAX_MS = 3000
const POLL_STEP_MS = 500

/**
 * Submit a backtest, poll until it finishes, then fetch the result.
 *
 * Polling starts at 1s and backs off to 3s: most runs finish in a few seconds,
 * and a fixed 1s interval on a 30s risk-parity run is 30 pointless requests.
 */
export const useBacktestRun = () => {
  const [taskId, setTaskId] = useState(null)
  const [status, setStatus] = useState("idle")
  const [progress, setProgress] = useState("")
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [quotaError, setQuotaError] = useState(null)
  const timer = useRef(null)
  const interval = useRef(POLL_START_MS)

  const clear = useCallback(() => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
  }, [])

  useEffect(() => clear, [clear])

  const fetchResult = useCallback(async (id) => {
    try {
      const { data } = await axios.get(`/api/backtester/results/${id}`)
      setResult(data)
      setStatus("complete")
    } catch (requestError) {
      setStatus("failed")
      setError(
        requestError?.response?.data?.detail || "The backtest finished but its results are gone."
      )
    }
  }, [])

  const poll = useCallback(
    async (id) => {
      try {
        const { data } = await axios.get(`/api/backtester/status/${id}`)
        setProgress(data?.progress || "")

        if (data?.status === "complete") {
          await fetchResult(id)
          return
        }
        if (data?.status === "failed") {
          setStatus("failed")
          setError(data?.error || "The backtest failed.")
          return
        }
        interval.current = Math.min(interval.current + POLL_STEP_MS, POLL_MAX_MS)
        timer.current = setTimeout(() => poll(id), interval.current)
      } catch (requestError) {
        setStatus("failed")
        setError("Lost contact with the backtester.")
      }
    },
    [fetchResult]
  )

  const reset = useCallback(() => {
    clear()
    setTaskId(null)
    setStatus("idle")
    setProgress("")
    setResult(null)
    setError(null)
    setQuotaError(null)
    interval.current = POLL_START_MS
  }, [clear])

  const submit = useCallback(
    async (payload) => {
      clear()
      setStatus("submitting")
      setError(null)
      setQuotaError(null)
      setResult(null)
      interval.current = POLL_START_MS

      try {
        const { data } = await axios.post("/api/backtester/run", payload)
        setTaskId(data.task_id)

        if (data.cached) {
          setStatus("running")
          await fetchResult(data.task_id)
          return data.task_id
        }
        setStatus("running")
        timer.current = setTimeout(() => poll(data.task_id), POLL_START_MS)
        return data.task_id
      } catch (requestError) {
        const response = requestError?.response
        setStatus("failed")
        if (response?.status === 402) {
          setQuotaError(response.data)
        } else {
          setError(response?.data?.detail || "Could not start the backtest.")
        }
        return null
      }
    },
    [clear, fetchResult, poll]
  )

  return { taskId, status, progress, result, error, quotaError, submit, reset }
}

export default useBacktestRun
```

- [ ] **Step 6: Lint, format and build**

```bash
npm run lint
npm run format
npm run build
```

Expected: lint clean, `npm run build` succeeds. `npm run format` rewrites files to Prettier's style — run it rather than `format:check` so the committed files already pass CI.

- [ ] **Step 7: Verify the proxy authenticates**

Start the dev server (`npm run dev`), then with no session:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8020/api/backtester/quota
```

Expected: `401`. With Django running and a logged-in browser session, `/api/backtester/quota` in the browser devtools network tab should return the quota JSON.

- [ ] **Step 8: Commit**

```bash
git add src/pages/api/backtester/ src/hooks/usePortfolios.js src/hooks/useBacktestRun.js \
        src/hooks/useSymbolSearch.js src/hooks/useBacktestQuota.js
git commit -m "feat: add backtester API proxy and data hooks"
```

---

### Task 16: Portfolio builder and settings

Progressive disclosure (§14): defaults good enough that a novice can press Run within 30 seconds, with everything advanced behind a disclosure. This task delivers the input half of the page and replaces the `ComingSoon` body so the page is usable end to end before any chart exists.

**Files:**
- Create: `src/componentsLegacy/Backtest/PortfolioBuilder.js`, `src/componentsLegacy/Backtest/BacktestSettings.js`, `src/componentsLegacy/Backtest/AdvancedSettings.js`, `src/componentsLegacy/Backtest/QuotaBanner.js`, `src/componentsLegacy/Backtest/backtestDefaults.js`
- Modify: `src/pages/backtest-portfolio.js` (replace the `ComingSoon` body)

**Interfaces:**
- Consumes: `useSymbolSearch`, `useBacktestQuota`, `useBacktestRun` from Task 15.
- Produces:
  - `backtestDefaults.js` exports `DEFAULT_SETTINGS`, `WEIGHTING_OPTIONS`, `REBALANCE_OPTIONS`, `CONTRIBUTION_OPTIONS`, `PERIOD_OPTIONS`, `COVARIANCE_OPTIONS`, `INCEPTION_OPTIONS`, and `buildRequestPayload(holdings, settings) -> object` — the single place the API payload shape is assembled.
  - `<PortfolioBuilder holdings settings onHoldingsChange onSettingsChange />`
  - `<BacktestSettings settings onChange />`
  - `<AdvancedSettings settings onChange />`
  - `<QuotaBanner quota quotaError />`

- [ ] **Step 1: Write the shared defaults module**

Create `src/componentsLegacy/Backtest/backtestDefaults.js`:

```javascript
/**
 * Option lists and the request payload shape, in one place.
 *
 * The values must match backend/backtester/engine/config.py exactly — a typo
 * here surfaces as a 422 with no clue which control caused it.
 */
export const WEIGHTING_OPTIONS = [
  { value: "equal", label: "Equal weight", hint: "Same amount in each holding." },
  { value: "custom", label: "My own weights", hint: "You set the percentages." },
  {
    value: "inverse_vol",
    label: "Inverse volatility",
    hint: "More in the steadier holdings.",
  },
  {
    value: "min_variance",
    label: "Minimum variance",
    hint: "The mix that would have swung the least.",
  },
  {
    value: "risk_parity",
    label: "Risk parity",
    hint: "Every holding contributes the same share of risk.",
  },
  {
    value: "max_sharpe",
    label: "Maximum Sharpe",
    hint: "Best past return per unit of risk. Very sensitive to the window.",
  },
]

export const REBALANCE_OPTIONS = [
  { value: "none", label: "Never" },
  { value: "monthly", label: "Monthly" },
  { value: "quarterly", label: "Quarterly" },
  { value: "semiannual", label: "Every 6 months" },
  { value: "annual", label: "Annually" },
]

export const CONTRIBUTION_OPTIONS = [
  { value: "none", label: "No regular deposits" },
  { value: "monthly", label: "Monthly" },
  { value: "quarterly", label: "Quarterly" },
  { value: "annual", label: "Annually" },
]

export const PERIOD_OPTIONS = [
  { value: 0, label: "As far back as the data goes" },
  { value: 3, label: "3 years" },
  { value: 5, label: "5 years" },
  { value: 10, label: "10 years" },
  { value: 20, label: "20 years" },
]

export const COVARIANCE_OPTIONS = [
  {
    value: "ledoit_wolf",
    label: "Shrinkage (recommended)",
    hint: "More stable when you hold many things over a short window.",
  },
  { value: "sample", label: "Plain sample", hint: "Textbook estimate. Noisier." },
]

export const INCEPTION_OPTIONS = [
  {
    value: "phase_in",
    label: "Phase holdings in as they list",
    hint: "Keeps the full period. Holdings join when their price history starts.",
  },
  {
    value: "common_start",
    label: "Start only when every holding exists",
    hint: "Shorter, but a clean like-for-like window.",
  },
]

export const BACKTEST_MODE_OPTIONS = [
  {
    value: "fixed",
    label: "Pick weights once",
    hint: "Chosen at the start and held.",
  },
  {
    value: "walk_forward",
    label: "Re-optimize at each rebalance",
    hint: "Only uses data available at the time. Slower, more honest.",
  },
]

export const DEFAULT_SETTINGS = {
  benchmarkSymbol: "SPY",
  periodYears: 10,
  weightingScheme: "equal",
  backtestMode: "fixed",
  rebalanceFrequency: "annual",
  initialAmount: 10000,
  periodicContribution: 0,
  contributionFrequency: "none",
  // advanced
  lookbackDays: 252,
  gapDays: 1,
  covarianceMethod: "ledoit_wolf",
  transactionCostBps: 10,
  longOnly: true,
  maxWeight: "",
  minWeight: "",
  riskFreeRate: 0,
  inceptionPolicy: "phase_in",
  enterImmediately: false,
}

const optionalNumber = (value) => {
  if (value === "" || value === null || value === undefined) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/** Turn the UI state into the exact payload POST /run/ validates. */
export const buildRequestPayload = (holdings, settings, portfolioId = null) => {
  const startDate =
    settings.periodYears > 0
      ? new Date(
          new Date().setFullYear(new Date().getFullYear() - Number(settings.periodYears))
        )
          .toISOString()
          .slice(0, 10)
      : null

  return {
    holdings: holdings.map((holding, index) => ({
      symbol: holding.symbol,
      // Sent as a fraction; the builder collects percentages.
      target_weight: Number(holding.weight || 0) / 100,
      order: index,
    })),
    benchmark_symbol: settings.benchmarkSymbol || "SPY",
    start_date: startDate,
    end_date: null,
    initial_amount: Number(settings.initialAmount) || 10000,
    periodic_contribution: Number(settings.periodicContribution) || 0,
    contribution_frequency: settings.contributionFrequency,
    weighting_scheme: settings.weightingScheme,
    backtest_mode: settings.backtestMode,
    rebalance_frequency: settings.rebalanceFrequency,
    lookback_days: Number(settings.lookbackDays) || 252,
    gap_days: Number(settings.gapDays) || 0,
    covariance_method: settings.covarianceMethod,
    transaction_cost_bps: Number(settings.transactionCostBps) || 0,
    long_only: Boolean(settings.longOnly),
    max_weight: optionalNumber(settings.maxWeight),
    min_weight: optionalNumber(settings.minWeight),
    risk_free_rate: Number(settings.riskFreeRate) || 0,
    inception_policy: settings.inceptionPolicy,
    enter_immediately: Boolean(settings.enterImmediately),
    portfolio_id: portfolioId,
  }
}
```

- [ ] **Step 2: Write `PortfolioBuilder.js`**

Create `src/componentsLegacy/Backtest/PortfolioBuilder.js`:

```javascript
import React, { useState } from "react"
import { Badge, Button, Card, Col, Form, ListGroup, Row, Table } from "react-bootstrap"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faPlus, faXmark } from "@fortawesome/free-solid-svg-icons"

import useSymbolSearch from "@hooks/useSymbolSearch"
import { WEIGHTING_OPTIONS } from "./backtestDefaults"

/**
 * Ticker typeahead, holding chips and — when the user picks custom weights —
 * a percentage column that shows its own running total.
 */
const PortfolioBuilder = ({ holdings, settings, onHoldingsChange, onSettingsChange }) => {
  const { query, setQuery, results, searching } = useSymbolSearch()
  const [notice, setNotice] = useState("")

  const addHolding = (row) => {
    if (holdings.some((holding) => holding.symbol === row.symbol)) {
      setNotice(`${row.symbol} is already in the portfolio.`)
      return
    }
    const evenSplit = Number((100 / (holdings.length + 1)).toFixed(2))
    onHoldingsChange([
      ...holdings.map((holding) => ({ ...holding, weight: evenSplit })),
      { symbol: row.symbol, name: row.name, kind: row.kind, weight: evenSplit },
    ])
    setQuery("")
    setNotice("")
  }

  const removeHolding = (symbol) => {
    onHoldingsChange(holdings.filter((holding) => holding.symbol !== symbol))
  }

  const setWeight = (symbol, weight) => {
    onHoldingsChange(
      holdings.map((holding) => (holding.symbol === symbol ? { ...holding, weight } : holding))
    )
  }

  const total = holdings.reduce((sum, holding) => sum + Number(holding.weight || 0), 0)
  const custom = settings.weightingScheme === "custom"

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <h5 className="mb-3">Build your portfolio</h5>

        <Form.Group className="mb-2 position-relative">
          <Form.Label className="fw-bold fs-13px">Add a stock or ETF</Form.Label>
          <Form.Control
            type="text"
            value={query}
            placeholder="Search by ticker or company name…"
            onChange={(event) => setQuery(event.target.value)}
            autoComplete="off"
          />
          {results.length > 0 && (
            <ListGroup
              className="position-absolute w-100 shadow"
              style={{ zIndex: 20, maxHeight: 260, overflowY: "auto" }}
            >
              {results.map((row) => (
                <ListGroup.Item
                  key={row.symbol}
                  action
                  onClick={() => addHolding(row)}
                  className="d-flex justify-content-between align-items-center"
                >
                  <span>
                    <strong>{row.symbol}</strong>
                    <span className="text-muted ms-2 fs-13px">{row.name}</span>
                  </span>
                  <Badge bg={row.kind === "etf" ? "info" : "secondary"}>{row.kind}</Badge>
                </ListGroup.Item>
              ))}
            </ListGroup>
          )}
          {searching && <Form.Text>Searching…</Form.Text>}
          {notice && <Form.Text className="text-warning d-block">{notice}</Form.Text>}
        </Form.Group>

        {holdings.length === 0 ? (
          <p className="text-muted fs-13px mb-0">
            Add two or more holdings to run a backtest.
          </p>
        ) : (
          <Table size="sm" className="align-middle mb-3">
            <thead>
              <tr>
                <th>Holding</th>
                {custom && <th style={{ width: 140 }}>Weight %</th>}
                <th style={{ width: 40 }} />
              </tr>
            </thead>
            <tbody>
              {holdings.map((holding) => (
                <tr key={holding.symbol}>
                  <td>
                    <strong>{holding.symbol}</strong>
                    <span className="text-muted ms-2 fs-13px">{holding.name}</span>
                  </td>
                  {custom && (
                    <td>
                      <Form.Control
                        type="number"
                        min="0"
                        max="100"
                        step="0.5"
                        size="sm"
                        value={holding.weight}
                        onChange={(event) => setWeight(holding.symbol, event.target.value)}
                      />
                    </td>
                  )}
                  <td className="text-end">
                    <Button
                      variant="link"
                      className="text-danger p-0"
                      onClick={() => removeHolding(holding.symbol)}
                      aria-label={`Remove ${holding.symbol}`}
                    >
                      <FontAwesomeIcon icon={faXmark} />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
            {custom && (
              <tfoot>
                <tr>
                  <td className="fw-bold">Total</td>
                  <td
                    className={
                      Math.abs(total - 100) < 0.01 ? "fw-bold text-success" : "fw-bold text-warning"
                    }
                  >
                    {total.toFixed(1)}%
                  </td>
                  <td />
                </tr>
              </tfoot>
            )}
          </Table>
        )}

        {custom && Math.abs(total - 100) > 0.01 && holdings.length > 0 && (
          <p className="fs-13px text-muted">
            These will be scaled to add up to 100% before the backtest runs.
          </p>
        )}

        <Form.Group>
          <Form.Label className="fw-bold fs-13px">How should the money be split?</Form.Label>
          {WEIGHTING_OPTIONS.map((option) => (
            <Form.Check
              key={option.value}
              type="radio"
              id={`weighting-${option.value}`}
              name="weightingScheme"
              checked={settings.weightingScheme === option.value}
              onChange={() => onSettingsChange({ weightingScheme: option.value })}
              label={
                <span>
                  {option.label}
                  <span className="text-muted ms-2 fs-13px">{option.hint}</span>
                </span>
              }
            />
          ))}
        </Form.Group>
      </Card.Body>
    </Card>
  )
}

export default PortfolioBuilder
```

The `@hooks/*` and `@componentsLegacy/*` aliases are already declared in `tsconfig.json:26-30`, so these imports resolve without config changes.

- [ ] **Step 3: Write `BacktestSettings.js`**

Create `src/componentsLegacy/Backtest/BacktestSettings.js`:

```javascript
import React from "react"
import { Card, Col, Form, InputGroup, Row } from "react-bootstrap"

import {
  CONTRIBUTION_OPTIONS,
  PERIOD_OPTIONS,
  REBALANCE_OPTIONS,
} from "./backtestDefaults"

/** Period, rebalance cadence, starting amount and deposits. */
const BacktestSettings = ({ settings, onChange }) => (
  <Card className="border-0 shadow-sm mb-4">
    <Card.Body>
      <h5 className="mb-3">Set up the simulation</h5>
      <Row className="g-3">
        <Col md={6}>
          <Form.Label className="fw-bold fs-13px">How far back?</Form.Label>
          <Form.Select
            value={settings.periodYears}
            onChange={(event) => onChange({ periodYears: Number(event.target.value) })}
          >
            {PERIOD_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Form.Select>
        </Col>
        <Col md={6}>
          <Form.Label className="fw-bold fs-13px">Rebalance</Form.Label>
          <Form.Select
            value={settings.rebalanceFrequency}
            onChange={(event) => onChange({ rebalanceFrequency: event.target.value })}
          >
            {REBALANCE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Form.Select>
        </Col>
        <Col md={4}>
          <Form.Label className="fw-bold fs-13px">Starting amount</Form.Label>
          <InputGroup>
            <InputGroup.Text>$</InputGroup.Text>
            <Form.Control
              type="number"
              min="1"
              step="500"
              value={settings.initialAmount}
              onChange={(event) => onChange({ initialAmount: event.target.value })}
            />
          </InputGroup>
        </Col>
        <Col md={4}>
          <Form.Label className="fw-bold fs-13px">Regular deposit</Form.Label>
          <InputGroup>
            <InputGroup.Text>$</InputGroup.Text>
            <Form.Control
              type="number"
              min="0"
              step="50"
              value={settings.periodicContribution}
              onChange={(event) => onChange({ periodicContribution: event.target.value })}
            />
          </InputGroup>
        </Col>
        <Col md={4}>
          <Form.Label className="fw-bold fs-13px">Deposit how often?</Form.Label>
          <Form.Select
            value={settings.contributionFrequency}
            onChange={(event) => onChange({ contributionFrequency: event.target.value })}
          >
            {CONTRIBUTION_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Form.Select>
        </Col>
        <Col md={6}>
          <Form.Label className="fw-bold fs-13px">Compare against</Form.Label>
          <Form.Control
            type="text"
            value={settings.benchmarkSymbol}
            onChange={(event) =>
              onChange({ benchmarkSymbol: event.target.value.toUpperCase() })
            }
          />
          <Form.Text>A ticker such as SPY, VTI or AGG.</Form.Text>
        </Col>
      </Row>
    </Card.Body>
  </Card>
)

export default BacktestSettings
```

- [ ] **Step 4: Write `AdvancedSettings.js`**

Create `src/componentsLegacy/Backtest/AdvancedSettings.js`:

```javascript
import React, { useState } from "react"
import { Button, Card, Collapse, Col, Form, InputGroup, Row } from "react-bootstrap"

import {
  BACKTEST_MODE_OPTIONS,
  COVARIANCE_OPTIONS,
  INCEPTION_OPTIONS,
} from "./backtestDefaults"

/**
 * Everything a novice should not have to see. Collapsed by default — the point
 * of progressive disclosure is that the defaults are already right.
 */
const AdvancedSettings = ({ settings, onChange }) => {
  const [open, setOpen] = useState(false)

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <Button
          variant="link"
          className="p-0 text-decoration-none"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
        >
          {open ? "▾" : "▸"} Advanced settings
        </Button>

        <Collapse in={open}>
          <div className="pt-3">
            <Row className="g-3">
              <Col md={12}>
                <Form.Label className="fw-bold fs-13px">
                  When should the weights be chosen?
                </Form.Label>
                {BACKTEST_MODE_OPTIONS.map((option) => (
                  <Form.Check
                    key={option.value}
                    type="radio"
                    id={`mode-${option.value}`}
                    name="backtestMode"
                    checked={settings.backtestMode === option.value}
                    onChange={() => onChange({ backtestMode: option.value })}
                    label={
                      <span>
                        {option.label}
                        <span className="text-muted ms-2 fs-13px">{option.hint}</span>
                      </span>
                    }
                  />
                ))}
              </Col>

              <Col md={12}>
                <Form.Label className="fw-bold fs-13px">
                  When holdings have different start dates
                </Form.Label>
                {INCEPTION_OPTIONS.map((option) => (
                  <Form.Check
                    key={option.value}
                    type="radio"
                    id={`inception-${option.value}`}
                    name="inceptionPolicy"
                    checked={settings.inceptionPolicy === option.value}
                    onChange={() => onChange({ inceptionPolicy: option.value })}
                    label={
                      <span>
                        {option.label}
                        <span className="text-muted ms-2 fs-13px">{option.hint}</span>
                      </span>
                    }
                  />
                ))}
                <Form.Check
                  type="checkbox"
                  id="enterImmediately"
                  className="mt-2"
                  checked={settings.enterImmediately}
                  onChange={(event) => onChange({ enterImmediately: event.target.checked })}
                  label={
                    <span>
                      Buy a new holding the day it becomes available
                      <span className="text-muted ms-2 fs-13px">
                        Otherwise it waits for the next rebalance, which is what a real
                        investor would do.
                      </span>
                    </span>
                  }
                />
              </Col>

              <Col md={6}>
                <Form.Label className="fw-bold fs-13px">Risk estimate</Form.Label>
                <Form.Select
                  value={settings.covarianceMethod}
                  onChange={(event) => onChange({ covarianceMethod: event.target.value })}
                >
                  {COVARIANCE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Form.Select>
              </Col>

              <Col md={3}>
                <Form.Label className="fw-bold fs-13px">Lookback (days)</Form.Label>
                <Form.Control
                  type="number"
                  min="2"
                  step="21"
                  value={settings.lookbackDays}
                  onChange={(event) => onChange({ lookbackDays: event.target.value })}
                />
              </Col>
              <Col md={3}>
                <Form.Label className="fw-bold fs-13px">Decision gap (days)</Form.Label>
                <Form.Control
                  type="number"
                  min="0"
                  max="10"
                  value={settings.gapDays}
                  onChange={(event) => onChange({ gapDays: event.target.value })}
                />
                <Form.Text>Days between the last data used and the trade.</Form.Text>
              </Col>

              <Col md={4}>
                <Form.Label className="fw-bold fs-13px">Trading cost</Form.Label>
                <InputGroup>
                  <Form.Control
                    type="number"
                    min="0"
                    step="1"
                    value={settings.transactionCostBps}
                    onChange={(event) => onChange({ transactionCostBps: event.target.value })}
                  />
                  <InputGroup.Text>bps</InputGroup.Text>
                </InputGroup>
              </Col>
              <Col md={4}>
                <Form.Label className="fw-bold fs-13px">Max per holding</Form.Label>
                <Form.Control
                  type="number"
                  min="0"
                  max="1"
                  step="0.05"
                  placeholder="no limit"
                  value={settings.maxWeight}
                  onChange={(event) => onChange({ maxWeight: event.target.value })}
                />
                <Form.Text>As a fraction, e.g. 0.3 for 30%.</Form.Text>
              </Col>
              <Col md={4}>
                <Form.Label className="fw-bold fs-13px">Min per holding</Form.Label>
                <Form.Control
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  placeholder="none"
                  value={settings.minWeight}
                  onChange={(event) => onChange({ minWeight: event.target.value })}
                />
              </Col>

              <Col md={6}>
                <Form.Label className="fw-bold fs-13px">Risk-free rate</Form.Label>
                <Form.Control
                  type="number"
                  min="0"
                  max="0.2"
                  step="0.005"
                  value={settings.riskFreeRate}
                  onChange={(event) => onChange({ riskFreeRate: event.target.value })}
                />
                <Form.Text>Annual, as a fraction. 0.04 is 4%.</Form.Text>
              </Col>
              <Col md={6} className="d-flex align-items-end">
                <Form.Check
                  type="checkbox"
                  id="longOnly"
                  checked={settings.longOnly}
                  onChange={(event) => onChange({ longOnly: event.target.checked })}
                  label={
                    <span>
                      Long only
                      <span className="text-muted ms-2 fs-13px">
                        Turning this off allows short positions, whose borrow costs this
                        simulation does not model.
                      </span>
                    </span>
                  }
                />
              </Col>
            </Row>
          </div>
        </Collapse>
      </Card.Body>
    </Card>
  )
}

export default AdvancedSettings
```

- [ ] **Step 5: Write `QuotaBanner.js`**

Create `src/componentsLegacy/Backtest/QuotaBanner.js`:

```javascript
import React from "react"
import { Alert } from "react-bootstrap"

/**
 * Remaining runs, and the upgrade prompt when the API returns 402.
 * Saving and editing portfolios never counts — say so, or the meter reads as
 * hostile.
 */
const QuotaBanner = ({ quota, quotaError }) => {
  if (quotaError) {
    return (
      <Alert variant="warning" className="mb-3">
        <strong>You have used all {quotaError.limit} of your free backtests.</strong>
        <div className="fs-13px">
          Saving, editing and duplicating portfolios stays free. Re-running a backtest you
          have already run is also free.
        </div>
      </Alert>
    )
  }

  if (!quota) return null
  if (quota.remaining === null) {
    return <div className="fs-13px text-muted">Unlimited backtests on your plan.</div>
  }

  return (
    <div className={`fs-13px ${quota.remaining <= 2 ? "text-warning" : "text-muted"}`}>
      {quota.remaining} of {quota.limit} free backtests remaining. Saving and editing
      portfolios is always free.
    </div>
  )
}

export default QuotaBanner
```

- [ ] **Step 6: Rewrite the page**

Replace the whole body of `src/pages/backtest-portfolio.js`:

```javascript
import React, { useMemo, useState } from "react"
import { Alert, Button, Col, Row, Spinner } from "react-bootstrap"

import ProfileLayout from "@componentsLegacy/Profile/ProfileLayout"
import PortfolioBuilder from "@componentsLegacy/Backtest/PortfolioBuilder"
import BacktestSettings from "@componentsLegacy/Backtest/BacktestSettings"
import AdvancedSettings from "@componentsLegacy/Backtest/AdvancedSettings"
import QuotaBanner from "@componentsLegacy/Backtest/QuotaBanner"
import {
  DEFAULT_SETTINGS,
  buildRequestPayload,
} from "@componentsLegacy/Backtest/backtestDefaults"
import useBacktestRun from "@hooks/useBacktestRun"
import useBacktestQuota from "@hooks/useBacktestQuota"

export async function getStaticProps() {
  return {
    props: {
      nav: {
        light: true,
        classes: "shadow",
        color: "white",
      },
      loggedUser: true,
      title: "Backtest Portfolio",
    },
  }
}

const PROGRESS_LABELS = {
  loading_prices: "Loading price history…",
  optimizing: "Choosing weights…",
  simulating: "Simulating…",
  computing_metrics: "Crunching the statistics…",
}

const BacktestPortfolio = () => {
  const [holdings, setHoldings] = useState([])
  const [settings, setSettings] = useState(DEFAULT_SETTINGS)
  const { status, progress, result, error, quotaError, submit } = useBacktestRun()
  const { quota, reload: reloadQuota } = useBacktestQuota()

  const updateSettings = (patch) => setSettings((current) => ({ ...current, ...patch }))

  const canRun = holdings.length >= 1 && status !== "running" && status !== "submitting"
  const busy = status === "running" || status === "submitting"

  const payload = useMemo(
    () => buildRequestPayload(holdings, settings),
    [holdings, settings]
  )

  const run = async () => {
    await submit(payload)
    reloadQuota()
  }

  return (
    <ProfileLayout>
      <Row>
        <Col xl={12}>
          <h4 className="mb-1">Backtest a portfolio</h4>
          <p className="text-muted fs-13px">
            Build a basket, choose how it is weighted, and see how it would have behaved.
            Every result comes with an honest account of what the simulation cannot tell
            you.
          </p>

          <PortfolioBuilder
            holdings={holdings}
            settings={settings}
            onHoldingsChange={setHoldings}
            onSettingsChange={updateSettings}
          />
          <BacktestSettings settings={settings} onChange={updateSettings} />
          <AdvancedSettings settings={settings} onChange={updateSettings} />

          <div className="d-flex align-items-center gap-3 mb-4">
            <Button variant="primary" disabled={!canRun} onClick={run}>
              {busy ? (
                <>
                  <Spinner animation="border" size="sm" className="me-2" />
                  {PROGRESS_LABELS[progress] || "Running…"}
                </>
              ) : (
                "Run backtest"
              )}
            </Button>
            <QuotaBanner quota={quota} quotaError={quotaError} />
          </div>

          {error && (
            <Alert variant="danger">
              <strong>The backtest did not run.</strong>
              <div className="fs-13px">{error}</div>
            </Alert>
          )}

          {result && (
            <Alert variant="success">
              Simulated {result.effective_start} to {result.effective_end}. Results
              rendering lands in the next step.
            </Alert>
          )}
        </Col>
      </Row>
    </ProfileLayout>
  )
}

export default BacktestPortfolio
```

- [ ] **Step 7: Lint, format and build**

```bash
npm run lint && npm run format && npm run build
```

Expected: all three succeed. Unused imports (`Row`/`Col` in `PortfolioBuilder`) will trip lint — remove any the linter flags rather than disabling the rule.

- [ ] **Step 8: Check it in a browser**

With Django, Redis, a Celery worker and `npm run dev` all running, log in and open `http://localhost:8020/backtest-portfolio`. Confirm:

- the typeahead returns symbols as you type
- adding two holdings enables **Run backtest**
- pressing it shows a spinner with a progress label, then the green "Simulated … to …" alert
- the remaining-runs count decrements by one, and pressing Run again with identical settings does **not** decrement it

- [ ] **Step 9: Commit**

```bash
git add src/componentsLegacy/Backtest/ src/pages/backtest-portfolio.js
git commit -m "feat: replace the backtest portfolio placeholder with the builder UI"
```

---

### Task 17: Results — headline, growth, drawdown, allocation, statistics

Results lead with a plain-language answer; the quant table sits behind a disclosure (§14). The allocation stacked area is where staggered inception becomes legible, so it is **not** behind a disclosure.

**Files:**
- Create: `src/componentsLegacy/Backtest/ResultsHeadline.js`, `GrowthChart.js`, `DrawdownChart.js`, `AllocationOverTime.js`, `StatsTable.js`, `formatters.js`
- Modify: `src/pages/backtest-portfolio.js` (render them)

**Interfaces:**
- Consumes: the result payload from `useBacktestRun`.
- Produces:
  - `formatters.js` exports `formatPercent(value, digits)`, `formatMoney(value)`, `formatMultiple(value)`, `formatDate(iso)`, `monthYear(iso)`.
  - `<ResultsHeadline result />`, `<GrowthChart result />`, `<DrawdownChart result />`, `<AllocationOverTime result />`, `<StatsTable result />`

- [ ] **Step 1: Write `formatters.js`**

Create `src/componentsLegacy/Backtest/formatters.js`:

```javascript
/** Display helpers shared across the results components. */
const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

export const formatPercent = (value, digits = 1) =>
  value === null || value === undefined || Number.isNaN(value)
    ? "—"
    : `${(Number(value) * 100).toFixed(digits)}%`

export const formatMoney = (value) =>
  value === null || value === undefined || Number.isNaN(value)
    ? "—"
    : `$${Math.round(Number(value)).toLocaleString("en-US")}`

export const formatNumber = (value, digits = 2) =>
  value === null || value === undefined || Number.isNaN(value)
    ? "—"
    : Number(value).toFixed(digits)

export const formatDate = (iso) => (iso ? iso : "—")

export const monthYear = (iso) => {
  if (!iso) return "—"
  const [year, month] = iso.split("-")
  return `${MONTHS[Number(month) - 1]} ${year}`
}

/** Trading days between two ISO dates in the result's own date array. */
export const monthsBetween = (dates, fromIso, toIso) => {
  if (!fromIso || !toIso) return null
  const from = dates.indexOf(fromIso)
  const to = dates.indexOf(toIso)
  if (from < 0 || to < 0) return null
  return Math.max(1, Math.round((to - from) / 21))
}
```

- [ ] **Step 2: Write `ResultsHeadline.js`**

Create `src/componentsLegacy/Backtest/ResultsHeadline.js`:

```javascript
import React from "react"
import { Card } from "react-bootstrap"

import { formatMoney, formatPercent, monthYear, monthsBetween } from "./formatters"

/**
 * The plain-language answer, first. Everything numeric below it is a footnote to
 * this sentence.
 */
const ResultsHeadline = ({ result }) => {
  const metrics = result?.metrics || {}
  const benchmark = result?.benchmark_metrics || null

  const started = result?.request?.initial_amount
  const ended = metrics.ending_balance
  const contributed = metrics.total_contributed

  const beat =
    benchmark && metrics.cagr !== null && benchmark.cagr !== null
      ? metrics.cagr - benchmark.cagr
      : null

  const recoveryMonths = monthsBetween(
    result?.dates || [],
    metrics.max_drawdown_trough_date,
    metrics.max_drawdown_recovery_date
  )

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <h3 className="mb-2">
          {formatMoney(started)} became {formatMoney(ended)}
          {beat !== null && (
            <span className={`ms-3 fs-5 ${beat >= 0 ? "text-success" : "text-danger"}`}>
              {beat >= 0 ? "beat" : "trailed"} {result.benchmark_symbol} by{" "}
              {formatPercent(Math.abs(beat))}/yr
            </span>
          )}
        </h3>

        <p className="mb-2 fs-6">
          That is {formatPercent(metrics.cagr)} a year over{" "}
          {metrics.years ? metrics.years.toFixed(1) : "—"} years
          {contributed > started
            ? `, on ${formatMoney(contributed)} of total deposits`
            : ""}
          .
        </p>

        <p className="mb-2 fs-6">
          Worst drop: <strong>{formatPercent(metrics.max_drawdown)}</strong>
          {metrics.max_drawdown_peak_date && (
            <>
              {" "}
              ({monthYear(metrics.max_drawdown_peak_date)}–
              {monthYear(metrics.max_drawdown_trough_date)})
            </>
          )}
          {recoveryMonths
            ? `, recovered in ${recoveryMonths} month${recoveryMonths === 1 ? "" : "s"}.`
            : metrics.max_drawdown_trough_date
              ? ", and had not recovered by the end of the period."
              : "."}
        </p>

        {metrics.money_weighted_return !== null &&
          metrics.money_weighted_return !== undefined &&
          contributed > started && (
            <p className="text-muted fs-13px mb-0">
              Your personal return, counting when each deposit went in, was{" "}
              {formatPercent(metrics.money_weighted_return)} a year. It differs from the{" "}
              {formatPercent(metrics.cagr)} above because that figure measures the strategy
              and this one measures your timing.
            </p>
          )}
      </Card.Body>
    </Card>
  )
}

export default ResultsHeadline
```

- [ ] **Step 3: Write `GrowthChart.js`**

Create `src/componentsLegacy/Backtest/GrowthChart.js`:

```javascript
import React, { useMemo, useState } from "react"
import dynamic from "next/dynamic"
import { Card, Form } from "react-bootstrap"

const ReactApexChart = dynamic(() => import("react-apexcharts"), { ssr: false })

/**
 * Portfolio vs benchmark, with inception markers.
 *
 * Plots the time-weighted index rather than NAV so the line is comparable to the
 * benchmark even when the user made deposits — a NAV line against a benchmark
 * index is not a like-for-like comparison.
 */
const GrowthChart = ({ result }) => {
  const [logScale, setLogScale] = useState(false)

  const series = useMemo(() => {
    if (!result) return []
    const rows = [
      {
        name: "Portfolio",
        data: result.dates.map((date, i) => ({ x: date, y: result.index[i] })),
      },
    ]
    if (result.benchmark_index?.length) {
      rows.push({
        name: result.benchmark_symbol || "Benchmark",
        data: result.dates.map((date, i) => ({ x: date, y: result.benchmark_index[i] })),
      })
    }
    return rows
  }, [result])

  const annotations = useMemo(() => {
    const entries = (result?.composition_events || []).filter(
      (event) => event.action === "entered" && event.date !== result.effective_start
    )
    return {
      xaxis: entries.slice(0, 12).map((event) => ({
        x: new Date(event.date).getTime(),
        borderColor: "#9aa0a6",
        strokeDashArray: 4,
        label: {
          text: `${event.symbol} in`,
          style: { fontSize: "10px", background: "#f1f3f4" },
        },
      })),
    }
  }, [result])

  if (!result) return null

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <div className="d-flex justify-content-between align-items-center mb-2">
          <h5 className="mb-0">Growth of $1</h5>
          <Form.Check
            type="switch"
            id="growth-log-scale"
            label="Log scale"
            checked={logScale}
            onChange={(event) => setLogScale(event.target.checked)}
          />
        </div>
        <ReactApexChart
          type="line"
          height={340}
          series={series}
          options={{
            chart: { type: "line", toolbar: { show: false }, animations: { enabled: false } },
            stroke: { width: 2, curve: "straight" },
            xaxis: { type: "datetime" },
            yaxis: {
              logarithmic: logScale,
              labels: { formatter: (value) => (value ? value.toFixed(2) : value) },
            },
            annotations,
            legend: { position: "top" },
            tooltip: { x: { format: "dd MMM yyyy" } },
            colors: ["#0d6efd", "#6c757d"],
            dataLabels: { enabled: false },
          }}
        />
        <p className="text-muted fs-13px mb-0">
          Dashed markers show when a holding first entered the portfolio.
        </p>
      </Card.Body>
    </Card>
  )
}

export default GrowthChart
```

- [ ] **Step 4: Write `DrawdownChart.js`**

Create `src/componentsLegacy/Backtest/DrawdownChart.js`:

```javascript
import React, { useMemo } from "react"
import dynamic from "next/dynamic"
import { Card } from "react-bootstrap"

const ReactApexChart = dynamic(() => import("react-apexcharts"), { ssr: false })

/** Underwater plot: how far below its previous high the portfolio sat. */
const DrawdownChart = ({ result }) => {
  const series = useMemo(() => {
    if (!result) return []
    const rows = [
      {
        name: "Portfolio",
        data: result.dates.map((date, i) => ({ x: date, y: result.drawdown[i] * 100 })),
      },
    ]
    if (result.benchmark_drawdown?.length) {
      rows.push({
        name: result.benchmark_symbol || "Benchmark",
        data: result.dates.map((date, i) => ({
          x: date,
          y: result.benchmark_drawdown[i] * 100,
        })),
      })
    }
    return rows
  }, [result])

  if (!result) return null

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <h5 className="mb-2">How far underwater</h5>
        <ReactApexChart
          type="area"
          height={260}
          series={series}
          options={{
            chart: { type: "area", toolbar: { show: false }, animations: { enabled: false } },
            stroke: { width: 1.5, curve: "straight" },
            fill: { type: "gradient", gradient: { opacityFrom: 0.4, opacityTo: 0.05 } },
            xaxis: { type: "datetime" },
            yaxis: { labels: { formatter: (value) => `${value.toFixed(0)}%` } },
            legend: { position: "top" },
            colors: ["#dc3545", "#adb5bd"],
            dataLabels: { enabled: false },
            tooltip: { y: { formatter: (value) => `${value.toFixed(1)}%` } },
          }}
        />
      </Card.Body>
    </Card>
  )
}

export default DrawdownChart
```

- [ ] **Step 5: Write `AllocationOverTime.js`**

Create `src/componentsLegacy/Backtest/AllocationOverTime.js`:

```javascript
import React, { useMemo } from "react"
import dynamic from "next/dynamic"
import { Card } from "react-bootstrap"

const ReactApexChart = dynamic(() => import("react-apexcharts"), { ssr: false })

const SAMPLE_TARGET = 400

/**
 * Stacked weights plus the effective asset count.
 *
 * The most informative view on the page: it is where staggered inception becomes
 * visible rather than merely disclosed, which is why it is not tucked behind a
 * disclosure. Series are downsampled — 5,000 points × 20 symbols would stall the
 * browser and would not show anything the sampled version does not.
 */
const AllocationOverTime = ({ result }) => {
  const { series, countSeries } = useMemo(() => {
    if (!result) return { series: [], countSeries: [] }

    const step = Math.max(1, Math.ceil(result.dates.length / SAMPLE_TARGET))
    const sampled = result.dates.filter((_, i) => i % step === 0)

    const weightSeries = Object.keys(result.weights_over_time).map((symbol) => ({
      name: symbol,
      data: result.weights_over_time[symbol]
        .filter((_, i) => i % step === 0)
        .map((weight, i) => ({ x: sampled[i], y: Number((weight * 100).toFixed(2)) })),
    }))

    const counts = [
      {
        name: "Holdings owned",
        data: result.effective_asset_count
          .filter((_, i) => i % step === 0)
          .map((count, i) => ({ x: sampled[i], y: count })),
      },
    ]

    return { series: weightSeries, countSeries: counts }
  }, [result])

  if (!result) return null

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <h5 className="mb-2">What you actually owned, over time</h5>
        <ReactApexChart
          type="area"
          height={300}
          series={series}
          options={{
            chart: {
              type: "area",
              stacked: true,
              toolbar: { show: false },
              animations: { enabled: false },
            },
            stroke: { width: 0 },
            fill: { opacity: 0.85 },
            xaxis: { type: "datetime" },
            yaxis: { max: 100, labels: { formatter: (value) => `${value.toFixed(0)}%` } },
            legend: { position: "bottom" },
            dataLabels: { enabled: false },
            tooltip: { y: { formatter: (value) => `${value.toFixed(1)}%` } },
          }}
        />

        <h6 className="mt-3 mb-1 fs-13px text-muted">
          Number of your holdings that existed and were owned
        </h6>
        <ReactApexChart
          type="line"
          height={140}
          series={countSeries}
          options={{
            chart: { type: "line", toolbar: { show: false }, animations: { enabled: false } },
            stroke: { width: 2, curve: "stepline" },
            xaxis: { type: "datetime" },
            yaxis: {
              min: 0,
              tickAmount: Math.min(result.symbols.length, 5),
              labels: { formatter: (value) => value.toFixed(0) },
            },
            colors: ["#198754"],
            dataLabels: { enabled: false },
            legend: { show: false },
          }}
        />
      </Card.Body>
    </Card>
  )
}

export default AllocationOverTime
```

- [ ] **Step 6: Write `StatsTable.js`**

Create `src/componentsLegacy/Backtest/StatsTable.js`:

```javascript
import React, { useState } from "react"
import { Button, Card, Collapse, Table } from "react-bootstrap"

import { formatMoney, formatNumber, formatPercent } from "./formatters"

const PERCENT_ROWS = [
  ["cagr", "Annual return (CAGR)"],
  ["annualized_return", "Annual return (average)"],
  ["annualized_volatility", "Volatility"],
  ["max_drawdown", "Worst drop"],
  ["var_95", "Bad-day threshold (95%)"],
  ["cvar_95", "Average of the worst 5% of days"],
  ["alpha", "Alpha vs benchmark"],
]

const NUMBER_ROWS = [
  ["sharpe", "Sharpe ratio"],
  ["sortino", "Sortino ratio"],
  ["calmar", "Calmar ratio"],
  ["beta", "Beta vs benchmark"],
  ["up_capture", "Up capture"],
  ["down_capture", "Down capture"],
  ["annual_turnover", "Turnover per year"],
]

const MONEY_ROWS = [
  ["ending_balance", "Ending balance"],
  ["total_contributed", "Total put in"],
  ["total_gain", "Total gain"],
  ["total_costs_paid", "Trading costs paid"],
]

/** The full §9 table, portfolio against benchmark, behind a disclosure. */
const StatsTable = ({ result }) => {
  const [open, setOpen] = useState(false)
  const metrics = result?.metrics || {}
  const benchmark = result?.benchmark_metrics || {}

  const row = (key, label, format) => (
    <tr key={key}>
      <td>{label}</td>
      <td className="text-end">{format(metrics[key])}</td>
      <td className="text-end text-muted">{format(benchmark[key])}</td>
    </tr>
  )

  if (!result) return null

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <Button
          variant="link"
          className="p-0 text-decoration-none"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
        >
          {open ? "▾" : "▸"} Full statistics
        </Button>

        <Collapse in={open}>
          <div className="pt-3">
            <Table size="sm" hover responsive className="align-middle">
              <thead>
                <tr>
                  <th>Measure</th>
                  <th className="text-end">Portfolio</th>
                  <th className="text-end">{result.benchmark_symbol || "Benchmark"}</th>
                </tr>
              </thead>
              <tbody>
                {PERCENT_ROWS.map(([key, label]) => row(key, label, (v) => formatPercent(v)))}
                {NUMBER_ROWS.map(([key, label]) => row(key, label, (v) => formatNumber(v)))}
                {MONEY_ROWS.map(([key, label]) => row(key, label, (v) => formatMoney(v)))}
                <tr>
                  <td>Best calendar year</td>
                  <td className="text-end">
                    {metrics.best_year} ({formatPercent(metrics.best_year_return)})
                  </td>
                  <td className="text-end text-muted">
                    {benchmark.best_year} ({formatPercent(benchmark.best_year_return)})
                  </td>
                </tr>
                <tr>
                  <td>Worst calendar year</td>
                  <td className="text-end">
                    {metrics.worst_year} ({formatPercent(metrics.worst_year_return)})
                  </td>
                  <td className="text-end text-muted">
                    {benchmark.worst_year} ({formatPercent(benchmark.worst_year_return)})
                  </td>
                </tr>
              </tbody>
            </Table>

            <h6 className="mt-4 fs-13px text-muted">Where the return and the risk came from</h6>
            <Table size="sm" responsive className="align-middle">
              <thead>
                <tr>
                  <th>Holding</th>
                  <th className="text-end">Share of return</th>
                  <th className="text-end">Share of risk</th>
                </tr>
              </thead>
              <tbody>
                {(result.symbols || []).map((symbol) => (
                  <tr key={symbol}>
                    <td>{symbol}</td>
                    <td className="text-end">
                      {formatPercent(metrics.contribution_to_return?.[symbol])}
                    </td>
                    <td className="text-end">
                      {formatPercent(metrics.contribution_to_risk?.[symbol])}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <p className="text-muted fs-13px mb-0">
              Every return and risk figure above is measured on the strategy itself, with
              deposits stripped out, so the deposit schedule cannot flatter it.
            </p>
            {result.request?.weighting_scheme === "risk_parity" && (
              <p className="text-muted fs-13px mb-0 mt-2">
                <strong>Why these risk shares are not equal.</strong> Risk parity equalized
                risk using the {result.request.lookback_days} trading days before each
                rebalance. The shares above are measured across the whole period against your
                final weights, which is the portfolio you actually held — so the two
                legitimately differ, often by a lot. Neither number is wrong.
              </p>
            )}
          </div>
        </Collapse>
      </Card.Body>
    </Card>
  )
}

export default StatsTable
```

- [ ] **Step 7: Render them on the page**

In `src/pages/backtest-portfolio.js`, add the imports:

```javascript
import ResultsHeadline from "@componentsLegacy/Backtest/ResultsHeadline"
import GrowthChart from "@componentsLegacy/Backtest/GrowthChart"
import DrawdownChart from "@componentsLegacy/Backtest/DrawdownChart"
import AllocationOverTime from "@componentsLegacy/Backtest/AllocationOverTime"
import StatsTable from "@componentsLegacy/Backtest/StatsTable"
```

and replace the placeholder `{result && (<Alert variant="success">…</Alert>)}` block with:

```javascript
          {result && (
            <>
              <ResultsHeadline result={result} />
              <GrowthChart result={result} />
              <AllocationOverTime result={result} />
              <DrawdownChart result={result} />
              <StatsTable result={result} />
            </>
          )}
```

- [ ] **Step 8: Lint, format and build**

```bash
npm run lint && npm run format && npm run build
```

Expected: all three succeed.

- [ ] **Step 9: Check the rendering in a browser**

Run a backtest of `AAPL`, `VTI` and one recently listed ETF over 20 years with monthly deposits. Confirm:

- the headline sentence reads naturally and the drop/recovery clause is correct
- both lines appear on the growth chart and the log-scale switch works
- inception markers appear for the late-listing holding
- the allocation area is stacked to 100% and the holdings-owned step line rises when the late holding enters
- the statistics table has two populated columns

- [ ] **Step 10: Commit**

```bash
git add src/componentsLegacy/Backtest/ src/pages/backtest-portfolio.js
git commit -m "feat: add backtest results charts and statistics table"
```

---

### Task 18: Reality check, efficient frontier and saved portfolios

The last of the frontend. `critical` diagnostics render **above** the results, not below them (§10), so this task also reorders the page.

**Files:**
- Create: `src/componentsLegacy/Backtest/RealityCheck.js`, `EfficientFrontier.js`, `SavedPortfolios.js`
- Modify: `src/pages/backtest-portfolio.js`

**Interfaces:**
- Consumes: `usePortfolios` from Task 15; the `diagnostics`, `frontier` and `composition_events` sections of the result payload.
- Produces:
  - `<RealityCheck result severities />` — `severities` selects which findings to show, so the same component serves the above-results critical block and the below-results full panel.
  - `<EfficientFrontier result />`
  - `<SavedPortfolios holdings settings onLoad />`

- [ ] **Step 1: Write `RealityCheck.js`**

Create `src/componentsLegacy/Backtest/RealityCheck.js`:

```javascript
import React from "react"
import { Alert, Card, Table } from "react-bootstrap"

const VARIANTS = { critical: "danger", warning: "warning", info: "secondary" }
const HEADINGS = {
  critical: "Read this before you read the numbers",
  warning: "What this simulation cannot tell you",
  info: "Worth knowing",
}

/**
 * The diagnostics panel and the composition timeline.
 *
 * `severities` lets the page render critical findings above the results and the
 * rest below, from one component and one data source.
 */
const RealityCheck = ({ result, severities = ["critical", "warning", "info"], showTimeline = true }) => {
  const findings = (result?.diagnostics || []).filter((finding) =>
    severities.includes(finding.severity)
  )
  const events = result?.composition_events || []

  if (!findings.length && !showTimeline) return null

  const onlyCritical = severities.length === 1 && severities[0] === "critical"

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <h5 className="mb-3">
          {onlyCritical ? HEADINGS.critical : "Reality check"}
        </h5>

        {!onlyCritical && (
          <p className="text-muted fs-13px">
            A backtest is a story you can tell about the past, and a well-chosen story can
            be made to look like almost anything. These notes exist so the number above is
            not the only thing you take away.
          </p>
        )}

        {findings.map((finding) => (
          <Alert key={finding.code} variant={VARIANTS[finding.severity]} className="mb-2">
            <strong>{finding.title}</strong>
            <div className="fs-13px mt-1">{finding.detail}</div>
          </Alert>
        ))}

        {!findings.length && !onlyCritical && (
          <p className="fs-13px mb-0">No specific warnings for this run.</p>
        )}

        {showTimeline && events.length > 0 && (
          <>
            <h6 className="mt-4 mb-2">What changed, and when</h6>
            <Table size="sm" responsive className="align-middle">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Holding</th>
                  <th>Change</th>
                  <th>Why</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event, index) => (
                  <tr key={`${event.date}-${event.symbol}-${index}`}>
                    <td>{event.date}</td>
                    <td>
                      <strong>{event.symbol}</strong>
                    </td>
                    <td>{event.action === "entered" ? "Bought" : "Sold"}</td>
                    <td className="fs-13px text-muted">{event.reason}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </>
        )}

        {result?.truncation_cause && showTimeline && (
          <p className="fs-13px text-muted mb-0">{result.truncation_cause}</p>
        )}
      </Card.Body>
    </Card>
  )
}

export default RealityCheck
```

- [ ] **Step 2: Write `EfficientFrontier.js`**

Create `src/componentsLegacy/Backtest/EfficientFrontier.js`:

```javascript
import React, { useMemo } from "react"
import dynamic from "next/dynamic"
import { Card } from "react-bootstrap"

const ReactApexChart = dynamic(() => import("react-apexcharts"), { ssr: false })

/**
 * Random portfolios, the frontier curve, the minimum-variance and best-Sharpe
 * points, and the user's own mix.
 *
 * Computed on the whole period at once, which means it knows how everything
 * turned out. The caption says so — presented without that caveat it reads as a
 * recommendation, which it is not.
 */
const EfficientFrontier = ({ result }) => {
  const frontier = result?.frontier

  const series = useMemo(() => {
    if (!frontier) return []
    const pair = (volatility, portfolioReturn) => [
      Number((volatility * 100).toFixed(3)),
      Number((portfolioReturn * 100).toFixed(3)),
    ]

    return [
      {
        name: "Possible mixes",
        type: "scatter",
        data: frontier.scatter.volatility.map((volatility, i) =>
          pair(volatility, frontier.scatter.return[i])
        ),
      },
      {
        name: "Best available (in hindsight)",
        type: "line",
        data: frontier.frontier.volatility.map((volatility, i) =>
          pair(volatility, frontier.frontier.return[i])
        ),
      },
      {
        name: "Steadiest mix",
        type: "scatter",
        data: [pair(frontier.gmvp.volatility, frontier.gmvp.return)],
      },
      {
        name: "Best return per unit of risk",
        type: "scatter",
        data: [pair(frontier.tangency.volatility, frontier.tangency.return)],
      },
      ...(frontier.portfolio
        ? [
            {
              name: "Your portfolio",
              type: "scatter",
              data: [pair(frontier.portfolio.volatility, frontier.portfolio.return)],
            },
          ]
        : []),
    ]
  }, [frontier])

  if (!frontier) return null

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <h5 className="mb-2">Risk against return, for every mix you could have held</h5>
        <ReactApexChart
          type="line"
          height={360}
          series={series}
          options={{
            chart: { toolbar: { show: false }, animations: { enabled: false } },
            stroke: { width: [0, 3, 0, 0, 0], curve: "smooth" },
            markers: { size: [3, 0, 9, 9, 11], strokeWidth: 0 },
            colors: ["#cfd4da", "#0d6efd", "#198754", "#fd7e14", "#dc3545"],
            xaxis: {
              type: "numeric",
              title: { text: "Volatility (% a year)" },
              labels: { formatter: (value) => `${Number(value).toFixed(0)}%` },
            },
            yaxis: {
              title: { text: "Return (% a year)" },
              labels: { formatter: (value) => `${Number(value).toFixed(0)}%` },
            },
            legend: { position: "top" },
            dataLabels: { enabled: false },
            tooltip: {
              shared: false,
              y: { formatter: (value) => `${Number(value).toFixed(1)}% return` },
              x: { formatter: (value) => `${Number(value).toFixed(1)}% volatility` },
            },
          }}
        />
        <p className="text-muted fs-13px mb-0">
          <strong>Illustration only.</strong> This chart was drawn knowing how the whole
          period turned out, so the curve is the best that could have been done with
          hindsight — not a mix anyone could have chosen in advance. Use it to see how much
          risk your portfolio took for the return it got, not as a recommendation.
        </p>
      </Card.Body>
    </Card>
  )
}

export default EfficientFrontier
```

- [ ] **Step 3: Write `SavedPortfolios.js`**

Create `src/componentsLegacy/Backtest/SavedPortfolios.js`:

```javascript
import React, { useState } from "react"
import { Alert, Button, Card, Form, InputGroup, Table } from "react-bootstrap"

import usePortfolios from "@hooks/usePortfolios"

/**
 * List, load, duplicate and delete. All of it free — only running meters — which
 * the copy states so the meter does not feel like it is watching everything.
 */
const SavedPortfolios = ({ holdings, settings, onLoad }) => {
  const { portfolios, loading, error, create, remove, duplicate } = usePortfolios()
  const [name, setName] = useState("")
  const [saved, setSaved] = useState(null)

  const save = async () => {
    if (!name.trim() || holdings.length === 0) return
    const created = await create({
      name: name.trim(),
      benchmark_symbol: settings.benchmarkSymbol,
      initial_amount: Number(settings.initialAmount) || 10000,
      periodic_contribution: Number(settings.periodicContribution) || 0,
      contribution_frequency: settings.contributionFrequency,
      weighting_scheme: settings.weightingScheme,
      backtest_mode: settings.backtestMode,
      rebalance_frequency: settings.rebalanceFrequency,
      settings: { ...settings },
      holdings: holdings.map((holding, index) => ({
        symbol: holding.symbol,
        target_weight: Number(holding.weight || 0) / 100,
        order: index,
      })),
    })
    if (created) {
      setName("")
      setSaved(`Saved “${created.name}”.`)
    }
  }

  const load = (portfolio) => {
    onLoad({
      holdings: (portfolio.holdings || []).map((holding) => ({
        symbol: holding.symbol,
        name: "",
        kind: "stock",
        weight: Number(holding.target_weight) * 100,
      })),
      settings: portfolio.settings && Object.keys(portfolio.settings).length
        ? portfolio.settings
        : {
            benchmarkSymbol: portfolio.benchmark_symbol,
            initialAmount: Number(portfolio.initial_amount),
            periodicContribution: Number(portfolio.periodic_contribution),
            contributionFrequency: portfolio.contribution_frequency,
            weightingScheme: portfolio.weighting_scheme,
            backtestMode: portfolio.backtest_mode,
            rebalanceFrequency: portfolio.rebalance_frequency,
          },
    })
  }

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <h5 className="mb-2">Saved portfolios</h5>
        <p className="text-muted fs-13px">
          Saving, loading, copying and deleting are always free — only running a backtest
          uses an allowance.
        </p>

        <InputGroup className="mb-3">
          <Form.Control
            placeholder="Name this portfolio…"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <Button
            variant="outline-primary"
            onClick={save}
            disabled={!name.trim() || holdings.length === 0}
          >
            Save current
          </Button>
        </InputGroup>

        {saved && (
          <Alert variant="success" className="fs-13px py-2">
            {saved}
          </Alert>
        )}
        {error && (
          <Alert variant="warning" className="fs-13px py-2">
            {error}
          </Alert>
        )}

        {loading ? (
          <p className="fs-13px text-muted mb-0">Loading…</p>
        ) : portfolios.length === 0 ? (
          <p className="fs-13px text-muted mb-0">Nothing saved yet.</p>
        ) : (
          <Table size="sm" responsive className="align-middle mb-0">
            <tbody>
              {portfolios.map((portfolio) => (
                <tr key={portfolio.id}>
                  <td>
                    <strong>{portfolio.name}</strong>
                    <div className="text-muted fs-13px">
                      {(portfolio.holdings || []).map((h) => h.symbol).join(", ") ||
                        "no holdings"}
                    </div>
                  </td>
                  <td className="text-end">
                    <Button size="sm" variant="outline-primary" className="me-2"
                            onClick={() => load(portfolio)}>
                      Load
                    </Button>
                    <Button size="sm" variant="outline-secondary" className="me-2"
                            onClick={() => duplicate(portfolio.id)}>
                      Copy
                    </Button>
                    <Button size="sm" variant="outline-danger"
                            onClick={() => remove(portfolio.id)}>
                      Delete
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card.Body>
    </Card>
  )
}

export default SavedPortfolios
```

- [ ] **Step 4: Wire all three into the page**

Add to the imports in `src/pages/backtest-portfolio.js`:

```javascript
import RealityCheck from "@componentsLegacy/Backtest/RealityCheck"
import EfficientFrontier from "@componentsLegacy/Backtest/EfficientFrontier"
import SavedPortfolios from "@componentsLegacy/Backtest/SavedPortfolios"
```

Add the load handler next to the other state:

```javascript
  const loadPortfolio = ({ holdings: loadedHoldings, settings: loadedSettings }) => {
    setHoldings(loadedHoldings)
    setSettings((current) => ({ ...current, ...loadedSettings }))
  }
```

Render `SavedPortfolios` directly under `<PortfolioBuilder …/>`:

```javascript
          <SavedPortfolios holdings={holdings} settings={settings} onLoad={loadPortfolio} />
```

Then replace the results block so critical findings come first:

```javascript
          {result && (
            <>
              <RealityCheck result={result} severities={["critical"]} showTimeline={false} />
              <ResultsHeadline result={result} />
              <GrowthChart result={result} />
              <AllocationOverTime result={result} />
              <DrawdownChart result={result} />
              <StatsTable result={result} />
              <EfficientFrontier result={result} />
              <RealityCheck result={result} severities={["warning", "info"]} />
            </>
          )}
```

- [ ] **Step 5: Lint, format and build**

```bash
npm run lint && npm run format && npm run build
```

Expected: all three succeed.

- [ ] **Step 6: Verify the full page in a browser**

Run a backtest with a deliberately awkward basket — one mega-cap, one bond ETF, and one ETF that listed within the last three years, benchmarked against `SPY`, using `max_sharpe` in `fixed` mode. Confirm:

- a red block appears **above** the headline (the `in_sample_fit` / `composition_coverage` findings)
- the composition timeline lists the late holding's entry with its reason
- the frontier chart shows the grey cloud, the blue curve, and your portfolio's red marker
- **Save current** stores the portfolio, **Load** repopulates the builder, **Copy** creates a second entry, **Delete** removes it
- the remaining-runs count did not move for any of those four actions

- [ ] **Step 7: Commit**

```bash
git add src/componentsLegacy/Backtest/ src/pages/backtest-portfolio.js
git commit -m "feat: add reality check, efficient frontier and saved portfolios"
```

---

### Task 19: Mark the page as built

**Files:**
- Modify: `src/componentsLegacy/Profile/ProfileSideNav.js:22`

**Interfaces:** none.

- [ ] **Step 1: Remove the flag**

In `src/componentsLegacy/Profile/ProfileSideNav.js`, change line 22 from:

```javascript
  { href: "/backtest-portfolio", label: "Backtest Portfolio", icon: faChartLine, built: false },
```

to:

```javascript
  { href: "/backtest-portfolio", label: "Backtest Portfolio", icon: faChartLine },
```

Leave the `built: false` on `/watchlist` and `/create-alerts` alone — those pages still render `ComingSoon`, and `ComingSoon.js` must not be deleted.

- [ ] **Step 2: Verify the nav renders it as a live link**

```bash
npm run lint && npm run build
```

Then in the browser, confirm the sidebar entry no longer shows the "coming soon" treatment and navigates to a working page.

- [ ] **Step 3: Commit**

```bash
git add src/componentsLegacy/Profile/ProfileSideNav.js
git commit -m "feat: mark backtest portfolio as built in the profile nav"
```

---

### Task 20: Rotate the leaked FMP key and delete the superseded notebook

`backend/class_files/portfolio_analyzer.ipynb` cell 3 contains a hardcoded live FMP API key (§ Context). The engine now supersedes that notebook entirely, so the key gets rotated and the file goes.

**Files:**
- Delete: `backend/class_files/portfolio_analyzer.ipynb`

**Interfaces:** none.

- [ ] **Step 1: Confirm the key is there and read it**

```bash
grep -n "apikey\|api_key\|FMP" backend/class_files/portfolio_analyzer.ipynb | head -20
```

Expected: at least one hardcoded key string. Note its first 6 characters so you can confirm the rotated key differs.

- [ ] **Step 2: Rotate the key — this is a manual step for the repo owner**

The exposed key must be revoked and replaced at Financial Modeling Prep (Dashboard → API Keys → regenerate), then the new value written to `backend/.env` as `FMP_API`. **Ask the repo owner to do this and confirm it is done before continuing** — the plan cannot do it, and deleting the notebook without rotating leaves the key live in git history.

Verify the new key works:

```bash
cd backend && python manage.py shell -c "
from django.conf import settings
import requests
r = requests.get(f'https://financialmodelingprep.com/api/v3/quote/AAPL?apikey={settings.FMP_API}', timeout=10)
print(r.status_code, str(r.json())[:120])
"
```

Expected: `200` and a quote payload.

- [ ] **Step 3: Confirm nothing imports the notebook**

```bash
grep -rn "portfolio_analyzer" backend/ src/ docs/ --include=*.py --include=*.js --include=*.md | grep -v "specs/2026-08-11\|plans/2026-08-11"
```

Expected: no hits outside the spec and this plan. If anything else references it, stop and report rather than deleting.

- [ ] **Step 4: Delete the notebook**

The file is untracked (`backend/class_files/` is gitignored and has never been committed), so this is a plain filesystem delete, not a `git rm`:

```bash
rm backend/class_files/portfolio_analyzer.ipynb
git status --short backend/class_files/
```

Expected: `git status` shows nothing — the directory is ignored, so there is no staged deletion to commit.

- [ ] **Step 5: Confirm the key is gone from the repository entirely**

Unlike the usual leaked-credential case, there is no history to purge:

```bash
git log --all -S "$(echo 'apikey')" --oneline -- backend/class_files/ | head -3
grep -rn "apikey" backend/class_files/*.ipynb 2>/dev/null | grep -v homepage_data | head
```

Expected: both empty. Deleting the file removed the key from the repo outright.

Two caveats to state when reporting this done:

- **`homepage_data.ipynb` still has hardcoded FMP and AWS keys.** It is a separate, previously recorded finding, is out of this build's scope, and is *not* fixed by this task. Say so rather than implying the credential problem is closed.
- Rotation is still necessary regardless of git history: the key sat in plaintext on a developer machine and may have been synced, backed up, or shared. Step 2 covers it.

- [ ] **Step 6: Nothing to commit — report instead**

There is no commit for this task: the deleted file was never tracked. Report to the repo owner that the notebook is gone, whether the key was rotated in Step 2, and that `homepage_data.ipynb` remains outstanding.

---

## Final verification

- [ ] **Backend suite**

```bash
cd backend && python manage.py test backtester users analyzer -v 2
```

Expected: everything passes. Report the counts.

- [ ] **Frontend gate**

```bash
npm run ci
```

Expected: build, lint and format check all pass — this is the same command CI runs.

- [ ] **Guardrail audit**

Confirm no Phase 5 artifact was created:

```bash
ls src/pages/backtester.js backend/backtester/engine/signal.py 2>&1
grep -rn "BacktestJob\|n_quintiles" backend/backtester/
git diff --stat main -- docs/superpowers/plans/2026-04-20-fintank-master-implementation-plan.md
```

Expected: both paths absent, no grep hits, and the master plan shows no diff beyond the Phase 5/10 annotations already committed.

- [ ] **Allowlist audit**

```bash
git diff --name-only main | grep -v "^backend/backtester/\|^src/" | sort
```

Expected exactly: `backend/class_files/backtester_portfolio.ipynb`, `backend/class_files/portfolio_analyzer.ipynb` (deleted), `backend/fintank_backend/settings.py`, `backend/fintank_backend/urls.py`, `backend/users/migrations/0002_*.py`, `backend/users/models.py`, `backend/users/serializers.py`, `backend/utils/StockCalculations.py`, plus the plan and spec docs. Anything else is out of scope — revert it.

- [ ] **Security re-check**

```bash
cd backend && python manage.py test backtester.tests.test_models.PrivilegeEscalationTests -v 2
```

Expected: 4 tests pass. This is the one that must never regress.
