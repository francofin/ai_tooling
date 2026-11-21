# FMP stable migration, branch 2 (weekly pipeline): implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The weekly AWS pipeline makes no `api/v3` or `api/v4` calls. It fetches from FMP `stable` and writes JSON, parquet and Django-bound files with exactly the v3-era field names and types.

**Architecture:** Approach 2A. Each v3 call is swapped one for one for its `stable` equivalent. A new pure module, `pipelines/fmp_stable_shapes.py`, turns each `stable` response back into the v3 row shape before anything is saved. The state-bucket JSON, `FIELD_MAPPINGS`, the build stage and every downstream reader therefore stay unchanged. `stock_pipeline.py` only changes how it fetches: URL builders, a history pager for stable's 5,000-row cap, and a shape step in the per-symbol driver.

**Tech stack:** Python 3.12, requests, pandas/pyarrow, pytest with moto (no AWS, no FMP in tests).

**Spec:** `docs/superpowers/specs/2026-11-19-fmp-stable-migration-design.md`, section "Branch 2".

## Global constraints

- No `api/v3` or `api/v4` URL anywhere in `backend/pipelines/*.py` when done. Task 7 adds a test that enforces this.
- Downstream shapes don't change: S3 parquet columns, constituent JSON keys and `FIELD_MAPPINGS` keep their names and dtypes. `FIELD_MAPPINGS` and `build_*` methods aren't edited.
- `pipelines/` must not import Django or `backend/utils` (the container is built from `pipelines/` only; see `tests/test_env_isolation.py`). Don't reuse `utils/fmp_stable.py`.
- Tests never call FMP. Fixtures are trimmed real responses saved under `backend/pipelines/tests/fixtures/fmp_stable/`, with no URLs or keys in them.
- FMP calls during development are limited to fixture capture (Task 1) and the verification script (Tasks 4 and 8).
- Every HTTP call to FMP goes through `self._get` (it redacts the key in errors) and is followed by one `self.limiter.tick()`.
- LF line endings in all touched files (all are LF today).
- Work happens in the worktree `/home/franc/projects/ai_agents/ai_tooling-worktrees/fmp-stable-pipeline` (branch `fix/fmp-stable-pipeline` from `origin/main`). The main folder stays on `feat/watchlist-analytics`, where Franc's servers run.
- Python: `/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python` (the worktree has no `.venv`). Pipeline tests: `cd backend && $PY -m pytest pipelines/tests -q`. CDK tests: `cd infra && /home/franc/projects/ai_agents/ai_tooling/fintank/infra/.venv/bin/python -m pytest -q`.
- The FMP key and AWS credentials come from `/home/franc/projects/ai_agents/ai_tooling/fintank/backend/.env` (pass it as `env_path`). Never print them.
- Stage exact paths only. Never `git commit -a`, never `git stash`. Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Every Python change gets a python-code-reviewer pass before the task is closed.

## Decisions taken here (spec "left to the builder")

1. **Raw OHLC is needed.** `analyzer/analyzer_utils/technicals.py` adjusts open/high/low by `adjClose/close`, `_close_series` (contribution to variance) reads raw `close`, and `_restated` compares `close`. So a stock price fetch is `historical-price-eod/full` (open/high/low/close/volume) plus `historical-price-eod/dividend-adjusted` (adjClose), joined on date. That is two calls per symbol. Incremental windows are 10 days, so bytes stay small.
2. **History cap.** `stable` returns at most 5,000 rows (about 20 years) per call, newest first, even with `from`. v3 files go back to 1999 (AAPL: 7,010 rows). A full download therefore pages backwards with `to`, until a page comes back under 5,000 rows or reaches `from`.
3. **Sort order.** Payloads saved to JSON keep v3's shape: `{"symbol": S, "historical": [rows newest first]}`.
4. **`label`.** stable has no `label`. It's synthesised as v3 wrote it: `date.strftime("%B %d, %y")` (e.g. `"November 13, 26"`). The parquet column stays a string.
5. **ETF `exchange`** comes from `profile-bulk` (CSV, paged by `part=0,1,…` until an empty part). `etf-list` decides membership, and bulk provides `exchangeFullName` → `exchange`, `exchange` → `exchangeShortName`, and `price`. `type` is always `"etf"`. Stored profiles were rejected because they only cover ETFs already on the list, so new ETFs would never enter.
6. **TTM.** Many v3 ratios-TTM fields moved to stable key-metrics-TTM and the reverse. Both stable TTM endpoints are fetched once per symbol and mapped together into the two v3 rows (tables in Task 6).
7. **Statements** request `limit=400`, matching the existing `ratios` call, because stable's default is 5 rows.

