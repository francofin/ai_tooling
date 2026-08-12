# Portfolio Backtest & Optimization Engine

**Status:** Design approved, not yet implemented
**Implements:** §8.7 V2 ("Strategy Simulation") of `2026-04-20-fintank-platform-design.md`
**Research basis:** `backend/class_files/backtest_research_context/` (9 PDFs, principally Palomar 2025 chapters 6 and 8)

---

## Context

Fintank has a stubbed `/backtest-portfolio` page in the authenticated profile area
(`src/pages/backtest-portfolio.js`, currently rendering `ComingSoon`) and a side-nav
entry marked `built: false`. This spec fills it: a tool that lets an everyday investor
assemble a basket of stocks and ETFs, weight it either by hand or by a real optimizer,
and simulate how it would have performed — with honest disclosure of what the
simulation can and cannot tell them.

The data foundation already exists. `stock_data/stock_prices/daily/{SYMBOL}_prices.parquet`
on S3 holds ~17,200 symbol-addressable price histories (~10,100 index constituents plus
~7,100 ETFs), written by the v2 pipeline documented in `backend/class_files/DATA_UPLOAD.md`.
`index_data/index_prices_v2/` holds ~65 benchmark series. Nothing new needs to be ingested.

This supersedes `backend/class_files/portfolio_analyzer.ipynb`, a pre-S3 prototype that
refetches everything from FMP on every call.

> **Security note:** `portfolio_analyzer.ipynb` cell 3 contains a hardcoded live FMP API
> key. It should be rotated and the notebook deleted once this engine lands. This mirrors
> the same finding previously recorded against `homepage_data.ipynb`.

### Relationship to the platform spec

| Platform spec requirement | How this spec complies |
|---|---|
| §2 — on-demand jobs run async via Celery, never block the API thread | `POST /run/` enqueues, returns `task_id`; frontend polls |
| §3 — `UserProfile.subscription_tier` ships with the core build | Added here, with the permission scaffolding |
| §4 — notebook-first prototyping | Build step 1 is `class_files/backtester_portfolio.ipynb` |
| §8.7 — new `backtester/` Django app | Backend app is `backtester/` |
| Cache convention `backtest:{task_id}:v1`, 72h | Followed verbatim |
| S3 `backtest_results/` prefix | Used for durable run output |

**One deliberate deviation.** The platform spec names the frontend page
`src/pages/backtester.js`. This build instead uses the existing `/backtest-portfolio`
page, which is already wired into `ProfileSideNav` and already carries the user's mental
model. No new route is created.

§8.7 **V1 (signal backtesting)** — ranking a universe by a factor and measuring forward
returns — is a *different* feature and is not in scope here. It is substantially already
delivered by `/api/getstockquintiles/` and the `/factor-performance` page.

### Relationship to the master implementation plan — THIS IS THE CANONICAL BACKTESTER

`docs/superpowers/plans/2026-04-20-fintank-master-implementation-plan.md` contains two
older backtester phases. **Neither is implemented** — `backend/backtester/` does not exist
and not one checkbox in that plan is ticked.

**This spec is now the definitive design for the `backtester` app.** Where it disagrees
with the master plan, this spec wins.

| Master plan | Status |
|---|---|
| **Phase 10** — Backtesting V2 (strategy simulation) | **SUPERSEDED.** This spec covers all of it and substantially more. Do not implement Phase 10 |
| **Phase 5** — Backtesting V1 (signal backtesting) | **UNTOUCHED AND OUT OF SCOPE.** A separate future feature, deferred indefinitely. See the hard rules below |

### Phase 5 is out of bounds

Phase 5 (factor/quintile signal backtesting) is a different product from this one. It is
**not** a prerequisite, **not** a dependency, and **must not be built, stubbed, partially
scaffolded, or refactored** as part of this work. The implementing session must not touch
it. Concretely:

| Phase 5 artifact | Rule |
|---|---|
| `BacktestJob` model | **Do not create.** This spec's job model is `BacktestRun` (§11) |
| `backtester/engine/signal.py` | **Do not create.** Not part of this engine |
| `src/pages/backtester.js` | **Do not create.** This feature lives at `/backtest-portfolio` |
| `RunBacktestView`, `BacktestStatusView`, `BacktestResultsView`, `BacktestHistoryView` | **Do not create under these names.** See §12 for this spec's view surface |
| Factor engine (Phase 4) dependency | **None.** This engine reads price parquets only |
| `n_quintiles`, `factor`, `universe` job fields | **Not in this app's models.** Signal-backtest concepts only |

If Phase 5 is ever revived, it must adapt to this app rather than the reverse: its model
gets named `SignalBacktestJob`, its views get `Signal…` prefixes, and it lives at
`/backtester`. Both features can then coexist in `backtester/` without collision. Nothing
in this spec needs to change to accommodate it — the namespace is already clear.

### Two further departures, both deliberate

1. **Phase ordering.** The master plan calls its order "load-bearing": Phase 4 (factor
   engine) → Phase 5 → Phase 10. This spec skips that chain entirely, and correctly so:
   portfolio backtesting depends only on price data that is already staged on S3. There is
   no technical dependency on the factor engine or on signal backtesting.
2. **Saved portfolios.** Phase 10 proposed bolting `strategy_type` / `position_sizing`
   fields onto a job model. That cannot support saved, reusable portfolios. This spec
   introduces `Portfolio` + `PortfolioHolding` entities the master plan never contemplated.
   Do not implement the field-bolting approach.

---

## 1. Scope

### In scope (phase 1)

- Portfolio construction from stocks and ETFs, saved per user
- Six weighting schemes: equal weight, custom, inverse-volatility, global minimum
  variance, risk parity, maximum Sharpe
