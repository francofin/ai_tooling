# Index return attribution: design

Date: 2026-11-07. Status: implemented and deployed 2026-11-08 (`ed5daf4`); first AWS build Sat 2026-11-14. Current state: `docs/RECENT_CHANGES.md`.

## Goal

For each index page, show how much each constituent and each sector contributed
to the index's return over **1W, 2W, 1M, 3M, YTD and 1Y**. Compute it in the
weekly AWS pipeline (lean and full runs), publish it to `thetradingfloor` through
the existing checked/held/published flow, and have Django read the parquet
instead of computing on request.

## Decisions (owner, 2026-11-07)

1. **Price return**, not total return. Reconciles with `index_prices_v2` and the
   proxy ETF's price.
2. **IEFA and WSML ship as local-currency attribution**, labelled as such. No FX
   series in the pipeline for v1.
3. **v1 scope:** sector table, top/bottom 10 constituents, breadth,
   concentration, cap-weighted minus equal-weighted gap. Brinson panel deferred.
4. **Computed inside the pipeline** as a build stage that runs on every run, not
   on the owner's machine.

## Why the current code is replaced

`get_index_sector_contribution` (`backend/analyzer/analyzer_utils/index_tools.py:677`)
computes on request from today's ETF weights × the factor_metrics window
returns, for `ytd` and `1M` only. Problems:

| # | Problem | Where |
|---|---|---|
| 1 | End-of-period weights over the whole window. Overstates the index return by Var_w0(r)/(1+R); about 9pp over 1Y at 30% dispersion. Winners look bigger than they were. | `index_tools.py:609-614` |
| 2 | Weights and returns are about 4 weeks apart (holdings `updated` vs factor_metrics `as_of`). | docstring `index_tools.py:567-569` |
| 3 | Null sector: `groupby('sector')` drops NaN keys but `index_return_pp` sums every row, so sectors don't add up to the total. | `index_tools.py:617, 633` |
| 4 | Each window renormalises over priced names, so the total is the subset's return; nothing reconciles it with the index. | `index_tools.py:609-613` |
| 5 | Each symbol uses its own last print (up to 5 business days of skew). | `factor_windows.py:44`, `stock_pipeline.py:1555` |
| 6 | Exact-string ticker join, no normalisation; unmatched weight is reported but never fails. | `index_tools.py:659` |
| 7 | A missing parquet surfaces as 500, not 404. | `views.py:457-461` |

## Method

### Notation

- `t_s`: holdings snapshot date (the constituents JSON `updated` field).
- `t_0`: window start (anchor). `T`: window end (common end date).
- `P_i(t)`: split-adjusted `close` (verified: NVDA reads ~121 on both sides of
  the June 2024 10:1 split). `adjClose` is **not** used; it includes dividends.

### Buy-and-hold contribution, single period

```
w0_i = w_s,i · P_i(t_0)/P_i(t_s)  /  Σ_j w_s,j · P_j(t_0)/P_j(t_s)     # drift snapshot weight to t_0
r_i  = P_i(T)/P_i(t_0) − 1
c_i  = w0_i · r_i                                                     # in pp when ×100
R_bh = Σ c_i
```

One formula covers `t_s` before, at or after `t_0`/`T`. When `t_s = T` it
reduces to `1 + R = 1/Σ w_T/(1+r)` and `c_i = (1+R)·w_T,i·r_i/(1+r_i)`, which is
the test oracle. No daily linking: with one snapshot, daily weights would come
from the same drift, so linking adds nothing.

Known approximations, stated in the payload docs, not fixed in v1: rebalances
and reconstitutions inside the window (Russell June, S&P/Nasdaq quarterly),
names deleted during the window (absent from the snapshot), names added during
the window (credited with pre-inclusion return unless they lack a start price).

### Windows

Calendar offsets, start resolved to the last trading day at or before the
calendar date (same semantics as `factor_windows._anchor_date` + `Series.asof`):