## Review focus

1. **A symbol with more than 5,000 trading days gets a full download** (new symbol, or restated). Expectation: the whole history back to `from` arrives, not just the last 20 years. Pinned in Task 2 (`test_full_download_pages_past_5000_rows`).
2. **A date present in `/full` but missing from `/dividend-adjusted`, or the reverse.** Expectation: the row keeps OHLC with `adjClose` None (dropped later by `daily_metrics`' dropna), and an adjusted-only date is dropped rather than written with no `close`. Pinned in Task 1 (`test_price_payload_joins_on_date_only`).
3. **First run after the switch: stable's adjClose differs slightly from the saved v3 adjClose,** so `_restated` flags many symbols and triggers full re-downloads (4 calls each). Expectation: measured, not discovered at run time. Task 4 reports the share of sample symbols `_restated` would flag, and the PR text states the expected first-run call count.
4. **An unknown or delisted symbol returns `[]`.** Expectation: the same "empty 'historical' payload" failure v3 gave, and a 402 still counts as not-on-plan. Pinned in Task 2 (`test_empty_stable_history_raises`).
5. **Holdings rows with no `asset` (cash lines), and stable's extra `symbol` key (the ETF itself).** Expectation: asset-less rows are dropped and `symbol` is removed, so `item.get("asset") or item.get("symbol")` can never pick the ETF ticker as a member. Pinned in Task 3 (`test_holdings_rows_drop_symbol_and_cash_lines`).

---

### Task 1: Worktree, fixtures, and the price/index shapers

**Files:**
- Create: `backend/pipelines/fmp_stable_shapes.py`
- Create: `backend/pipelines/tests/fixtures/fmp_stable/` (JSON fixtures below)
- Create: `backend/pipelines/tests/test_fmp_stable_shapes.py`
- Create: `docs/superpowers/plans/2026-11-21-fmp-stable-pipeline.md` (this plan, copied in)

**Interfaces, produces:**
- `HISTORY_ROW_CAP = 5000`
- `v3_label(date: str) -> str`
- `price_payload(symbol: str, full_rows: list[dict], adjusted_rows: list[dict]) -> dict` returns `{"symbol", "historical"}`, newest first. Each row has `date, open, high, low, close, adjClose, volume, label`, plus `change, changePercent, vwap` when stable sends them.
- `index_payload(symbol: str, full_rows: list[dict]) -> dict`, same shape, with `adjClose = close`.
- `load_fixture(name) -> list|dict` in `tests/helpers.py` (reads `tests/fixtures/fmp_stable/{name}.json`).

- [ ] **Step 1:** Once Franc has run `git fetch origin`, create the worktree with `git -C /home/franc/projects/ai_agents/ai_tooling worktree add /home/franc/projects/ai_agents/ai_tooling-worktrees/fmp-stable-pipeline -b fix/fmp-stable-pipeline origin/main`. Copy this plan in. Run the pipeline tests and record the baseline count.
- [ ] **Step 2: Capture fixtures** (one call each, Python with the key from the main `.env`, writing only the JSON body). Trim to at most 30 rows unless stated:
  - `px_full_aapl` (`historical-price-eod/full?symbol=AAPL&from=2026-10-01`)
  - `px_divadj_aapl` (same window)
  - `idx_full_gsptse` (`^GSPTSE`, same window)
  - `etf_holdings_spy` (keep 40 rows, including any row with an empty `asset`)
  - `etf_list` (40 rows), `profile_bulk_part0` (40 ETF rows plus 5 non-ETF rows, CSV text kept as a `.csv` fixture)
  - `income_q_aapl`, `balance_q_aapl`, `cashflow_q_aapl` (`limit=400&period=quarter`, keep 8 rows). Also record the full row count to confirm the limit is honoured.
  - `ratios_ttm_aapl`, `key_metrics_ttm_aapl`
  - `sector_snapshot_nyse`, `sector_snapshot_nasdaq` (`sector-performance-snapshot?date=2026-11-20&exchange=…`)
  - `etf_sector_weightings_spy`
  - Paging probe, not saved: `historical-price-eod/full?symbol=AAPL&from=1999-01-01`. Confirm the row count is 5,000, note the oldest date, then request `to=<oldest−1 day>` and confirm older rows arrive. If paging doesn't work, stop and report.
  - `profile-bulk` part probe, not saved: count parts until an empty one, and note any rate-limit response. Report the part count and total bytes.
- [ ] **Step 3: Write failing tests** in `test_fmp_stable_shapes.py`:
  - `test_v3_label_format`: `v3_label("2026-11-13") == "November 13, 26"`
  - `test_price_payload_shape`: built from the AAPL fixtures. `historical[0]["date"]` is newest. Each row's keys ⊇ `{date, open, high, low, close, adjClose, volume, label}`. `adjClose` equals the dividend-adjusted fixture's value for that date. `volume` is an `int`.
  - `test_price_payload_joins_on_date_only`: a full-only date → `adjClose is None`, and an adjusted-only date isn't present.
  - `test_index_payload_copies_close`: `adjClose == close` on every row, newest first.
- [ ] **Step 4:** Run `$PY -m pytest pipelines/tests/test_fmp_stable_shapes.py -q`. Expected: FAIL (module missing).
- [ ] **Step 5:** Implement the two shapers and `v3_label` in `fmp_stable_shapes.py`. Pure functions, no I/O, no pandas.
- [ ] **Step 6:** Run the same command. Expected: PASS.
- [ ] **Step 7:** Commit the fixtures, shapes module, test, helper and plan.

### Task 2: Prices and index history on stable

**Files:**
- Modify: `backend/pipelines/stock_pipeline.py` (`_index_history_url`, `_prices_url`, `_fetch_symbol_prices`, `_price_payload`, `fetch_index_prices`, plus new helpers next to `_get`)
- Test: `backend/pipelines/tests/test_stable_history.py`

**Interfaces:**
- Consumes: `price_payload`, `index_payload` and `HISTORY_ROW_CAP` from Task 1.
- Produces: `StockDataPipeline._stable_rows(path: str, **params) -> list[dict]`, which is one `_get` plus one `limiter.tick()`, raises `ValueError` on a non-list body, and is used by Tasks 3 to 7. Also `StockDataPipeline._stable_history(path: str, symbol: str, from_date: str | None) -> list[dict]`, which pages backwards while a page holds `HISTORY_ROW_CAP` rows and its oldest date is after `from_date`, then returns rows de-duplicated by date.

- [ ] **Step 1: Write failing tests** with `_get` patched on the instance (pattern as in `tests/test_fetch_results.py`):
  - `test_full_download_pages_past_5000_rows`: a fake returns 5,000 rows for the first call and 300 older rows for the call with `to`. The saved `historical` holds 5,300 unique dates, and `limiter.tick` was called once per HTTP call.
  - `test_incremental_window_uses_both_endpoints`: an existing file plus an unchanged overlap means mode `"incremental"`, exactly 2 HTTP calls (`/full` and `/dividend-adjusted`, both with `from=` the overlap date), and merged rows saved.
  - `test_restated_redownloads_full_history`: a moved adjClose in the overlap means mode `"restated"` and the file is replaced.
  - `test_empty_stable_history_raises`: both endpoints return `[]` with no saved file, so `ValueError("empty 'historical' payload")`.
  - `test_index_backfill_and_update_on_stable`: cold start pages from `START_DATE`; with an existing parquet, one call with `from=` the last date. The parquet columns equal `RAW_PRICE_COLS` plus metrics, with `label` present.
- [ ] **Step 2:** Run `$PY -m pytest pipelines/tests/test_stable_history.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement. `_prices_url` and `_index_history_url` are replaced by calls to `_stable_history("historical-price-eod/full"| "historical-price-eod/dividend-adjusted", …)` and the Task 1 shapers. `fetch_index_prices` reads `index_payload(...)["historical"]`. Remove the `[v3-only]` comments that no longer apply and update the docstrings (call count: "two per symbol, four on a restated or new symbol beyond 5,000 rows").
- [ ] **Step 4:** Run the new tests, then the full pipeline suite. Expected: all PASS, with the count at baseline plus the new tests.
- [ ] **Step 5:** python-code-reviewer pass on the diff, then fix, re-run and commit.

### Task 3: Constituents (ETF holdings) and the ETF list

**Files:**
- Modify: `backend/pipelines/fmp_stable_shapes.py`, `backend/pipelines/stock_pipeline.py` (`_etf_holder_url`, `_etf_list_url`, the `holdings` and `etf_list` closures in the constituent refresh), `backend/pipelines/pipeline_config.py` (comments at L30 and L52 only)
- Test: `backend/pipelines/tests/test_fmp_stable_shapes.py`, `backend/pipelines/tests/test_stable_constituents.py`

**Interfaces, produces:**
- `holdings_rows(stable_rows: list[dict]) -> list[dict]` with keys exactly `asset, name, isin, cusip, sharesNumber, weightPercentage, marketValue, updated`. Mapping: `securityCusip→cusip`, `updatedAt→updated`, `symbol` dropped, rows with a falsy `asset` dropped.
- `etf_list_rows(etf_list: list[dict], bulk_rows: list[dict], exchange_filter: list[str]) -> list[dict]` with keys exactly `symbol, name, price, exchange, exchangeShortName, type`, keeping symbols in both inputs whose `exchangeFullName` is in the filter. `price` is a float or None.
- `StockDataPipeline._profile_bulk() -> list[dict]` reads parts `0..n` through `_get_text` (a CSV variant of `_stable_rows`: same redaction and tick) until an empty part, parsed with `csv.DictReader`.

- [ ] **Step 1: Write failing tests:**
  - `test_holdings_rows_drop_symbol_and_cash_lines` (fixture plus one hand-added `{"asset": ""}` row): keys are exactly as above, `"symbol"` is in no row, and the count equals the fixture's non-empty assets.
  - `test_holdings_weight_is_float`.
  - `test_etf_list_rows_join_exchange`: from the fixtures, each output row's `exchange` is in `ETF_EXCHANGE_FILTER`, the keys are exactly as above, and `type == "etf"`.
  - `test_refresh_constituents_on_stable` (driver level, `_get` patched): `sp500_const` is saved with v3 keys, the snapshot date is taken from `updated`, and the existing 50%-shrink guard still raises on a short payload.
  - `test_profile_bulk_stops_at_empty_part`: three parts, the third empty, so 3 calls and 3 ticks.
- [ ] **Step 2:** Run the two test files. Expected: FAIL.
- [ ] **Step 3:** Implement. `stable/etf/holdings?symbol=` and `stable/etf-list` replace the v3 calls.
- [ ] **Step 4:** Run the tests and the full suite. Expected: PASS.
- [ ] **Step 5:** python-code-reviewer pass, fix and commit.

### Task 4: Verification script, part 1 (prices, indexes, constituents, ETF list), then run it

**Files:**
- Create: `backend/pipelines/verify_stable.py` (CLI, not imported by the pipeline or the tests)

**Interfaces:**
- Consumes: `StockDataPipeline(root=<tmpdir>, env_path=<main .env>)` and its fetchers from Tasks 2 and 3.
- Produces: `python -m pipelines.verify_stable {prices,constituents,fundamentals,all} --out <report.md>` exits non-zero if any pass rule fails. Task 8 adds `fundamentals`.

Behaviour (decided here):
- Sample: the first 5 members by `weightPercentage` of each of the 8 `CONSTITUENT_PROXY_ETFS` lists, read from the **live** S3 constituent JSON (`thetradingfloor/index_data/constituents/`), plus the ETFs `SPY, XIU.TO, EFA, XEQT.TO, TLT`. That's 45 symbols. Indexes: `sp500, sp500_tr, tsx, tsx_60, nikkei_225, ftse_100, russell_2000, vix`.
- Prices: write a one-list constituent file into the temp root, run `fetch_stock_prices(from_date=START_DATE)` then `build_price_parquets`, and diff each daily parquet against the live `stock_data/stock_prices/daily/{sub}/{SYM}_prices.parquet` on overlapping dates. Indexes: run `fetch_index_prices` cold, then diff against the live index parquets.
- Pass rule: identical column set and dtypes (every downstream field exists with the same name and type). `adjClose` within 0.5% relative on ≥ 99% of overlapping rows per symbol. `close` within 0.5% on ≥ 99%. The oldest date is within 5 trading days of the live file's oldest date (proves paging). Report each failing symbol with its worst rows.
- Restatement measure (Review focus 3): for each sample symbol, run `_restated(live_last_30_rows, stable_last_30_rows)` and report the share flagged.
- Constituents: for each list, member overlap with the live JSON ≥ 95%, identical key set, and identical value types per key. ETF list: count within ±10% of the live 8,521 and overlap ≥ 90%.
- The report is markdown with a table per check. It contains no URLs and no keys.

- [ ] **Step 1:** Write `verify_stable.py` (prices and constituents parts).
- [ ] **Step 2:** Run `cd backend && $PY -m pipelines.verify_stable prices --out /tmp/claude-1000/.../scratchpad/verify_prices.md`, then `constituents`. Expected: exit 0. Otherwise each failure is explained (data drift or a basis change) in the report, or fixed.
- [ ] **Step 3: Checkpoint.** Show Franc the two reports: the pass/fail table, the restatement share, the expected first-run call count, and anything explained instead of fixed. Wait for his OK before Task 5.
- [ ] **Step 4:** python-code-reviewer pass on the script, then commit.

### Task 5: Statements on stable

**Files:**
- Modify: `fmp_stable_shapes.py`, `stock_pipeline.py` (`_income_url`, `_balance_url`, `_cashflow_url`, `fetch_financial_statements`, `_fetch_constituent_datasets`)
- Test: `test_fmp_stable_shapes.py`, `tests/test_stable_fundamentals.py`

**Interfaces:**
- Produces `statement_rows(kind: str, rows: list[dict]) -> list[dict]` with `kind in {"income", "balance", "cashflow"}`. Renames apply to all kinds: `filingDate→fillingDate`, `fiscalYear→calendarYear`. Income only: `epsDiluted→epsdiluted`. The derived income ratios are each part divided by `revenue`, or None when revenue is 0 or None: `grossProfitRatio←grossProfit`, `ebitdaratio←ebitda`, `operatingIncomeRatio←operatingIncome`, `incomeBeforeTaxRatio←incomeBeforeTax`, `netIncomeRatio←netIncome`. `link` and `finalLink` are None. Any further balance or cash-flow rename found by diffing the Task 1 fixtures' keys against `FIELD_MAPPINGS['balance_sheet_statements' | 'cash_flow_statements']` is added to a module-level `STATEMENT_RENAMES[kind]` dict. Every key of the target `FIELD_MAPPINGS` must be present in each output row, with None allowed.
- The driver change: dataset tuples become `(data_type, fetch, suffix, merge)` where `fetch(symbol) -> payload` (list or dict). Existing callers wrap their URL builder as `lambda s: self._get(builder(s))` plus a tick. Statements use `lambda s: statement_rows(kind, self._stable_rows(path, symbol=s, period="quarter", limit=400))`.

- [ ] **Step 1: Write failing tests:**
  - `test_statement_rows_cover_field_mappings[income|balance|cashflow]`: every key of the matching `FIELD_MAPPINGS` is in every row.
  - `test_income_ratios_derived`: `grossProfitRatio == grossProfit / revenue` on the fixture's first row (`pytest.approx`).
  - `test_income_ratios_none_when_revenue_zero`.
  - `test_calendar_year_keeps_v3_type`: `type(row["calendarYear"]) is str`.
  - `test_statements_driver_saves_v3_rows` (driver level, patched `_get`).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement the shaper, the driver tuple change, and the three stable calls. Update the `fetch_financial_statements` docstring.
- [ ] **Step 4:** Run the tests and the full suite. Expected: PASS (profiles, ratios and TTM still go through the driver unchanged in behaviour).
- [ ] **Step 5:** python-code-reviewer pass, fix and commit.

### Task 6: Ratios TTM and key metrics TTM on stable

**Files:**
- Modify: `fmp_stable_shapes.py`, `stock_pipeline.py` (`_ratios_ttm_url`, `_metrics_ttm_url`, `fetch_ttm_ratios`)
- Test: `test_fmp_stable_shapes.py`, `tests/test_stable_fundamentals.py`

**Interfaces:**
- Produces `ttm_rows(ratios: dict, metrics: dict) -> tuple[dict, dict]`, returning `(v3_ratios_ttm_row, v3_metrics_ttm_row)`. Each output row contains every key of `FIELD_MAPPINGS['company_ratios_ttm']` or `['company_metrics_ttm']`, with None where the source is missing. A field present under the same name in stable is copied as is. The renamed ones come from `RATIOS_TTM_SOURCES` and `METRICS_TTM_SOURCES`: `{v3_field: (endpoint, stable_field, scale)}` with endpoint `"R"` (ratios-ttm) or `"M"` (key-metrics-ttm) and scale `1` or `100`. Initial tables (checked against values in Task 8):

  ratios-TTM v3 field ← source:
  `cashConversionCycleTTM←M.cashConversionCycleTTM`, `cashFlowCoverageRatiosTTM←R.operatingCashFlowCoverageRatioTTM`, `cashFlowToDebtRatioTTM←R.operatingCashFlowCoverageRatioTTM`, `companyEquityMultiplierTTM←R.financialLeverageRatioTTM`, `daysOfInventoryOutstandingTTM←M.daysOfInventoryOutstandingTTM`, `daysOfPayablesOutstandingTTM←M.daysOfPayablesOutstandingTTM`, `daysOfSalesOutstandingTTM←M.daysOfSalesOutstandingTTM`, `debtEquityRatioTTM←R.debtToEquityRatioTTM`, `debtRatioTTM←R.debtToAssetsRatioTTM`, `dividendYielPercentageTTM←R.dividendYieldTTM×100`, `dividendYielTTM←R.dividendYieldTTM`, `ebitPerRevenueTTM←R.ebitMarginTTM`, `interestCoverageTTM←R.interestCoverageRatioTTM`, `longTermDebtToCapitalizationTTM←R.longTermDebtToCapitalRatioTTM`, `operatingCycleTTM←M.operatingCycleTTM`, `payoutRatioTTM←R.dividendPayoutRatioTTM`, `peRatioTTM←R.priceToEarningsRatioTTM`, `pegRatioTTM←R.priceToEarningsGrowthRatioTTM`, `priceBookValueRatioTTM←R.priceToBookRatioTTM`, `priceCashFlowRatioTTM←R.priceToOperatingCashFlowRatioTTM`, `priceEarningsRatioTTM←R.priceToEarningsRatioTTM`, `priceEarningsToGrowthRatioTTM←R.priceToEarningsGrowthRatioTTM`, `priceFairValueTTM←R.priceToFairValueTTM`, `priceSalesRatioTTM←R.priceToSalesRatioTTM`, `priceToFreeCashFlowsRatioTTM←R.priceToFreeCashFlowRatioTTM`, `priceToOperatingCashFlowsRatioTTM←R.priceToOperatingCashFlowRatioTTM`, `returnOnAssetsTTM←M.returnOnAssetsTTM`, `returnOnCapitalEmployedTTM←M.returnOnCapitalEmployedTTM`, `returnOnEquityTTM←M.returnOnEquityTTM`, `shortTermCoverageRatiosTTM←R.shortTermOperatingCashFlowCoverageRatioTTM`, `totalDebtToCapitalizationTTM←R.debtToCapitalRatioTTM`.

  key-metrics-TTM v3 field ← source:
  `bookValuePerShareTTM←R.bookValuePerShareTTM`, `capexPerShareTTM←R.capexPerShareTTM`, `cashPerShareTTM←R.cashPerShareTTM`, `daysOfInventoryOnHandTTM←M.daysOfInventoryOutstandingTTM`, `daysPayablesOutstandingTTM←M.daysOfPayablesOutstandingTTM`, `daysSalesOutstandingTTM←M.daysOfSalesOutstandingTTM`, `debtToAssetsTTM←R.debtToAssetsRatioTTM`, `debtToEquityTTM←R.debtToEquityRatioTTM`, `debtToMarketCapTTM←R.debtToMarketCapTTM`, `dividendPerShareTTM←R.dividendPerShareTTM`, `dividendYieldPercentageTTM←R.dividendYieldTTM×100`, `dividendYieldTTM←R.dividendYieldTTM`, `enterpriseValueOverEBITDATTM←M.evToEBITDATTM`, `freeCashFlowPerShareTTM←R.freeCashFlowPerShareTTM`, `interestCoverageTTM←R.interestCoverageRatioTTM`, `interestDebtPerShareTTM←R.interestDebtPerShareTTM`, `inventoryTurnoverTTM←R.inventoryTurnoverTTM`, `marketCapTTM←M.marketCap`, `netIncomePerShareTTM←R.netIncomePerShareTTM`, `operatingCashFlowPerShareTTM←R.operatingCashFlowPerShareTTM`, `payablesTurnoverTTM←R.payablesTurnoverTTM`, `payoutRatioTTM←R.dividendPayoutRatioTTM`, `pbRatioTTM←R.priceToBookRatioTTM`, `peRatioTTM←R.priceToEarningsRatioTTM`, `pfcfRatioTTM←R.priceToFreeCashFlowRatioTTM`, `pocfratioTTM←R.priceToOperatingCashFlowRatioTTM`, `priceToSalesRatioTTM←R.priceToSalesRatioTTM`, `ptbRatioTTM←R.priceToBookRatioTTM`, `receivablesTurnoverTTM←R.receivablesTurnoverTTM`, `revenuePerShareTTM←R.revenuePerShareTTM`, `roeTTM←M.returnOnEquityTTM`, `roicTTM←M.returnOnInvestedCapitalTTM`, `shareholdersEquityPerShareTTM←R.shareholdersEquityPerShareTTM`, `tangibleBookValuePerShareTTM←R.tangibleBookValuePerShareTTM`.

- `fetch_ttm_ratios` keeps its two datasets and file names. Both `fetch` callables call `self._ttm_pair(symbol) -> tuple[dict, dict]`, which makes the two stable calls (2 ticks) and keeps only the last symbol's result, so each symbol costs 2 calls in total, as today.

- [ ] **Step 1: Write failing tests:**
  - `test_ttm_rows_cover_field_mappings`: all 58 and 61 keys are present.
  - `test_ttm_scale_100`: `dividendYielPercentageTTM == 100 * dividendYieldTTM`.
  - `test_ttm_cross_endpoint`: v3 `returnOnEquityTTM` comes from the key-metrics fixture.
  - `test_ttm_pair_two_calls_per_symbol`: the driver over 2 symbols makes 4 HTTP calls and writes 4 files.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the tests and the full suite. Expected: PASS.
- [ ] **Step 5:** python-code-reviewer pass, fix and commit.

### Task 7: Sector snapshot, sector exposure, and removing v3

**Files:**
- Modify: `fmp_stable_shapes.py`, `stock_pipeline.py` (`get_sector_snapshot`, `get_index_sector_exposure`, delete `V3_BASE` and `_v3`, refresh the endpoint comment block at about L303), `pipeline_config.py` (stale v3 comments at L20–31, L52, L92, L391–393), `backend/pipelines/README.md` (one line: the pipeline is on stable from this date)
- Test: `test_fmp_stable_shapes.py`, `tests/test_no_v3.py`

**Interfaces, produces:**
- `sector_snapshot_rows(rows_by_exchange: list[list[dict]]) -> list[dict]` returns `[{"sector": str, "changesPercentage": "x.xx%"}]`: the mean of `averageChange` per sector across the given exchanges, formatted `f"{v:.2f}%"`, in first-seen sector order. `get_sector_snapshot` requests NYSE and NASDAQ for the latest weekday (today if a weekday, else the previous Friday). If both are empty it retries once with the previous weekday.
- `get_index_sector_exposure` calls `stable/etf/sector-weightings?symbol=`. The parser already does `float(str(v).rstrip("%"))`, which accepts floats, so only the URL changes. A test pins that.

- [ ] **Step 1: Write failing tests:**
  - `test_sector_snapshot_averages_exchanges` (the two fixtures): 11 rows, each `changesPercentage` a string ending in `%`, and the value for one sector equals the mean of its two fixture values to 2 dp.
  - `test_sector_exposure_accepts_float_weights` (patched `_get` with the fixture).
  - `test_no_v3_or_v4_urls`: `api/v3` and `api/v4` don't appear in any `pipelines/*.py` file. The tests folder is excluded.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement and delete the v3 plumbing.
- [ ] **Step 4:** Run the full pipeline suite and the CDK tests. Expected: all PASS.
- [ ] **Step 5:** python-code-reviewer pass, fix and commit.

### Task 8: Verification part 2 (statements and TTM), full report

**Files:**
- Modify: `backend/pipelines/verify_stable.py` (adds `fundamentals`)

Behaviour: for the same 40 stock symbols (ETFs excluded), run `fetch_financial_statements` and `fetch_ttm_ratios` into the temp root, then `build_fundamentals_parquets`, and diff against the live fundamentals parquets. Pass rule: identical column set and dtypes. Numeric values within 1% relative wherever both sides are non-null, on overlapping statement dates. TTM is compared as a snapshot: the v3 values are from 2026-11-14, so price-based TTM fields (any `price*`, `pe*`, `pb*`, `ptb*`, `pfcf*`, `pocf*`, `dividendYield*`, `marketCap*`, `enterpriseValue*`, `debtToMarketCap*`, `peg*`) are compared after scaling by the symbol's close ratio between the two dates, and flagged rather than failed when only that drift explains the gap. Any v3 field whose table mapping disagrees by more than 1% on most symbols is reported with the stable field that does match, if one exists (this corrects the Task 6 table). A field that's missing always fails.

- [ ] **Step 1:** Add `fundamentals` to the script.
- [ ] **Step 2:** Run `$PY -m pipelines.verify_stable all --out …/verify_all.md`. Expected: exit 0, or every failure explained. Correct the Task 6 tables where the report shows a better match, re-run the Task 6 tests, and commit those corrections separately.
- [ ] **Step 3: Checkpoint.** Show Franc the report and wait for his OK.
- [ ] **Step 4:** python-code-reviewer pass, then commit.

### Task 9: Dry run, whole-branch review, PR text, deploy hand-off

- [ ] **Step 1:** `cd backend && $PY -m pipelines run --mode lean --dry-run --limit 5` (worktree; it writes to a local folder and uses the main `.env` through the CLI's env option, or `FINTANK_ENV_PATH` if that's what `cli.py` reads; check first). Expected: every stage passes its checks, with no 403 in the log.
- [ ] **Step 2:** Run the full pipeline suite and the CDK tests one last time and record the counts.
- [ ] **Step 3:** Whole-branch review (`superpowers:requesting-code-review`) on `origin/main..fix/fmp-stable-pipeline`, then fix findings.
- [ ] **Step 4:** Write the PR text to the scratchpad (summary, the decisions above, verification numbers, the expected first-run call count and duration, the deploy steps from `backend/pipelines/README.md`), ending with the Claude Code attribution line. Give Franc numbered steps, each with the full command, the machine it runs on and the expected output: push the branch, open the PR, merge, deploy the pipeline image per the README, start the run by hand, approve or discard after reading its report.
- [ ] **Step 5:** After Franc confirms the run was approved, add a dated entry to `~/projects/fintank-private-docs/docs/RECENT_CHANGES.md` (pipeline on stable, first-run numbers, follow-ups: branch 3, and the 2B bulk redesign later) and tell him the commit to push. Update the memory note `project_fintank_fmp_v3_dead.md`.