- Two backtest modes: fixed-weight and walk-forward (rolling re-optimization)
- Staggered asset inception with automatic re-weighting (§5)
- Periodic contributions (dollar-cost averaging)
- Transaction costs and turnover
- Benchmark comparison
- Full performance statistics (§9)
- Seven-sins diagnostics panel (§10)
- Efficient frontier visualization
- Usage metering scaffolding for later monetization (§13)

### Explicitly out of scope (phase 2+, seams left open)

- Multiple randomized backtests (resampled assets × windows, leaderboard, boxplots)
- Hierarchical risk parity, Black–Litterman, strategy-specific eigenvector shrinkage
- Factor attribution against `stock_data/factor_metrics/`
- Preset risk-tiered model portfolios
- Monte Carlo forward projection
- Short selling with borrow-cost modelling (long-only is enforced by default; if a user
  disables it, diagnostics state plainly that borrow costs are unmodelled)
- Live Stripe billing (the meter ships; pricing and checkout do not)

---

## 2. Architecture

```
backend/backtester/
  __init__.py
  models.py            Portfolio, PortfolioHolding, BacktestRun
  serializers.py
  views.py             CRUD + run submission + status/result polling
  urls.py
  tasks.py             Celery task run_portfolio_backtest
  quota.py             metering: check_and_consume
  permissions.py       IsAuthenticated + HasBacktestQuota
  engine/
    __init__.py
    prices.py          price panel loader (S3 -> FMP -> Redis), availability mask
    covariance.py      sample + Ledoit-Wolf shrinkage
    optimizers.py      the six weighting schemes
    backtest.py        the simulation loop
    metrics.py         performance measures
    diagnostics.py     seven-sins reality check
    frontier.py        efficient frontier sampling
    config.py          dataclasses for request/config validation
  tests/
    test_prices.py  test_optimizers.py  test_backtest.py
    test_metrics.py test_diagnostics.py test_views.py test_quota.py
```

**Design rule:** everything under `engine/` is pure functions over numpy/pandas. No Django
imports, no S3 imports, no Redis. `prices.py` is the single exception and is structured so
its I/O sits behind one function that tests monkeypatch. This keeps the numerical core
unit-testable without infrastructure, and keeps each file small enough to reason about.

`backtester/` is a new app rather than an extension of `analyzer/` because `analyzer` is
deliberately model-free ("read-only API views that serve cached market data. No DB models")
and this feature requires user-scoped writes.

---

## 3. Request contract

A backtest request is fully self-contained — it does not require a saved `Portfolio`.
Saving is a separate, free action.

```python
@dataclass
class BacktestRequest:
    holdings: list[Holding]           # symbol + target_weight
    benchmark_symbol: str = "SPY"
    start_date: date | None = None    # None => earliest available
    end_date: date | None = None      # None => latest available
    initial_amount: float = 10_000.0
    periodic_contribution: float = 0.0
    contribution_frequency: str = "none"      # none | monthly | quarterly | annual

    weighting_scheme: str = "equal"   # equal|custom|inverse_vol|min_variance|
                                      # risk_parity|max_sharpe
    backtest_mode: str = "fixed"      # fixed | walk_forward
    rebalance_frequency: str = "annual"  # none|monthly|quarterly|semiannual|annual

    # advanced
    lookback_days: int = 252
    gap_days: int = 1
    covariance_method: str = "ledoit_wolf"    # sample | ledoit_wolf
    transaction_cost_bps: float = 10.0
    long_only: bool = True
    max_weight: float | None = None
    min_weight: float | None = None
    risk_free_rate: float = 0.0
    inception_policy: str = "phase_in"        # phase_in | common_start
    enter_immediately: bool = False
    min_history_days: int | None = None       # None => derived, see §5
```

`Holding.target_weight` is required only when `weighting_scheme == "custom"`; it is
otherwise ignored. Custom weights are normalized to sum to 1 and rejected if any is
negative while `long_only` is true.

---

## 4. Price data layer — `engine/prices.py`

### Loading

```python
def load_price_panel(symbols, start=None, end=None) -> PricePanel
```

Returns a `PricePanel` carrying a dates × symbols DataFrame of `adjClose`, plus per-symbol
`first_valid` / `last_valid` dates and a provenance map (`s3` | `fmp` | `cache`).

Resolution order per symbol:

1. Redis `prices:panel:{SYMBOL}:v1` — gzipped JSON of `[date, adjClose]`, 24h TTL
2. `GetData.load_stock_prices(symbol, columns=['date', 'adjClose'])`
3. On S3 miss (`FileNotFoundError` / `OSError` / `KeyError`): FMP
   `historical-price-full/{symbol}?serietype=line`, cached identically

Symbols are fetched concurrently with a `ThreadPoolExecutor` (these are I/O bound;
concurrency from `BACKTEST_MAX_WORKERS`, default 8).

**Required upstream change:** `GetData.load_stock_prices` currently takes no `columns`
argument. Add one, mirroring the existing `load_index_parquet` signature
(`backend/utils/StockCalculations.py:136`). The price parquets carry 52 columns and this
engine needs two; pushing the projection into `pq.read_table` avoids reading ~26x more
bytes than necessary per symbol.

The change is **additive and backwards compatible**: default `columns=None` reproduces
current behaviour exactly, and the only existing call sites
(`CorePerformanceTools.py:207`, `index_tools.py:160`) pass no columns.

Schema verified against S3 on 2026-08-11 —
`stock_data/stock_prices/daily/AAPL_prices.parquet` and
`index_data/index_prices_v2/daily/sp500_prices.parquet` have identical structure: 52
columns, `date` present as a real named column, `pandas_metadata.index_columns == ['date']`,
no `__index_level_0__`.