| Label | Calendar start |
|---|---|
| `1W` | T − 7 days |
| `2W` | T − 14 days |
| `1M` | T − 1 month |
| `3M` | T − 3 months |
| `ytd` | Dec 31 of the prior year (prior year-end close) |
| `1Y` | T − 1 year |

**One grid per universe:** `T` = the latest date on which at least 50% of the
universe has a print (the rule `compute_contr_to_vol` already uses,
`stock_pipeline.py:1774`). Each name's price at `t_0`, `t_s` and `T` is its
`asof` on that grid, forward-filled at most 5 sessions; older than that is
"stale" and goes to unattributed.

`ATTRIBUTION_WINDOWS` is a **new constant** in `pipelines/factor_windows.py`.
`WINDOWS` is not touched: it drives `FACTOR_NUMERIC_COLS`,
`FACTOR_METRICS_COLUMNS` and `REQUIRED_COLUMNS["factor_metrics"]`
(`stock_pipeline.py:123-133`, `checks.py:24`), so new keys there would change the
factor schema. `_anchor_date` is generalised to take an offset so both share one
anchor rule.

### Buckets that are not silently dropped

Every unit of declared snapshot weight ends up in exactly one row:

| Level | Meaning |
|---|---|
| `constituent` | priced at `t_s`, `t_0` and `T` |
| `joined` | no price at `t_0` (first print more than 3 sessions after the anchor): IPO, spin-off, new add. End weight and return-since-first-trade shown, **no contribution** |
| `unattributed` | no price file, stale price, or ticker that didn't match |
| `non_equity` | cash, currency, futures, FX-forward and money-market lines (blocklist regex + no price file) |

Identity checked on every window: `Σ sector contributions = index contribution`,
and `constituent + joined + unattributed + non_equity` weights = 100% of declared.

### Reported per window

Index row: `R_bh`, reference return and residual (below), covered weight %,
breadth (count up, % up, % beating the index, median return), effective N
(`1/Σ w0²`), names needed for 50% of the return, top-10 contribution in pp,
equal-weight return and cap − EW gap. Percent-of-return figures are suppressed
when |R| < 50bp.

Sector rows: start weight, end weight, cap-weighted sector return
(`Σc/Σw0`), contribution, count. Null sector → `"Unclassified"`.

Constituent rows: all priced names (r2000 ≈ 2,000 × 6 windows ≈ 12k rows).
Django picks the top and bottom 10.

### Reconciliation

Reference = the **proxy ETF's price return** (`close`) from
`stock_data/stock_prices/daily/etfs/{ETF}_prices.parquet`
(`cfg.CONSTITUENT_PROXY_ETFS`), same universe, same price basis. Not the page's
index: the NASDAQ page's index is the Composite (`nas_comp`) while its weights
are QQQ (Nasdaq-100).

Warn thresholds on |R_bh − R_etf|:

| Window | sp500, nas, r2000 | tsx, tsx_small_cap, rmicro |
|---|---|---|
| 1W / 2W | 25bp | 40bp |
| 1M | 40bp | 60bp |
| 3M | 75bp | 100bp |
| YTD / 1Y | 150bp | 250bp |

msci_eafe and msci_sm are local-currency vs a USD ETF, so their residual carries
the FX move: reported, **not** checked (INFO).

**Migrating lists, YTD and 1Y:** for r2000, rmicro, tsx_small_cap (and msci_sm)
the snapshot no longer holds members that graduated to a bigger index at
reconstitution, often the year's biggest winners, so the attributed return
falls short of the ETF. Local smoke run 2026-11-07, 1Y residual: r2000 −6.8pp,
rmicro −16.8pp, tsx_small_cap −5.0pp, vs under 0.8pp for sp500/nas/tsx. Those
windows are reported, not checked, and the index page labels them approximate,
until history-linked attribution replaces them. Residual is warn-only for all
universes until three runs show the normal range; then tune.

