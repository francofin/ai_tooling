# Fund Finder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An ETF exposure search: the reader picks a listing market, stocks to include and stocks to exclude, and gets the ETFs ranked by the combined weight of the included stocks.

**Architecture:** The weekly AWS pipeline builds the fund universe from `profile-bulk`, fetches `etf/holdings` per fund, looks through funds of funds, resolves every holding to a company id (ISIN of the home share; ADRs linked), and publishes `fund_data/` to S3 after checks. Django reads only the lookup buckets a query needs, through Redis. A Pages Router page `/fund-finder` renders the results.

**Tech Stack:** Python 3.12, pandas/pyarrow, pytest (pipeline), Django REST Framework + Django test runner (site), Next.js Pages Router, React-Bootstrap, SWR 1, `node --test` for pure `.mjs` utilities.

**Spec:** `fintank/docs/superpowers/specs/2026-11-22-fund-finder-design.md` (approved 2026-11-22). Read it before any task.

**Branch / worktree:** `feature/fund-finder` in `/home/franc/projects/ai_agents/ai_tooling-worktrees/fund-finder`. All paths below are relative to `fintank/` unless they start with `/`.

## Global Constraints

- FMP `stable` only; build every URL with `StockDataPipeline._stable_rows` / `_stable`. `pipelines/tests/test_no_v3.py` must keep passing.
- Tests never call FMP or AWS. Pipeline tests fake `pipeline._get` / `_get_text` as `test_stable_constituents.py` does.
- Never `git commit -a`; `git add` exact paths and check `git diff --cached --stat` before each commit. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Don't start servers, AWS runs or any live FMP call; Task 8's measurement needs the owner's go-ahead.
- Every new threshold lives in `backend/pipelines/thresholds.py`; every new universe filter in `backend/pipelines/pipeline_config.py`.
- Values pinned by the spec: AUM floor US $100M / CA $25M on `profile-bulk` `marketCap`; holding rows below **0.001%** dropped from the lookup; **64** buckets; up to **10** included and **10** excluded symbols; top **100** results (stock-page shortcut: top **10**); ties by AUM descending; identical-portfolio collapse within one market, same issuer, all pick weights within **0.01 pp**; cross-check symbols **RY.TO, TD.TO, SHOP.TO, AAPL, MSFT** (≥95% of FMP's in-universe funds present, weights within **0.5 pp** for ≥95%); ADR test pairs **TSM→2330.TW, ASML→ASML.AS, NVO→NOVO-B.CO**; ADR link share may not fall more than **5 pp** from last run; XEQT.TO must have **>1,000** rows with an `asset`.
- US exchanges: `AMEX, NASDAQ, NYSE, CBOE`; Canadian: `TSX, NEO` (the `exchange` column of `profile-bulk`).
- New checks are WARN-only (same mechanism as attribution: `WARN_ONLY_DATASETS`, `WARN_ONLY_STAGES`, a `FUND_FINDER_FAILURE_STATUS = "warn"`).
- Page copy (exact): disclaimer "Information only, not investment advice."; coverage note "ETFs only; mutual funds are not covered yet, and Canadian mutual funds are not available."; holdings line "Holdings fetched {date} from fund issuers via FMP."; empty state "No ETF in this market holds these stocks without the excluded ones."
- `listed` is required on the API (400 without it) and must be chosen in the UI before any fetch; no default.

## Review Focus

1. **A pick that is the "other" listing** (RY when funds list RY.TO, TSM when funds list 2330.TW): it must find the same funds. Pinned in Task 2 (`test_company_ids_*`) and Task 6 (`test_pick_us_listing_finds_tsx_holders`).
2. **An excluded stock held only through an underlying ETF**: the fund must be removed. Pinned in Task 3 (`test_look_through_*`) and Task 6 (`test_exclude_via_underlying`).
3. **Symbols the lookup doesn't know, lower-case or padded input** (`ry.to `, `ZZZZ`): normalised, unknown ones returned in `unknown`, never a 500. Pinned in Task 6 (`test_unknown_and_messy_symbols`).
4. **A fund whose holdings fetch fails this week**: keeps last week's file and still appears; the stage counts it as failed. Pinned in Task 4 (`test_failed_fetch_keeps_previous`).
5. **The same pick in include and exclude, or more than 10 of either**: 400 with a clear message. Pinned in Task 6 (`test_bad_queries`).

---

### Task 1: Fixtures

**Files:**
- Create: `backend/pipelines/tests/fixtures/fmp_stable/etf_holdings_xiu.json`, `etf_holdings_xeqt.json`, `etf_holdings_vea.json`, `etf_holdings_agg.json`, `profile_bulk_funds.csv`, `etf_asset_exposure_ry.json`, `etf_info_xiu.json`
- Delete when done: `backend/pipelines/tests/fixtures/fmp_stable/_probe_20261122/` (untracked raw probes saved 2026-11-22; never commit it)

- [ ] **Step 1: Trim the probe files into fixtures.** From `_probe_20261122/`: XIU.TO in full (65 rows); XEQT.TO the 40 largest rows with an `asset` plus 3 with empty `asset` (FMP returns it already looked through, so it holds no ETF rows); VEA the 30 largest rows plus the `RY.TO`, `TD.TO`, `SHOP.TO` rows and the stray `SHOP` row (0.0000046%); AGG 20 rows (all empty `asset`). Keep the stable field names (`asset`, `name`, `isin`, `weightPercentage`, `updatedAt`, `securityCusip`, ...).
- [ ] **Step 2: Write `profile_bulk_funds.csv` by hand** with the `profile-bulk` header (`symbol,price,marketCap,...,isEtf,isActivelyTrading,isAdr,isFund`) and these rows: ETFs `XIU.TO` (TSX, 22016318183), `XEQT.TO` (TSX, 18547474230), `ZEB.TO` (TSX, 4725377103), `ZWC.TO` and `ZWC-T.TO` (TSX, same name "BMO Canadian High Dividend Covered Call ETF", ZWC.TO larger), `BTCQ.TO` and `BTCQ-U.TO` (same name "3iQ Bitcoin ETF"), `VEA` (AMEX), `VTI` (AMEX), `AGG` (AMEX), `TQQQ` ("ProShares UltraPro QQQ", NASDAQ), `SH` ("ProShares Short S&P500", AMEX), `SHY` ("iShares 1-3 Year Treasury Bond ETF", NASDAQ), `VGSH` ("Vanguard Short-Term Treasury ETF", NASDAQ), `TINY.TO` (TSX, 10000000, below floor), `SPYX` (LSE, out of market), `XUS.TO` (TSX, "iShares Core S&P 500 Index ETF"), `IVV` (AMEX, "iShares Core S&P 500 ETF"); mutual fund `FXAIX` (`isFund` true); stocks `RY` (NYSE, CA7800871021), `RY.TO` (TSX, CA7800871021), `TD`/`TD.TO` (CA8911605092), `SHOP` (NASDAQ)/`SHOP.TO` (CA82509L1076), `AAPL` (US0378331005), `TSM` (NYSE, US8740391003, isAdr), `2330.TW` (TAI, TW0002330008, "Taiwan Semiconductor Manufacturing Company Limited"), `ASML` (NASDAQ, USN070592100, isAdr), `ASML.AS` (AMS, NL0010273215), `NVO` (NYSE, US6701002056, isAdr), `NOVO-B.CO` (CPH, DK0062498333), `DUPE` (NYSE, isAdr, "Twin Holdings", US0000000001) with two home rows `TWN.L` (LSE, GB0000000001) and `TWN.PA` (PAR, FR0000000001) both named "Twin Holdings". Company names for the three real ADR pairs must match their home rows exactly (as probed).
- [ ] **Step 3: Capture nothing new.** `etf_asset_exposure_ry.json` and `etf_info_xiu.json` are hand-written in the stable shapes (`[{"symbol": "XIU.TO", "asset": "RY.TO", "weightPercentage": 9.43, "sharesNumber": ..., "marketValue": ...}, ...]` for asset-exposure; `[{"symbol": "XIU.TO", "expenseRatio": 0.18, "assetsUnderManagement": ..., "nav": ..., "assetClass": "Equity", "etfCompany": "BlackRock", "inceptionDate": "1999-10-04"}]` for etf/info). If the implementer is unsure of a field name, mark the fixture `"_handwritten": true` and leave a TODO for Task 8 to compare against one live call.
- [ ] **Step 4: Commit** the seven fixture files (not `_probe_20261122/`).

### Task 2: Fund universe and company ids (pure)

**Files:**
- Create: `backend/pipelines/fund_universe.py`
- Modify: `backend/pipelines/pipeline_config.py` (add `FUND_US_EXCHANGES`, `FUND_CA_EXCHANGES`, `FUND_AUM_FLOOR = {"us": 100e6, "ca": 25e6}`, `FUND_LEVERAGED_PATTERN`)
- Test: `backend/pipelines/tests/test_fund_universe.py`

**Interfaces:**
- Produces:
  - `build_universe(bulk_rows: list[dict]) -> tuple[list[dict], dict]` → (funds, detail). Each fund: `{"symbol", "name", "exchange", "region" ("us"|"ca"), "currency", "aum", "isin", "series": [other symbols collapsed into it]}`. `detail = {"active_etfs", "dropped_leveraged": [names], "dropped_floor", "collapsed_series", "funds"}`.
  - `company_ids(bulk_rows: list[dict]) -> tuple[dict[str, str], dict[str, str], dict]` → (`symbol_to_company`, `isin_to_company`, detail). Company id = home-share ISIN; ADR linked per the spec rule; `detail = {"adrs", "adrs_linked", "unlinked": [symbols]}`.
  - `bucket_of(company_id: str, n: int = 64) -> int` = `int(hashlib.md5(company_id.encode()).hexdigest(), 16) % n`.

- [ ] **Step 1: Write failing tests** with `load_fixture("profile_bulk_funds", "csv")` parsed by `csv.DictReader`:
  - `test_universe_filters`: result symbols include `XIU.TO, XEQT.TO, VEA, VTI, AGG, SHY, VGSH, XUS.TO, IVV` and exclude `TQQQ, SH` (leveraged/inverse), `TINY.TO` (floor), `SPYX` (market), `FXAIX` (mutual fund), every stock. `"ProShares UltraPro QQQ"` is in `detail["dropped_leveraged"]`; `VGSH` ("Short-Term") is kept.
  - `test_series_collapse`: `ZWC.TO` kept with `series == ["ZWC-T.TO"]`; `BTCQ.TO` kept with `["BTCQ-U.TO"]` (largest AUM wins; base symbol on a tie).
  - `test_company_ids_interlisted`: `symbol_to_company["RY"] == symbol_to_company["RY.TO"] == "CA7800871021"`.
  - `test_company_ids_adr_links`: `TSM→TW0002330008`, `ASML→NL0010273215`, `NVO→DK0062498333`; `isin_to_company["US8740391003"] == "TW0002330008"`.
  - `test_company_ids_ambiguous_adr_unlinked`: `DUPE` keeps `US0000000001` and is in `detail["unlinked"]`.
  - `test_bucket_of_is_stable`: `bucket_of("CA7800871021") == <value computed once and pasted>`, and every result in `range(64)`. (The same literal appears in Task 6's Django test.)
- [ ] **Step 2: Run** `cd backend && /home/franc/projects/ai_agents/ai_tooling/.venv/bin/python -m pytest pipelines/tests/test_fund_universe.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement.** Leveraged pattern (case-insensitive, on `companyName`): `\b-?\d(\.\d)?x\b`, `\bultra(pro|short)?\b`, `leveraged`, `inverse`, `\bbear\b`, `\bbull\b`, `\bdaily\b(?! income)`, `\bshort\b(?![- ](term|duration|maturity|dated))`. Series key: symbol with a trailing `-U`, `-T`, `.U` before the `.TO` removed, plus the lower-cased name with "cad", "usd", "hedged", "unhedged", "non-hedged", "units", "series", "class" removed; group on both and keep the largest `marketCap`. Hedged/unhedged pairs with different base symbols (e.g. `XSP.TO`/`XUS.TO`) are **not** merged here; Task 6's identical-portfolio collapse handles them. ADR rule: for `isAdr` rows, candidates = non-ADR, non-ETF, non-fund rows with identical `companyName` whose exchange is not in `FUND_US_EXCHANGES`; link if exactly one distinct ISIN among them.
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Commit** `fund_universe.py`, `pipeline_config.py`, the test.

### Task 3: Lookup builder (pure)

**Files:**
- Create: `backend/pipelines/fund_lookup.py`
- Modify: `backend/pipelines/thresholds.py` (`FUND_MIN_HOLDING_PCT = 0.001`, `FUND_WEIGHT_SUM_RANGE = (90.0, 110.0)`, `FUND_BUCKETS = 64`)
- Test: `backend/pipelines/tests/test_fund_lookup.py`

**Interfaces:**
- Consumes: `bucket_of`, `company_ids` output (Task 2).
- Produces: `build_lookup(holdings: dict[str, list[dict]], funds: list[dict], symbol_to_company: dict, isin_to_company: dict, fund_info: dict[str, dict]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]` → (`exposure`, `funds_df`, `isin_map`, detail).
  - `holdings`: fund symbol → stable `etf/holdings` rows (raw, as saved by Task 4), including underlying ETFs fetched only for look-through.
  - `exposure` columns: `company_id` (str), `fund` (str), `weight` (float, percent), `via` (str, "" when direct), `bucket` (int).
  - `funds_df` columns: `symbol, name, exchange, region, currency, aum, mer, issuer, asset_class, fetched (YYYY-MM-DD), series (list[str]), rows, coverage_pct`.
  - `isin_map` columns: `symbol, company_id, name, exchange, is_adr`, every listing whose company id appears in `exposure`.
  - `detail`: `{"funds", "funds_with_rows", "rows", "weight_sum_outside": [symbols], "unexpanded": [fund symbols still holding a universe fund], "deep_chains": [..], "xeqt_asset_rows": int}`.

- [ ] **Step 1: Write failing tests:**
  - `test_direct_rows_resolve_by_isin`: XIU fixture → `exposure` has `company_id "CA7800871021"`, `fund "XIU.TO"`, weight ≈ 9.4299, `via ""`.
  - `test_symbol_fallback_when_no_isin`: a row with `isin ""` and `asset "RY.TO"` resolves to `CA7800871021`.
  - `test_tiny_rows_dropped`: the VEA stray `SHOP` row (0.0000046) is not in `exposure`; the `SHOP.TO` row (0.6067) is.
  - `test_look_through_expands_one_level`: synthetic fund `MIX.TO` holding `XIU.TO` 50% and `VEA` 50% → `MIX.TO`'s RY weight = 0.5·9.4299 + 0.5·0.8925 with `via` set per row (two rows, `via "XIU.TO"` and `via "VEA"`); `detail["unexpanded"] == []`.
  - `test_look_through_deep_chain_logged`: a fund holding `MIX.TO` is expanded one level only and listed in `detail["deep_chains"]`.
  - `test_xeqt_comes_looked_through`: XEQT fixture → `via` is "" on every row; `detail["xeqt_asset_rows"] == 40` with the fixture.
  - `test_coverage_and_weight_sum`: AGG (no `asset`, no resolvable ISIN for stocks) gives `rows == 0` in `exposure`, `coverage_pct == 0`, and is not in `weight_sum_outside` (its raw weights sum to ~100).
  - `test_isin_map_lists_all_listings`: `isin_map` contains both `RY` and `RY.TO` for `CA7800871021`, and `TSM` with `is_adr True` for `TW0002330008` when a fund holds `2330.TW`.
- [ ] **Step 2: Run** `/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python -m pytest pipelines/tests/test_fund_lookup.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** Resolve each row: `isin_to_company.get(isin)` → else `symbol_to_company.get(asset)` → else unresolved (counts toward `rows` but not `exposure`). A row whose resolved symbol is a key of `holdings` and a fund (in `funds` or fetched for look-through) is expanded: its holdings scaled by `weight/100`, `via` = that fund; a second-level fund inside is not expanded and the outer fund goes to `deep_chains`. After expansion, sum weights per (`company_id`, `fund`, `via`), then drop rows below `FUND_MIN_HOLDING_PCT`. `fetched` = date part of the most common `updatedAt`. `mer/issuer/asset_class` from `fund_info` (None when missing).
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Commit.**

### Task 4: Fetch stages

**Files:**
- Modify: `backend/pipelines/stock_pipeline.py` (memoise `_profile_bulk`; add `fund_holdings_dir`, `fund_info_dir` properties; add `fetch_fund_holdings`, `fetch_fund_info`)
- Modify: `backend/pipelines/runner.py` (`fetch_fund_holdings` in `LEAN_STAGES` and `FULL_STAGES` right after `refresh_constituents`; `fetch_fund_info` in `FULL_STAGES` right after it; both in `LIMITABLE`)
- Test: `backend/pipelines/tests/test_fund_fetch.py`; update `test_runner.py` stage-list assertions if they pin the lists.

**Interfaces:**
- Consumes: `build_universe` (Task 2).
- Produces:
  - `fund_holdings_dir` = `{json_root}/fund_holdings/` (a state unit automatically, via `state.SPLIT_ROOTS`). Files: `<SYMBOL>.json` (raw stable rows), `_universe.json` (the `build_universe` funds list), `_profile_slim.json` (every `profile-bulk` row reduced to `symbol, isin, exchange, companyName, isEtf, isFund, isAdr`, for Task 5's company ids), `_crosscheck/<SYMBOL>.json` (raw `etf/asset-exposure` rows for the five cross-check symbols).
  - `fund_info_dir` = `{json_root}/fund_info/`, files `<SYMBOL>.json` (raw `etf/info` rows).
  - `fetch_fund_holdings(limit: int | None = None) -> StageResult` (name `"fetch_fund_holdings"`; `detail` = universe detail + `{"look_through_fetched": int, "crosscheck": [symbols saved]}`).
  - `fetch_fund_info(limit: int | None = None) -> StageResult` (name `"fetch_fund_info"`).
  - `_profile_bulk()` returns the cached list on the second call in one process.

- [ ] **Step 1: Write failing tests** (fake `_get` / `_get_text` from fixtures, `counting_ticks` as in `test_stable_constituents.py`):
  - `test_profile_bulk_memoised`: two calls → one set of part requests.
  - `test_fetch_fund_holdings_saves_each_fund`: universe from `profile_bulk_funds.csv`; every fund's file written; `_universe.json` and `_profile_slim.json` written; one `etf/holdings` request per fund plus five `etf/asset-exposure` requests.
  - `test_failed_fetch_keeps_previous`: a pre-existing `XIU.TO.json`, the fake raises `FetchHTTPError(…, 500)` for XIU.TO → file unchanged, `result.failed == 1`, `"XIU.TO"` in `failed_items`.
  - `test_look_through_fetches_missing_underlying`: a fund whose holdings contain an ETF symbol not in the universe (present in `profile-bulk` with `isEtf` true) → that ETF's holdings are fetched and saved, `detail["look_through_fetched"] == 1`.
  - `test_limit_caps_funds`: `limit=2` → two holdings requests (plus cross-check).
  - `test_fetch_fund_info_full_only`: `"fetch_fund_info" in FULL_STAGES and not in LEAN_STAGES`; saves `XIU.TO.json` under `fund_info/`.
- [ ] **Step 2: Run** `/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python -m pytest pipelines/tests/test_fund_fetch.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** Use `_stable_rows("etf/holdings", symbol=…)`, `_stable_rows("etf/asset-exposure", symbol=…)`, `_stable_rows("etf/info", symbol=…)` with `_retry_once`. An empty holdings list counts `record_no_data()` and keeps the previous file. A 402 counts as no data (same rule as `ed5daf4`). Errors are passed through `redact`.
- [ ] **Step 4: Run** the new tests and `/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python -m pytest pipelines/tests -q`. Expected: all PASS.
- [ ] **Step 5: Commit.**

### Task 5: Build stage, outputs and checks

**Files:**
- Modify: `backend/pipelines/stock_pipeline.py` (`fund_data_dir` property = `{root}/fund_data`; `build_fund_finder()`)
- Modify: `backend/pipelines/runner.py` (`build_fund_finder` in `BUILD_STAGES` after `build_index_attribution`; call `check_fund_finder` like `check_attribution`)
- Modify: `backend/pipelines/outputs.py` (`"fund_finder"` after `"attribution"` in `DATASET_ORDER`; `add(p.fund_data_dir, "fund_data", "fund_finder")` and `add(os.path.join(p.fund_data_dir, "exposure"), "fund_data/exposure", "fund_finder")`)
- Modify: `backend/pipelines/thresholds.py` (`MIN_COUNTS["fund_finder"] = 66` (funds + isin_map + 64 buckets); `FUND_FINDER_FAILURE_STATUS = "warn"`; add `"fund_finder"` to `WARN_ONLY_DATASETS`, `"build_fund_finder"` and `"fetch_fund_holdings"` to `WARN_ONLY_STAGES`; `FUND_MIN_FUNDS = 3000` placeholder, replaced in Task 8; `FUND_CROSSCHECK_PRESENT = 0.95`, `FUND_CROSSCHECK_WEIGHT_PP = 0.5`, `FUND_ADR_LINK_DROP_PP = 5.0`, `FUND_XEQT_MIN_ROWS = 1000`)
- Modify: `backend/pipelines/checks.py` (`check_fund_finder(detail: dict, previous: dict | None) -> list[CheckResult]`)
- Test: `backend/pipelines/tests/test_fund_build.py`, additions to `test_checks.py` and `test_outputs.py`

**Interfaces:**
- Consumes: `build_lookup` (Task 3), `company_ids` (Task 2), files from Task 4.
- Produces (local, then published under the same keys): `fund_data/funds.parquet`, `fund_data/isin_map.parquet`, `fund_data/exposure/{00..63}.parquet` (zero-padded bucket number; every bucket written, empty ones with the schema). `build_fund_finder() -> StageResult` with `detail` = lookup detail + company-id detail + `{"crosscheck": {symbol: {"in_universe": int, "present_pct": float, "weight_ok_pct": float}}, "adr_link_pct": float}`.
- `check_fund_finder` gets the previous published report's `build_fund_finder` detail (the runner already loads `LAST_PUBLISHED_REPORT` for `check_counts`; pass that report's stage detail) for the ADR-link drop; `None` when absent → PASS with "no baseline".

- [ ] **Step 1: Write failing tests:**
  - `test_build_writes_all_files` (fixtures from Tasks 1–4 on disk): 64 bucket files plus `funds.parquet` and `isin_map.parquet`; each `exposure` row is in the bucket `bucket_of(company_id)` names.
  - `test_outputs_registered`: `collect_outputs` returns 66 `fund_finder` outputs with keys `fund_data/funds.parquet`, `fund_data/isin_map.parquet`, `fund_data/exposure/00.parquet` … `63.parquet`.
  - `test_check_fund_finder_warns_not_fails`: detail with 10 funds (below `FUND_MIN_FUNDS`), cross-check present 0.5, `adr_link_pct` 10 pp below previous, `unexpanded` non-empty, `xeqt_asset_rows` 12 → every result's status is `WARN`, names `fund_finder.funds`, `fund_finder.crosscheck.RY.TO`, `fund_finder.adr_links`, `fund_finder.look_through`, `fund_finder.xeqt`, `fund_finder.weight_sum`.
  - `test_check_fund_finder_adr_pairs`: a detail whose company-id map sends TSM elsewhere → `fund_finder.adr_pairs` WARN.
  - `test_check_fund_finder_clean`: a clean detail → all PASS.
- [ ] **Step 2: Run** the three test files. Expected: FAIL.
- [ ] **Step 3: Implement.** The build reads `_universe.json`, every `<SYMBOL>.json`, `fund_info/` (whatever exists) and `_profile_slim.json` (company ids via `company_ids`). Cross-check: for each saved `_crosscheck/<SYMBOL>.json`, restrict FMP's funds to our universe, compute present % and the share with `|ours − FMP| ≤ 0.5 pp`. A build exception skips the dataset (record failure, nothing written), like attribution.
- [ ] **Step 4: Run** `/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python -m pytest pipelines/tests -q`. Expected: all PASS.
- [ ] **Step 5: Commit.**

### Task 6: Django read API

**Files:**
- Create: `backend/analyzer/analyzer_utils/fund_finder.py`
- Modify: `backend/analyzer/views.py` (views `get_fund_finder`, `get_funds_holding`, sharing a `_fund_response` wrapper like `_earnings_response`)
- Modify: `backend/analyzer/urls.py` (`path('fund-finder/', …, name='fund_finder')`, `path('funds-holding/<str:symbol>/', …, name='funds_holding')`)
- Test: `backend/analyzer/tests.py` (new `FundFinderTests`, S3 reads mocked by patching `fund_finder._read_parquet`)

**Interfaces:**
- Produces:
  - `find_funds(include: list[str], exclude: list[str], listed: str, limit: int = 100) -> dict` → `{"listed", "include", "exclude", "unknown": [symbols], "fetched": "YYYY-MM-DD", "funds": [{"symbol", "name", "exchange", "currency", "combined", "weights": {pick: {"weight", "via": [symbols]}}, "mer", "aum", "fetched", "also": [symbols]}]}`
  - `FundsUnavailable(Exception)` for S3 errors (502 in the view).
  - `bucket_of` duplicated here (same md5 rule); the test pins the same literal as Task 2.
  - Redis keys: `funds:meta:v1` (funds + isin_map), `funds:bucket:{nn}:v1`, `funds:query:{sha1 of normalised query}:v1`; TTL 6 hours.
- API: `GET /api/fund-finder/?include=RY.TO,TD.TO&exclude=SHOP.TO&listed=ca|us|both` and `GET /api/funds-holding/<symbol>/?listed=ca|us|both` (top 10).

- [ ] **Step 1: Write failing tests** (small in-memory frames for funds, isin_map and two buckets):
  - `test_ranking_is_pure_combined_weight`: fund A RY 8%; fund B RY/TD/SHOP 2% each; picks RY, TD, SHOP → order `[A, B]`, `combined` 8.0 and 6.0.
  - `test_pick_us_listing_finds_tsx_holders`: include `RY` → funds holding company `CA7800871021` (stored under RY.TO) are returned; same for `TSM` against a fund holding `2330.TW`.
  - `test_exclude_via_underlying`: a fund with a SHOP row whose `via` is `XIC.TO` is dropped when SHOP is excluded.
  - `test_listed_filter`: `ca` returns only `region == "ca"`; `both` returns all.
  - `test_collapse_same_market_only`: `ZWC.TO`/`ZWC2.TO` (same issuer, weights equal within 0.01) collapse to the larger AUM with `also == ["ZWC2.TO"]`; `XUS.TO`/`IVV` with equal weights stay separate under `both`; two funds with equal weights but `issuer` None on either are not collapsed (issuer comes from `etf/info`, full runs only).
  - `test_ties_by_aum`, `test_limit_100`.
  - `test_unknown_and_messy_symbols`: `include=" ry.to ,ZZZZ"` → picks `["RY.TO"]`, `unknown == ["ZZZZ"]`, 200.
  - `test_bad_queries`: no `listed` → 400 "listed is required (ca, us or both)"; `listed=eu` → 400; 11 includes → 400 "at most 10 stocks to include"; 11 excludes → 400; same symbol in both → 400 "RY.TO is in both include and exclude"; no include → 400.
  - `test_s3_error_is_502`.
  - `test_funds_holding_shortcut`: top 10.
- [ ] **Step 2: Run** `cd backend && /home/franc/projects/ai_agents/ai_tooling/.venv/bin/python manage.py test analyzer.tests.FundFinderTests` (env loaded as in the "Testing" note at the end). Expected: FAIL.
- [ ] **Step 3: Implement.** Symbol normalisation: strip, upper-case, validate with the `_SYMBOL_RE` pattern from `earnings_hub.py`. Read with `data_getter.fs.open("s3://thetradingfloor/fund_data/…")` + `pd.read_parquet`. Resolve picks through `isin_map` to company ids, load only the buckets needed, apply exclude, then `listed`, then collapse, then sort (`combined` desc, `aum` desc), then limit. Per pick, `via` lists the distinct non-empty `via` values.
- [ ] **Step 4: Run** the tests. Expected: PASS. Then the whole analyzer app: `manage.py test analyzer`. Expected: PASS.
- [ ] **Step 5: Commit.**

### Task 7: Frontend page and stock-page link

**Files:**
- Create: `src/utils/fundFinder/query.mjs`, `src/utils/fundFinder/query.test.mjs`
- Create: `src/hooks/useFundFinder.js`
- Create: `src/componentsLegacy/FundFinder/FundFinderForm.js`, `src/componentsLegacy/FundFinder/FundResultsTable.js`
- Create: `src/pages/fund-finder.js`
- Modify: `src/utils/stockApi.js` (`fetchFundFinder(query)`, `fetchFundsHolding(symbol, listed)`)
- Modify: `src/componentsLegacy/Comparison/TickerPicker.js` (optional `max` prop, default `MAX_SYMBOLS`; no behaviour change for existing callers)
- Modify: `src/pages/stock-data/[ticker].js` (a "Funds that hold this" link to `/fund-finder?include=<symbol>`, near `AnalystView`)
- Modify: `src/data/menu.json` (a "Fund Finder" entry next to "/factor-performance")
- Modify: `/home/franc/projects/ai_agents/ai_tooling-worktrees/fund-finder/.github/workflows/fintank-deploy.yml` (add `node --test fintank/src/utils/fundFinder/query.test.mjs` after the existing `node --test` lines). Note: this is a workflow change; it does not deploy by itself.

**Interfaces:**
- Consumes: the Task 6 API.
- Produces: `parseQuery(urlQuery: object) -> {listed: "ca"|"us"|"both"|null, include: string[], exclude: string[]}`, `toQuery(state) -> object` (omits empty lists, never invents `listed`), `canSearch(state) -> boolean` (true only when `listed` is set and `include` is non-empty).

- [ ] **Step 1: Write failing node tests** in `query.test.mjs`: round-trip `?listed=ca&include=RY.TO,TD.TO&exclude=SHOP.TO`; `parseQuery({include: "ry.to"})` gives `listed null`, `include ["RY.TO"]`; `canSearch` false without `listed`; duplicates removed; more than 10 truncated to 10.
- [ ] **Step 2: Run** `node --test src/utils/fundFinder/query.test.mjs`. Expected: FAIL.
- [ ] **Step 3: Implement** `query.mjs`, then the hook (SWR key `null` until `canSearch`; options as `useEarningsNotes`: no focus refetch), the form (listing dropdown with a disabled "Choose…" first option and Canada / United States / Both; two `TickerPicker`s with `max={10}`), the table (columns and copy as in the spec's sketch; per-pick weight cells show "via X" under the number when `via` is non-empty; fund symbol links to `/etf-data/<symbol>`; "also available as" under the name), and the page (state in the URL with `router.replace`, shallow). Copy strings exactly as in Global Constraints.
- [ ] **Step 4: Run** `node --test src/utils/fundFinder/query.test.mjs` (PASS) and `npm run lint` (no new errors). Do **not** run `next build` in the main folder; if a build check is wanted, run it in this worktree only.
- [ ] **Step 5: Commit.**

### Task 8: Owner-gated measurement, thresholds and docs

**Files:**
- Modify: `backend/pipelines/thresholds.py` (`FUND_MIN_FUNDS` = 90% of the measured count, rounded down to the nearest 100)
- Modify: `backend/pipelines/README.md` (new section "Fund finder": what the stages do, the WARN-only switch, what each check means, how to read the dropped-names list)
- Modify: `docs/BACKEND_BREAKDOWN.md` (one row for `analyzer_utils/fund_finder.py`)

- [ ] **Step 1: Ask the owner** for a go-ahead to spend FMP calls (no extra cost; about 4 `profile-bulk` parts plus ~3,400 holdings calls, roughly 1 GB of the 170 GB monthly allowance). Without it, stop here and report.
- [ ] **Step 2: With the go-ahead, run locally** (from `backend/`, keys from `backend/.env`): `/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python -m pipelines run --mode lean --dry-run --limit 5` and confirm `fetch_fund_holdings` and `build_fund_finder` appear with no exception. Then a fund-only measurement: call `StockDataPipeline(...).fetch_fund_holdings()` and `build_fund_finder()` from a short script in the session scratchpad (not committed) and record: fund count, `dropped_leveraged` names (give the owner the full list to look over), ADRs linked/unlinked, total bytes, run time, cross-check numbers, and whether any fund of funds came back unexpanded.
- [ ] **Step 3: Compare one live `etf/info` and one `etf/asset-exposure` response** with the hand-written fixtures from Task 1; fix field names and the code if they differ (re-run the pipeline tests).
- [ ] **Step 4: Set `FUND_MIN_FUNDS`**, write the README section and the BACKEND_BREAKDOWN row, run all tests (pipeline, infra, Django, node).
- [ ] **Step 5: Commit**, then report the measurements to the owner. The owner pushes, opens the PR, merges (which deploys the site; the pipeline image picks the stages up on the next CDK deploy, which the owner runs with every flag: `cdk deploy --profile fintank -c alert_email=francoiskieran89@gmail.com -c news_schedule=on -c weekly_schedule=on -c earnings_schedule=on`).

---

**Testing note (Django):** the worktree has no `backend/.env`. Load the main folder's env without printing it, as done on 2026-11-22:

```bash
cd /home/franc/projects/ai_agents/ai_tooling-worktrees/fund-finder/fintank/backend
DJANGO_SKIP_DOTENV=1 /home/franc/projects/ai_agents/ai_tooling/.venv/bin/python -c "
import os,sys
from dotenv import dotenv_values
for k,v in dotenv_values('/home/franc/projects/ai_agents/ai_tooling/fintank/backend/.env').items():
    os.environ.setdefault(k, v or '')
os.environ['DEBUG']='True'
sys.argv=['manage.py','test','--noinput','analyzer']
import runpy; runpy.run_path('manage.py', run_name='__main__')
"
```

Known local-only failure: `fintank_backend.test_auth_throttling.AllauthClientAddressTests.test_allauth_uses_the_last_proxy_hop` (fails on `main` too; passes in CI).