> ⚠️ **`'date'` must be included in any `columns` list.** It is the pandas index, so
> omitting it makes `to_pandas()` return a RangeIndex and the subsequent
> `df.reset_index(); df['date']` raises `KeyError`. This is why
> `index_tools._comparison_columns()` lists `'date'` explicitly — follow that pattern.

Benchmarks resolve through `load_index_parquet` when the symbol matches a known index key,
otherwise through the same per-symbol path (so `SPY`, `VTI` etc. work unchanged).

### Alignment

Prices are reindexed onto the union of trading dates across all requested symbols, then
forward-filled **within** each symbol's own `[first_valid, last_valid]` span only. Forward
fill never manufactures a price before a symbol's first trade or after its last — that is
what makes the availability mask in §5 meaningful.

Returns are simple returns on `adjClose`:  `r_t = P_t / P_{t-1} - 1`.

---

## 5. Staggered inception

The default behaviour when assets have different start dates. This is `inception_policy = "phase_in"`.

### The problem with the obvious approach

Intersecting dates across symbols (`panel.dropna()`) means a single asset that listed in
2021 silently truncates a requested 20-year backtest to 4 years, with no explanation. Users
read the resulting CAGR as if it answered the question they asked. It did not.

### The mask

Two boolean matrices over (date × symbol):

```
available[t, i]  =  first_valid[i] <= t <= last_valid[i]
eligible[t, i]   =  available[t, i]  and  (trading days since first_valid[i]) >= min_history_days
```

`min_history_days` defaults to:

| Weighting scheme | Default `min_history_days` |
|---|---|
| `equal`, `custom` | 1 |
| `inverse_vol`, `min_variance`, `risk_parity`, `max_sharpe` | `lookback_days` (252) |

The optimizer defaults are not conservatism for its own sake. An asset with 3 days of
history has no estimable covariance with anything. Requiring a full lookback keeps the
covariance estimated over a **complete rectangular block** of the panel, which guarantees a
positive semi-definite matrix and eliminates an entire class of numerical failure
(ragged/pairwise-complete covariance requires a nearest-PSD projection, which we thereby
avoid entirely).

### Re-weighting

At each rebalance date `t`, let `A(t) = { i : eligible[t, i] }`.

For `equal` and `custom` schemes, targets are renormalized over the available set:

```
w_i(t) = target_w_i / Σ_{j ∈ A(t)} target_w_j        for i ∈ A(t)
w_i(t) = 0                                            otherwise
```

This preserves relative proportions. A 40/30/20/10 portfolio missing its 10% asset becomes
44.4 / 33.3 / 22.2 — not something arbitrary. When the fourth asset becomes eligible it
takes its 10% and the others scale back down proportionally.

For optimizer schemes, the optimizer simply runs on the sub-panel `A(t)`. No renormalization
is needed or applied — the optimizer's output already sums to 1 over the assets it was given.

### Entry timing

An asset that becomes eligible **enters at the next scheduled rebalance on or after its
eligibility date**, not on the eligibility date itself. Entering the day an asset first
prints means an unscheduled whole-portfolio rebalance and a turnover cost no real investor
would pay. `enter_immediately = True` overrides this for users who want it.

Consequence to disclose: with annual rebalancing, an asset eligible in February waits until
the next annual rebalance. The composition timeline (§10) states the actual entry date and
why.

### Exit

An asset whose series ends mid-backtest (`t > last_valid[i]`) is liquidated **on the delist
date** — this is a forced, unscheduled rebalance and does incur transaction cost, because a
real holder would have to trade. Its weight redistributes pro-rata across remaining
holdings. The same mask handles this with no additional machinery.

Note that the staged universe is built from *current* constituent lists, so genuine
delistings are largely absent from the data. This path exists to handle data gaps and
truncated series robustly rather than to correct survivorship bias, which it cannot do.

### Degenerate cases

| Case | Behaviour |
|---|---|
| `A(t)` empty at requested start | Effective start moves to the first date where `\|A(t)\| >= 1`; reported |
| `A(t)` empty mid-backtest | Portfolio holds cash (return 0) for that span; flagged |
| `\|A(t)\| == 1` | Portfolio is 100% that asset. Legal, but triggers a loud diagnostic |
| No asset ever eligible | Hard error: `NoEligibleAssets`, 422 with the per-symbol reason |

### The honesty problem this creates

If four of five assets start in year eight, a "10-year, 5-asset backtest" is really an
8-year single-asset backtest. This must be surfaced prominently, not buried:

- A `composition_coverage` diagnostic (§10) firing when the portfolio held fewer than half
  its assets for more than 25% of the period
- An **effective asset count** series rendered under the allocation chart
- Inception markers annotated on the growth chart
- A composition timeline in the Reality Check panel listing every entry and exit with date
  and cause

### `common_start` alternative

Setting `inception_policy = "common_start"` restores intersection behaviour: the backtest
begins only when every asset is eligible. This is the right choice for a user comparing
several candidate portfolios who needs a clean apples-to-apples window. It is not the
default, because phase-in is what someone means when they ask for ten years.

---

## 6. Covariance — `engine/covariance.py`

```python
def estimate_covariance(returns: np.ndarray, method: str) -> np.ndarray
```

`returns` is a T × N block, already restricted to eligible assets and complete.

**`sample`** — `np.cov(returns, rowvar=False, ddof=1)`.

**`ledoit_wolf`** — the Ledoit–Wolf (2004) well-conditioned estimator, shrinking toward a
scaled identity. Implemented directly (~30 lines); adding scikit-learn as a dependency for
this alone is not warranted.

Given demeaned `X` (T × N) and `S = XᵀX / T`:

```
m   = trace(S) / N
d²  = ‖S − m·I‖²_F / N
b̄²  = (1/T²) · Σ_t ‖x_t x_tᵀ − S‖²_F / N
b²  = min(b̄², d²)
a²  = d² − b²
Σ̂   = (b²/d²)·m·I + (a²/d²)·S
```