## Holdings history (ships first, Phase 0)

Each run saves the holdings it fetched, so later versions can use real
historical weights (segment drift between snapshots, Carino-linked: 3M after
~13 weekly snapshots, YTD/1Y after a year). History can't be recovered later, so
this goes out before the attribution stage.

- `refresh_constituents` writes
  `index_data/constituents_history/{sub}/{YYYY-MM-DD}.json`, where the date is the
  holdings `updated` date. If that date's file already exists, nothing is
  written (stale holdings don't create duplicates).
- Local copy lives in the `index_data` state unit (`state.py:21`), so it's pulled
  and pushed with the rest of `index_data` automatically.
- **Also published** to the live bucket as dataset `constituents_history` at
  the same key. Reason: the state bucket expires noncurrent versions after 14
  days (`pipeline_stack.py:71`), so one bad push could lose the history for good.
  In the live bucket each snapshot is its own key, publish never deletes keys
  (only `rollback` does, `publish.py:199`), and the bucket is versioned.
- If the state unit ever comes back without history but the live bucket has it,
  restoring is a manual `aws s3 sync` (runbook note). No auto-restore in v1.

## Pipeline changes

### New stage `build_index_attribution`

- Added to `BUILD_STAGES` (`runner.py:33-37`) right after `build_contr_to_var`.
  `BUILD_STAGES` is part of both `LEAN_STAGES` and `FULL_STAGES`, so it runs
  every Saturday. Needs `build_price_parquets` (daily parquets), `build_factor_metrics`
  (sectors), `fetch_etf_prices` (reference). Not in `LIMITABLE`; build stages
  aren't checkpointed, so no runner change beyond the list.
- **No API calls.** Reads only files already on the task's disk.
- New module `pipelines/attribution.py` with the pure function:

  ```python
  def compute_attribution(prices: pd.DataFrame,      # date × symbol close, any calendar
                          weights: pd.Series,        # symbol -> declared weight (decimal)
                          sectors: pd.Series,        # symbol -> sector, NaN allowed
                          holdings_date: pd.Timestamp,
                          reference: pd.Series | None,  # proxy ETF close
                          windows=ATTRIBUTION_WINDOWS) -> pd.DataFrame  # long format
  ```

  Vectorised over the price matrix: one `asof`/`searchsorted` per window on the
  common grid, no per-symbol loop.
- Wrapper `IndexDataPipeline.build_index_attribution(self, constituent_keys=None)`
  in `stock_pipeline.py`, mirroring `build_contr_to_var` (`:1815-1848`): reuses
  `constituent_weights` (`:1724`), and on failure records `result.record(False, sub)`
  and leaves the previous parquet in place. `result.detail[sub]` carries the
  per-window covered weight, residual, identity error and row count for the
  checks.
- `_load_adj_close_matrix` (`:1735`) gains `column="adjClose"` and `since=None`
  parameters. Attribution calls it with `column="close"` and
  `since = T − 1Y − 15 days`. The existing positional `lookback=100` stays for
  `build_contr_to_var`.
- Sectors from the site-wide `stock_data/company_profiles/company_profiles.parquet`
  (built earlier in the run; 13,771 symbols, 99.99% with a sector), falling back
  to the list's factor_metrics parquet. (Changed 2026-11-07: factor_metrics alone
  silently left 92% of S&P 500 weight "Unclassified" on a `--limit` build.)
- Price lookup searches **every** universe's daily folder, own universe first.
  Measured on local data (2026-11-07): a symbol is saved under whichever list
  fetched it, so e.g. `SJ.TO` (1.2% of XCS) lives in `tsx/` and `msci_sm/` but
  not `tsx_small_cap/`. Holdings and price files are both FMP symbols
  (EAFE rows already carry suffixes: `ASML.AS`, `HSBA.L`), so lookup is an
  exact match; no fuzzy or suffix normalisation in v1. Names still unmatched go
  to `unattributed`; the first run's list decides whether normalisation is
  worth adding.