`ledoit_wolf` is the default. With 252 daily observations and 10–30 assets the sample
covariance is poorly conditioned, and min-variance and max-Sharpe both invert it — this is
precisely the regime where shrinkage matters most, and it is a documented driver of the
"optimizers underperform 1/N" result.

The strategy-specific eigenvector shrinkage of Goldberg, Gurdogan & Kercheval (2025) is a
natural phase-2 extension and plugs in behind this same function signature.

---

## 7. Optimizers — `engine/optimizers.py`

### The contract

Every scheme is one function with one signature, borrowed from the `portfolioBacktest`
package's design (a function that takes a window of data and returns weights):

```python
def optimizer(returns: np.ndarray, config: OptimizerConfig) -> np.ndarray
```

`returns` is T × N (eligible assets only); the return is a length-N weight vector summing
to 1. The backtest loop never learns which optimizer it called. This is what makes
walk-forward nearly free and lets phase-2 optimizers drop in without touching the loop.

Registry: `OPTIMIZERS: dict[str, Callable]`, so adding a scheme is one entry.

### The six schemes

| Scheme | Formulation | Solver |
|---|---|---|
| `equal` | `w = 1/N` | closed form |
| `custom` | user weights, normalized over eligible set | closed form |
| `inverse_vol` | `w = σ⁻¹ / 1ᵀσ⁻¹`, `σ = √diag(Σ)` | closed form |
| `min_variance` | `min wᵀΣw  s.t. 1ᵀw = 1, w ≥ 0` | SLSQP; closed form `Σ⁻¹1 / 1ᵀΣ⁻¹1` only when unconstrained |
| `risk_parity` | `min Σᵢ (RCᵢ − 1/N)²`, `RCᵢ = wᵢ(Σw)ᵢ / √(wᵀΣw)` | SLSQP |
| `max_sharpe` | `max (wᵀμ − r_f) / √(wᵀΣw)  s.t. 1ᵀw = 1, w ≥ 0` | SLSQP |

All six are reachable with `scipy.optimize`, which is already a backend dependency. **No
cvxpy or riskfolio-lib is required** — avoid adding them.

Constraints applied uniformly: `long_only` (bounds `w ≥ 0`, default on), `max_weight`,
`min_weight`. Bounds are validated for feasibility first — `max_weight × N < 1` is
rejected at request validation with a clear message rather than producing a silent
solver failure.

Solver hygiene:
- Warm-start from equal weight
- On non-convergence, fall back to inverse-volatility and record a
  `optimizer_fallback` diagnostic naming the rebalance date. A backtest must never
  silently substitute a different strategy.
- `max_sharpe` uses the sample mean of the lookback window for `μ`. This is a
  deliberately noisy estimate; diagnostics say so (§10, `return_estimation`).

### Efficient frontier — `engine/frontier.py`

For the frontier chart: sample ~2,000 random long-only weight vectors (Dirichlet) over the
full-period covariance, plus the analytic frontier traced by solving min-variance subject
to a target-return constraint across a grid. Returns scatter points, the frontier curve,
the GMVP point, the tangency point, and the user's own portfolio marked on the same axes.

This is computed on the **full-period, in-sample** covariance and is explicitly labelled as
illustrative in the UI — it is not a walk-forward result and must not be presented as one.

---

## 8. Backtest engine — `engine/backtest.py`

### The timing contract

This is the single most important thing to get right, and the one most commonly got wrong
(Palomar ch. 8, "Sin #2: Look-Ahead Bias"):

> Weights decided for date `t` may use data only through `t − 1 − gap_days`.
> The portfolio return realized at `t` is `R_t = w_{t−1}ᵀ · r_t`.

Multiplying `w_t` by `r_t` is the classic time-alignment error and produces spectacular,
fictional results. §15 specifies a regression test that fails if this contract is ever
broken.

### Loop

```
for each trading day t in [effective_start, end]:
    1. R_t = w_{t-1}ᵀ r_t                      # realize yesterday's weights against today's returns
    2. w_drift_i = w_{i,t-1} (1 + r_{i,t}) / (1 + R_t)     # weights move with prices
    3. update the TWR index:  I_t = I_{t-1} · (1 + R_t)
    4. update NAV:            NAV_t = NAV_{t-1} · (1 + R_t)
    5. if t is a contribution date:
         NAV_t += C_t                          # invested pro-rata at w_drift, so weights unchanged
         NAV_t -= C_t × transaction_cost_bps / 10_000
    6. if t is a rebalance date OR a forced event (delisting):
         a. A(t) = eligible set
         b. w_target = scheme(returns[t-gap-lookback : t-gap, A(t)], config)
         c. turnover  = Σ_i |w_target_i − w_drift_i|
         d. cost      = turnover × transaction_cost_bps / 10_000
         e. NAV_t    *= (1 - cost);  I_t *= (1 - cost)
         f. w_t = w_target
       else:
         w_t = w_drift
```

Step order matters: `R_t` must be computed **before** drift, because the drift denominator
is `1 + R_t`. Computing drift first and then taking `w_driftᵀ r_t` is a look-ahead error.

**Drift** between rebalances: `w_i,t = w_i,t−1 (1 + r_i,t) / (1 + R_t)`.

**Contributions** are deployed pro-rata at the current drifted weights, so they change NAV
but not composition and incur no rebalancing turnover. They do incur a one-way trading cost
on the contributed notional (step 5), because the cash has to be put to work. That cost hits
`nav` only — never `index`, which must stay free of anything driven by the deposit schedule.

**Turnover** is the L1 norm `‖w_reb − w_drift‖₁`, matching the research. Note this equals
total notional traded as a fraction of NAV: selling 5% of A and buying 5% of B gives
`Σ|Δw| = 0.10`, and the notional traded is indeed `0.10 × NAV`.

**Fixed vs walk-forward.** In `fixed` mode, step 6b runs once at `effective_start` using
the first lookback window, and thereafter reuses those targets (renormalized over `A(t)`).
In `walk_forward` mode it re-runs at every rebalance on the trailing window.

### Two series, not one

The engine maintains **two** wealth series, and conflating them is the second-easiest way
to produce wrong numbers:

| Series | Definition | Used for |
|---|---|---|
| `nav` | actual account balance, includes contributions | the headline "$10,000 became $31,400" |
| `index` | time-weighted growth of $1, contribution-free | **every** risk and return statistic |

With periodic contributions, computing CAGR from `nav` conflates investment skill with
deposit schedule, and computing drawdown from `nav` lets a well-timed contribution paper
over a real drawdown. So:

- CAGR, volatility, Sharpe, Sortino, drawdown, CVaR, beta — all from `index` (time-weighted)
- Ending balance, total contributed, total gain — from `nav`
- Additionally report **money-weighted return (IRR)** over the actual cash-flow schedule,
  labelled "your personal return", so the user gets both readings and knows they differ

The per-period return that feeds `index` is contribution-adjusted:

```
R_t = (NAV_t − NAV_{t−1} − C_t) / NAV_{t−1}
```

### Outputs

```
BacktestResult:
  dates, nav, index, drawdown, returns
  weights_over_time        (dates × symbols)
  effective_asset_count    (per date)
  rebalance_events         [{date, turnover, cost, weights, trigger}]
  composition_events       [{date, symbol, action: entered|exited, reason}]
  benchmark_index, benchmark_drawdown
  metrics                  (§9)
  benchmark_metrics
  diagnostics              (§10)
  frontier                 (§7)
  effective_start, effective_end, truncation_cause
```

---

## 9. Metrics — `engine/metrics.py`

All computed from the `index` (time-weighted) series unless noted. Annualization uses 252
trading days.

| Metric | Definition |
|---|---|
| CAGR | `(I_T / I_0)^(252/T) − 1` |
| Annualized return (arithmetic) | `252 · mean(R_t)` |
| Annualized volatility | `√252 · std(R_t, ddof=1)` |
| Sharpe | `(mean(R_t) − r_f/252) / std(R_t) · √252` |
| Sortino | excess mean / downside deviation (MAR = `r_f`), × `√252` |
| Max drawdown | `min(I_t / cummax(I_t) − 1)`, with peak, trough and recovery dates |
| Calmar | `CAGR / \|MaxDD\|` |
| VaR(95), CVaR(95) | 5th percentile of `R_t`; mean of the tail below it |
| Best / worst year | calendar-year returns off `index` |
| Beta, alpha | OLS of portfolio excess returns on benchmark excess returns |
| Up / down capture | mean portfolio return in up/down benchmark periods ÷ benchmark's |
| Annual turnover | `Σ turnover / years` |
| Total costs paid | cumulative cost drag, in dollars and as annualized bps |
| Correlation matrix | pairwise across holdings, full period |
| Contribution to return | `w̄_i · r̄_i` per asset, normalized |
| Contribution to risk | `w_i(Σw)_i / (wᵀΣw)` per asset |
| Ending balance, total contributed, total gain | from `nav` |
| Money-weighted return (IRR) | Newton solve over the dated cash-flow vector |

**Reuse note:** contribution-to-risk is the same computation as
`create_index_contr_to_var()` in `stock_data_getter_v2.ipynb`, which produces
`index_data/contr_to_var/`. The formula should be shared, not reimplemented — extract it
into `engine/metrics.py` and have the notebook path reference the same definition.

---

## 10. Diagnostics — `engine/diagnostics.py`

The feature that distinguishes this from a toy backtester. Returns an ordered list of
structured findings, each `{code, severity: info|warning|critical, title, detail}` in plain
language, no jargon without a gloss. Mapped onto the seven sins of quantitative investing
(Luo et al. 2014, via Palomar ch. 8).

| Code | Sin | Fires when |
|---|---|---|
| `survivorship_bias` | #1 | **Always.** The universe is built from *current* index constituents; companies that went bankrupt or were delisted are absent, so results are optimistic by construction |
| `history_truncation` | — | Effective start later than requested. Names the constraining asset and its first price date |
| `composition_coverage` | — | Portfolio held < half its assets for > 25% of the period. States the share of the period and which assets dominated it |
| `single_asset_period` | — | `effective_asset_count == 1` for any span > 30 trading days |
| `in_sample_fit` | #4 | `backtest_mode == "fixed"` with an optimizer scheme — weights were chosen on the same data they are scored against. Recommends walk-forward |
| `return_estimation` | #4 | `max_sharpe` selected; expected returns are estimated from a noisy sample mean |
| `short_sample` | #4 | Period < 3 years, or fewer than 60 rebalance observations |
| `cost_sensitivity` | #5 | Turnover × fees consumed > 15% of gross return |
| `outlier_dependence` | #6 | Removing the 5 best days cuts CAGR by > 50% |
| `concentration` | — | Any weight > 40%, or effective N (`1/Σwᵢ²`) < 3 |
| `shorting_unmodelled` | #7 | `long_only == False`; borrow costs and locate availability are not simulated |
| `optimizer_fallback` | — | The solver failed to converge at one or more rebalances; lists dates |
| `benchmark_mismatch` | — | Benchmark's asset class differs materially from the portfolio (e.g. an all-bond portfolio against SPY) |