### Output

One long-format parquet per universe:
`index_data/attribution/{sub}_attribution.parquet` (`sub` = `sp500`, `nas`,
`r2000`, `tsx`, `tsx_small_cap`, `msci_eafe`, `rmicro`, `msci_sm`; the same short
names as `contr_to_var`, i.e. the Django `risk_key`). One object per universe
is one atomic publish unit.

| Column | Dtype | Rows |
|---|---|---|
| `window` | string | all |
| `level` | string: `index`, `sector`, `constituent`, `joined`, `unattributed`, `non_equity` | all |
| `key` | string: symbol, sector name, or `__index__` | all |
| `sector` | string | constituent, joined |
| `weight_start_pct` | float64 | all but joined |
| `weight_end_pct` | float64 | all |
| `return_pct` | float64 | all but unattributed, non_equity |
| `contribution_pp` | float64 | index, sector, constituent |
| `count` | Int64 | index, sector, buckets |
| `start_date`, `end_date`, `holdings_date` | datetime64[ns] | all |
| `return_basis` | string `"price"` | index |
| `currency_basis` | string `"local"` / `"USD"` / `"CAD"` | index |
| `ref_symbol`, `ref_return_pct`, `residual_pp` | string / float64 | index |
| `covered_weight_pct`, `breadth_up`, `breadth_pct_up`, `breadth_pct_beat`, `median_return_pct`, `effective_n`, `names_to_50pct`, `top10_contribution_pp`, `ew_return_pct`, `cap_minus_ew_pp` | float64 | index |

inf → NaN before writing; `to_parquet(index=False)` like `:1843`.

Built parquets are not state (state is pushed only after fetch stages), so a
universe skipped this run has no local file; the live copy stays as last
published because publish never deletes keys. `counts.attribution` and the
build failure rate are capped at WARN for this reason (review finding C1).

### Registration and checks