Storytelling bias (#3) is not machine-detectable and is addressed in static UI copy
accompanying the panel.

Severity drives presentation: `critical` findings render above the results, not below them.

---

## 11. Models — `backtester/models.py`

```python
class Portfolio(models.Model):
    user                 = FK(settings.AUTH_USER_MODEL, related_name="portfolios", on_delete=CASCADE)
    name                 = CharField(max_length=120)
    description          = TextField(blank=True, default="")
    benchmark_symbol     = CharField(max_length=20, default="SPY")
    initial_amount       = DecimalField(max_digits=14, decimal_places=2, default=10000)
    periodic_contribution= DecimalField(max_digits=14, decimal_places=2, default=0)
    contribution_frequency = CharField(max_length=20, default="none")
    weighting_scheme     = CharField(max_length=30, default="equal")
    backtest_mode        = CharField(max_length=20, default="fixed")
    rebalance_frequency  = CharField(max_length=20, default="annual")
    start_date           = DateField(null=True, blank=True)
    end_date             = DateField(null=True, blank=True)
    settings             = JSONField(default=dict)   # advanced block, see §3
    created_at / updated_at

    class Meta:
        unique_together = ("user", "name")
        indexes = [Index(fields=["user", "-updated_at"])]


class PortfolioHolding(models.Model):
    portfolio     = FK(Portfolio, related_name="holdings", on_delete=CASCADE)
    symbol        = CharField(max_length=20)
    target_weight = DecimalField(max_digits=7, decimal_places=6, default=0)
    order         = PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ("portfolio", "symbol")
        ordering = ["order"]


class BacktestRun(models.Model):
    user         = FK(settings.AUTH_USER_MODEL, related_name="backtest_runs", on_delete=CASCADE)
    portfolio    = FK(Portfolio, null=True, blank=True, on_delete=SET_NULL)
    task_id      = CharField(max_length=64, db_index=True)
    request_hash = CharField(max_length=64, db_index=True)
    request      = JSONField()
    status       = CharField(max_length=20, default="queued")  # queued|running|complete|failed
    summary      = JSONField(null=True, blank=True)   # headline metrics only
    result_key   = CharField(max_length=300, blank=True, default="")  # S3 key
    error        = TextField(blank=True, default="")
    counted_against_quota = BooleanField(default=True)
    created_at / completed_at

    class Meta:
        indexes = [Index(fields=["user", "-created_at"]),
                   Index(fields=["user", "request_hash"])]
```

`BacktestRun` does triple duty: quota counter, run history for a future comparison view,
and usage analytics. Full result JSON goes to S3 (`backtest_results/{user_id}/{task_id}.json`)
and Redis (`backtest:{task_id}:v1`, 72h) — not into Postgres.

### `UserProfile` change

Add, per platform spec §3:

```python
subscription_tier      = CharField(max_length=20, default="free", db_index=True)  # free | pro
backtest_quota_override = PositiveIntegerField(null=True, blank=True)
```

`backtest_quota_override` allows comping an individual account without a code change.

Both fields carry defaults, so the migration is additive and needs no backfill. `users/`
currently has only `0001_initial`, so this lands cleanly as `0002`.

> 🔒 **REQUIRED — privilege escalation guard.** `UserProfileSerializer`
> (`backend/users/serializers.py:58`) declares `fields = "__all__"`, and
> `users/views.py:150` feeds user-supplied `request.data` straight into it for a partial
> update of the caller's own profile. Adding these two fields therefore makes them
> **user-writable by default** — any authenticated user could `PATCH
> {"subscription_tier": "pro"}` and grant themselves unlimited backtests, silently
> defeating the entire meter.
>
> Both fields **must** be marked read-only in that serializer:
>
> ```python
> extra_kwargs = {
>     "stripe_account_id": {"write_only": True},
>     "subscription_tier": {"read_only": True},
>     "backtest_quota_override": {"read_only": True},
> }
> ```
>
> Read-only rather than excluded: the frontend needs to *display* tier and remaining runs
> (§14 `QuotaBanner`), it just must never *set* them. Tier changes come only from the admin
> or, later, a Stripe webhook.
>
> A view test asserting `PATCH {"subscription_tier": "pro"}` leaves the tier at `free` is
> mandatory (§15).

---

## 12. API — `backtester/urls.py`

Mounted at `/api/backtester/`. Every route requires `IsAuthenticated`.

| Method | Path | Purpose |
|---|---|---|
| GET, POST | `/portfolios/` | list mine / create |
| GET, PATCH, DELETE | `/portfolios/<id>/` | retrieve / update / delete |
| POST | `/portfolios/<id>/duplicate/` | copy |
| POST | `/run/` | submit a backtest → `{task_id, status: "queued"}` |
| GET | `/status/<task_id>/` | `{status, progress}` |
| GET | `/results/<task_id>/` | full result JSON |
| GET | `/history/` | past runs (paginated summaries) |
| GET | `/search-symbols/?q=` | typeahead over the staged universe |
| GET | `/quota/` | `{used, limit, tier, remaining}` |

Querysets are filtered by `request.user` at the manager level, never by a URL parameter.
`/results/` and `/status/` verify `BacktestRun.user == request.user` before returning.

**Symbol search** builds a Redis-cached index from the constituent JSONs plus the ETF list,
joined to `long_profiles` for company names — following the existing pattern in
`analyzer/analyzer_utils/universe_lookup.py:build_symbol_universe_index`. Cache key
`backtest:symbol_index:v1`, 24h.

### Execution flow

Per platform spec §2, backtests never run in the request thread.

```
POST /run/
  ├── validate request (422 on bad input)
  ├── compute request_hash = sha256(canonical_json(normalized_request))
  ├── if a complete BacktestRun exists for (user, request_hash):
  │       return its task_id immediately, quota NOT consumed
  ├── quota.check_and_consume(user)   -> 402 if exhausted
  ├── create BacktestRun(status="queued")
  └── enqueue run_portfolio_backtest.delay(run_id) -> {task_id, status}
```

`tasks.py::run_portfolio_backtest` loads prices, runs the engine, writes JSON to S3 and
Redis, and updates the `BacktestRun` row. Progress is reported coarsely
(`loading_prices` → `optimizing` → `simulating` → `computing_metrics`) for the polling UI.

Frontend polls `/status/` at 1s intervals with backoff to 3s, then fetches `/results/`.

---

## 13. Metering — `backtester/quota.py`

Scaffolding ships now; pricing is deliberately undefined.

```python
FREE_TIER_BACKTEST_LIMIT = 10   # settings-overridable

def get_quota(user) -> Quota          # {used, limit, tier, remaining}
def check_and_consume(user) -> None   # raises QuotaExceeded (-> HTTP 402)
```

`used` is `BacktestRun.objects.filter(user=user, counted_against_quota=True).count()`.
Limit resolution: `backtest_quota_override` if set, else unlimited for `pro`, else
`FREE_TIER_BACKTEST_LIMIT`.

Three rules that matter more than the number:

1. **Only novel runs count.** An identical `request_hash` serves from cache and is free.
   Without this, toggling a chart option burns a credit and the tool feels hostile.
2. **Saving, loading, editing and duplicating portfolios are always free.** Only execution meters.
3. **Failed runs are refunded.** If the task ends `failed`, set
   `counted_against_quota = False`. Users do not pay for our bugs.

`QuotaExceeded` renders as **402 Payment Required** with
`{detail, used, limit, upgrade_required: true}`.

`UserProfile` already carries `stripe_account_id`, and `STRIPE_SECRET_KEY` is already
configured, so the later billing hook-up is additive — a webhook that flips
`subscription_tier` — rather than a refactor.

---

## 14. Frontend

Replaces the `ComingSoon` body of `src/pages/backtest-portfolio.js`. Pages Router, inside
`ProfileLayout`, Bootstrap + ApexCharts to match surrounding legacy components. `.js`, not
`.tsx` — this page belongs to the legacy tree. Remove `built: false` from the
`/backtest-portfolio` entry in `ProfileSideNav.js` when it ships.

### UX model: progressive disclosure

One page. Defaults good enough that a novice can press Run within 30 seconds. An
**Advanced settings** disclosure holds optimizer choice, covariance method, constraints,
costs, lookback, gap and inception policy. Results lead with a plain-language headline; the
quant table sits below a second disclosure.

```
BUILD YOUR PORTFOLIO
  [+ Add ticker…]   [AAPL ×] [VTI ×] [BND ×]
  Weighting  ( ) Equal  (•) Custom  ( ) Optimize
  Period [10 years ▾]   Rebalance [Annual ▾]
  Invest [$10,000]  + [$500]/month
  ▸ Advanced settings
  [ Run backtest ]          7 of 10 free backtests remaining
        ↓
$10,000 became $31,400  ·  beat SPY by 2.1%/yr
Worst drop: −34% (Feb–Mar 2020), recovered in 5 months.
⚠ For 62% of this period the portfolio held 2 of your 5 assets.
[growth chart vs benchmark, inception markers]
▸ Full statistics
```

### Components — `src/componentsLegacy/Backtest/`

| Component | Responsibility |
|---|---|
| `PortfolioBuilder.js` | typeahead, holding chips, weight inputs, allocation donut |
| `BacktestSettings.js` | period, rebalance, amounts, contributions |
| `AdvancedSettings.js` | the disclosure: optimizer, covariance, constraints, costs, inception policy |
| `ResultsHeadline.js` | the plain-language answer |
| `GrowthChart.js` | NAV vs benchmark, log-scale toggle, inception annotations |
| `DrawdownChart.js` | underwater plot |
| `AllocationOverTime.js` | stacked area of weights + effective asset count line |
| `StatsTable.js` | full metrics, portfolio vs benchmark columns |
| `RealityCheck.js` | diagnostics panel + composition timeline |
| `EfficientFrontier.js` | scatter + frontier + user's point |
| `SavedPortfolios.js` | list, load, duplicate, delete |
| `QuotaBanner.js` | remaining runs; upgrade prompt on 402 |

### Hooks — `src/hooks/`

`usePortfolios.js` (CRUD), `useBacktestRun.js` (submit + poll + result),
`useSymbolSearch.js` (debounced typeahead), `useBacktestQuota.js`.

Follow existing conventions: `NEXT_PUBLIC_FINTANK_API_URL`, JWT from the existing auth
flow.

The `AllocationOverTime` stacked area is where staggered inception becomes legible — it is
the most informative view on the page and should not be buried behind a disclosure.

---

## 15. Testing

`engine/` is pure, so it tests without Django, S3 or Redis.

**Golden numerical tests** — a 3-asset synthetic panel with hand-computed expected values:
- 1/N NAV, CAGR, volatility, Sharpe, max drawdown
- Drawdown peak/trough/recovery dates
- Turnover and cost arithmetic across a known rebalance

**Property tests:**
- All optimizers return weights summing to 1 within 1e-9, non-negative under `long_only`
- Risk parity: risk contributions equal within 1e-4
- Min variance: portfolio variance ≤ that of equal weight on the same covariance
- Ledoit–Wolf output is symmetric PSD with condition number ≤ the sample covariance's

**Look-ahead regression test (required).** Construct a panel where one asset's future
return is knowable. Assert that a strategy which would profit from `w_t · r_t` alignment
produces no such profit under the engine. This test is the guardrail on the §8 timing
contract and must fail loudly if the loop is ever reordered.

**Staggered inception tests:**
- Asset entering mid-period gets exactly its target weight at the first rebalance on/after
  eligibility
- Weights sum to 1 on every date, including the phase-in span
- `min_history_days` correctly delays optimizer eligibility beyond price availability
- `common_start` reproduces plain intersection behaviour
- Delisting mid-period liquidates and redistributes pro-rata
- `effective_asset_count` matches the composition event log

**Contribution tests:**
- With contributions, `index`-derived CAGR is unaffected by the deposit schedule
- Drawdown computed from `index` is not masked by a well-timed contribution
- IRR matches a known XIRR case

**View tests** (mocked price loader, matching `analyzer/tests.py` conventions): auth
required on every route; users cannot read another user's run; 402 on exhausted quota;
repeat `request_hash` does not consume quota; failed run refunds.

**Privilege escalation test (required).** `PATCH /api/profile/` with
`{"subscription_tier": "pro"}` must leave the caller's tier at `free`. Same for
`backtest_quota_override`. See the guard in §11 — without it, `UserProfileSerializer`'s
`fields = "__all__"` makes the meter trivially bypassable.

---

## 16. Build sequence

Per platform spec §4, numerical logic is validated in a notebook before it becomes Django code.

1. **`backend/class_files/backtester_portfolio.ipynb`** — prototype and validate against
   real S3 data: price panel + availability mask, the six optimizers, the backtest loop,
   metrics. Confirm numbers against a known reference (e.g. a 60/40 SPY/AGG backtest) before
   porting. *Do not run the existing notebooks in `class_files/` — several have live-fetch
   cells.*
2. `GetData.load_stock_prices(columns=…)` projection support
3. `engine/prices.py` + tests
4. `engine/covariance.py`, `engine/optimizers.py` + tests
5. `engine/backtest.py` + tests, **including the look-ahead regression test**
6. `engine/metrics.py`, `engine/diagnostics.py`, `engine/frontier.py` + tests
7. Models + migrations (`backtester`, plus the `UserProfile` fields) — **and in the same
   step, apply the `UserProfileSerializer` read-only guard from §11.** The fields and the
   guard must land together; a commit that adds `subscription_tier` without it ships a
   user-writable subscription tier
8. `tasks.py`, `quota.py`, `views.py`, `urls.py`, `serializers.py` + view tests
9. Frontend: hooks → builder → results → reality check → saved portfolios
10. Remove `built: false` from `ProfileSideNav.js`
11. Rotate the FMP key in `portfolio_analyzer.ipynb` and delete that notebook

Steps 3–6 are independently testable and are the bulk of the risk. Do not start step 9
until step 8's endpoints return real result JSON.

### Scope guardrails

The implementing session builds **only** what §2's file tree lists. Specifically, it must
**not**:

- create `BacktestJob`, `engine/signal.py`, or `src/pages/backtester.js` (Phase 5 artifacts
  — see "Phase 5 is out of bounds" above)
- add any factor-engine, quintile, or signal-ranking capability to this app
- modify `/factor-performance`, `/api/getstockquintiles/`, or `analyzer_utils/factor_tools.py`
- touch `docs/superpowers/plans/2026-04-20-fintank-master-implementation-plan.md` beyond the
  Phase 5 / Phase 10 status annotations already applied

### Files modified outside `backend/backtester/` and `src/`

This is the **complete and authoritative allowlist**. Anything not on this list is out of
scope. The backend entries are all additive — no existing endpoint, task or query changes
behaviour. The two frontend entries replace a `ComingSoon` placeholder, which is the point
of the feature, not a regression.

| File | Change | Why |
|---|---|---|
| `backend/utils/StockCalculations.py` | add optional `columns=` to `load_stock_prices` | §4, column projection |
| `backend/users/models.py` | add `subscription_tier`, `backtest_quota_override` | §11 |
| `backend/users/migrations/0002_*.py` | new migration (both fields defaulted, no backfill) | §11 |
| `backend/users/serializers.py` | mark both new fields `read_only` in `UserProfileSerializer.extra_kwargs` | §11 — **security-critical, not optional** |
| `backend/fintank_backend/settings.py` | add `backtester.apps.BacktesterConfig` to `INSTALLED_APPS`; add `BACKTEST_MAX_WORKERS` (default 8) | app registration |
| `backend/fintank_backend/urls.py` | one `path("api/", include("backtester.urls"))` | routing |
| `src/pages/backtest-portfolio.js` | replace the `ComingSoon` body with the real UI | §14 |
| `src/componentsLegacy/Profile/ProfileSideNav.js` | remove `built: false` from the `/backtest-portfolio` entry | §14 |

Two notes on that list:

- **Do not delete `ComingSoon.js`.** `create-alerts.js` and `watchlist.js` still render it.
- **Route prefix.** Every app mounts at `path("api/", include(...))`, so `backtester/urls.py`
  must carry the `backtester/` segment on each of its own routes to produce
  `/api/backtester/…` as specified in §12.

No new Python or npm dependencies are required — scipy, numpy, pandas, pyarrow, s3fs,
celery and redis are already in `backend/pyproject.toml`; ApexCharts is already in
`package.json`. Celery's `autodiscover_tasks()` picks up the new `tasks.py` with no config
change.

---

## 17. Open items

- **Runtime budget.** 120 monthly rebalances × ~50ms per risk-parity SLSQP solve is ~6s;
  weekly rebalancing over 20 years would be ~25s. Acceptable under Celery. If p95 exceeds
  60s, cache per-rebalance covariance across runs sharing a lookback window before
  reaching for anything more elaborate.
- **`BACKTEST_MAX_WORKERS`** is named in the platform spec §config table but does not yet
  exist in settings; add it (default 8).
- **Benchmark for non-US portfolios** — `SPY` is a poor default for a TSX or EAFE basket.
  Phase 1 ships the `benchmark_mismatch` diagnostic; auto-suggesting a benchmark from
  holdings' listing exchange is a phase-2 nicety.
- **Rate limiting** on `/run/` beyond the quota (a Pro user could still queue hundreds of
  jobs). A per-user concurrent-job cap of 3 is probably right; not specced here.