- `outputs.py`: add `"constituents_history"` and `"attribution"` to
  `DATASET_ORDER` (`:13-15`). Order: `constituents_history` after
  `constituents`; `attribution` after `factor_metrics`. Add
  `add(p.attribution_dir, "index_data/attribution", "attribution")` and one
  `add(...)` per sub for the history folders (`_files` isn't recursive).
  Update `test_outputs.py`'s expected list.
- `checks.py`: `REQUIRED_COLUMNS["attribution"] = {"window", "level", "key", "contribution_pp"}`
  (`:21-26`). New pure `check_attribution(detail)` wired into `run_checks` next
  to `check_factor_coverage` (`:178-190`, `:238`):

  | Check | Status in v1 |
  |---|---|
  | any non-finite in a numeric column the payload serves | WARN |
  | identity error > 1e-6 pp (sectors ≠ index, or weights ≠ 100%) | WARN |
  | covered weight < 97% (rmicro, msci_sm: 90%), any window | WARN |
  | residual over the table above | WARN |
  | residual on msci_eafe / msci_sm | PASS, value reported |

  **Every attribution check is WARN-only in v1.** A FAIL fails the whole weekly
  run, so nothing at all would publish; a bug in a new dataset must not block
  prices and fundamentals. With `always_hold` on, a WARN holds the run for the
  owner, who can discard it. After three clean runs, promote non-finite,
  identity and coverage to FAIL (one-line change in `thresholds.py`).

- `thresholds.py`: `MIN_COUNTS["attribution"] = 8` (no floor for the
  ever-growing `constituents_history`; `check_counts` catches a shrink), plus
  `ATTRIBUTION_MIN_COVERAGE`, `ATTRIBUTION_MIN_COVERAGE_LONG_TAIL`,
  `ATTRIBUTION_RESIDUAL_WARN_BP`.
- `check_counts` skips datasets with no baseline (`checks.py:148-153`), so the
  first run with the new datasets doesn't trip it; `MIN_COUNTS` covers the
  first run.
- A `--limit` run fails coverage by design, like the factor-coverage check. The
  local smoke test calls `IndexDataPipeline(root=<copy of local data>).build_index_attribution()`
  directly on full local data (below), not `run --limit`. No new CLI flag.

## Django changes

- `utils/StockCalculations.py`: `load_index_attribution(universe)` next to
  `load_factor_metrics` (`:107-120`), same `pq.read_table` from
  `s3://thetradingfloor/index_data/attribution/{universe}_attribution.parquet`.
- `get_index_sector_contribution` (`index_tools.py:677`):
  - cache key `index:sector_contribution:{risk_key}:v2`;
  - reshapes the long frame into the **current** response shape
    (`windows[w].contribution[]` with `sector`, `weight_pct`, `contribution_pp`,
    `average_return`, `count`; `index_return_pp`; `breadth`), so the existing
    `SectorContribution.js` keeps working;
  - adds `source: "pipeline"`, `return_basis`, `currency_basis`,
    `holdings_as_of`, `windows_available` (from the file), and per window
    `top_contributors`, `bottom_contributors`, `concentration`,
    `cap_minus_ew_pp`, `reconciliation`, `coverage`;
  - when the parquet is missing (`FileNotFoundError`/`OSError`/`ArrowIOError`),
    falls back to the current `_sector_contribution` with `source: "live"`,
    cached for 15 minutes rather than `CACHE_TTL`, so it stops being served
    soon after the first publish;
  - both sources missing → `KeyError` → 404.
- Bug fixes in the fallback path: null sector → `"Unclassified"`.
- Celery beat refreshes from the bucket at fixed times; the attribution reads
  are on-request with a 24h cache, so new data shows within a day of publish.
  No beat change.

## Frontend changes

`src/componentsLegacy/IndexDetail/SectorContribution.js` (via
`useIndexSectorContribution`, `src/lib/indexApi.js:41`):

- Window selector driven by `windows_available` (1W, 2W, 1M, 3M, YTD, 1Y).
- Top/bottom 10 contributors table.
- Strip with breadth, concentration and cap − EW gap.
- Labels: "price return"; "local currency" on the two MSCI pages; "holdings as
  of {date}"; "unattributed X%" when coverage < 100%.
- Absent fields (fallback payload) render as they do today.

## AWS changes

**No infrastructure (CDK) change is needed.**

| Concern | Finding |
|---|---|
| Write permission for the new prefixes | The publish task can Get/Put `thetradingfloor/*` (`pipeline_stack.py:129-130`). The run task never writes the live bucket. |
| Django read permission | `deploy/iam-django-policy.json` grants `GetObject` on `thetradingfloor/*`. |
| State | New local files are under `index_data/`, an existing state unit. |
| Task size / timeout | Run task 4 vCPU / 16 GB / 150 GB (`pipeline_stack.py:117`), 12h timeout. Close matrix for r2000 over ~1Y ≈ 2,000 × 260 floats, trivial. Adds an estimated 1-3 minutes. |
| Schedules, state machines | Unchanged. The same `run --mode lean|full` command picks up the new stage. |
| FMP bandwidth | Zero extra calls. |

**What does change is the container image**, which only rebuilds on
`cdk deploy`. So shipping each pipeline phase means:

```bash
cd fintank/infra
.venv/bin/python -m pytest -q
cdk diff --profile fintank -c alert_email=<owner email> -c news_schedule=on -c weekly_schedule=on [-c always_hold=...]
cdk deploy --profile fintank -c alert_email=<owner email> -c news_schedule=on -c weekly_schedule=on [-c always_hold=...]
```

Repeat **every** flag currently in use; an omitted flag reverts to its default
and turns the schedules off. `cdk diff` should show only the image asset hash
changing.

**always_hold:** the Nov 7 run is the third of the three clean runs after which
the handoff says to set `always_hold=false`. Recommended: keep `always_hold`
**on** for the first run that includes `constituents_history` and the first that
includes `attribution`, review the held email, then flip it in the next deploy.

## Phases and order

Each phase is its own commit (or PR) with tests green before the next.

| Phase | What | Ships via | Earliest live run |
|---|---|---|---|
| 0 | Holdings history in `refresh_constituents` + `constituents_history` dataset + checks/thresholds + tests | owner `cdk deploy` | Sat 2026-11-14 (lean) |
| 1 | `ATTRIBUTION_WINDOWS` + `pipelines/attribution.py` pure compute + unit tests | no deploy (library only) | n/a |
| 2 | Stage wrapper, loader params, outputs/checks/thresholds wiring, local smoke run against `class_files/stock_data` | owner `cdk deploy` | Sat 2026-11-21 (lean), or 11-14 if 0-2 ship together |
| 3 | Django loader + v2 payload + fallback + tests | web deploy (push to `main`, once `deploy/README.md` go-live is done) | any time; safe before or after phase 2 thanks to the fallback |
| 4 | Frontend window selector + contributors table + labels | web deploy | after phase 3 |
| later | Segment-linked attribution from history (3M ~Feb 2027, YTD/1Y ~Nov 2027); FX for MSCI; Brinson vs EW panel | | |

First full run with attribution: Sat 2026-12-05.

### Verification per phase

- Pipeline: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests -q`.
- Phase 2 smoke test, local data only, no AWS, no notebooks: run the stage
  against `class_files/stock_data` writing to a scratch root, then compare
  per-universe `R_bh` with the proxy ETF's return by eye.
- Infra: `cd infra && .venv/bin/python -m pytest -q`, then `cdk diff`.
- Django: `cd backend && ../../.venv/bin/python manage.py test analyzer`.
- First AWS run: in the held email, check `minimum.attribution`,
  `attribution.*` coverage/identity/residual lines, then spot-check one parquet
  from `runs/<run-id>/stage/index_data/attribution/` with `aws s3 cp` to scratch
  before approving.

## Tests

`pipelines/tests/test_attribution.py`, hand-built frames:

- `t_s = T`: `1 + R = 1/Σ w_T/(1+r)` and `c_i` match the closed form.
- The end-weight bias equals `Var_w0(r)/(1+R)` (guards against regressing to the old method).
- Two names, 50/50, +20% / −10%: hand-computed `w0` and `c`.
- `t_s` three weeks before `T` (stale holdings) drifts correctly.
- Identity: sectors = index, all buckets = 100%, to 1e-9.
- No start price → `joined`; no price file → `unattributed`; `USD`/`XTSLA`/`ESZ6`
  rows → `non_equity`.
- Weights summing to 80 and 120; zero/NaN weights; all-zero weights → empty, no error.
- Null sector → `Unclassified`; single-name sector.
- Zero or inf price never emits inf.
- Holiday/weekend anchors equal `Series.asof`; window starting before the first
  print → window omitted, not partial.
- Ragged multi-calendar grid (msci_eafe-style) with one stale name.
- `factor_metrics` columns unchanged (guards `WINDOWS`).

Also `test_outputs.py` (new datasets/keys/order), `test_checks.py`
(`check_attribution` statuses), `test_build_results.py` (skipped universe
leaves the old parquet), and Django `test_sector_contribution.py` (v2 cache
key, response shape contract, fallback with short TTL, no NaN/inf, 404s).

## Open items

- ~~Is `updated` the holdings date?~~ Yes (checked 2026-11-07): it differs per
  ETF (2026-10-15 13:34 to 2026-10-16 15:56) while all files were fetched
  2026-10-17. `t_s` = the date part of `updated`.
- Non-equity blocklist: build it from the actual non-priced rows of the first
  run's constituents JSONs rather than guessing.
- Update `docs/RECENT_CHANGES.md` and `backend/pipelines/README.md` (new
  datasets, new held-email lines, history restore note) in phase 2.
