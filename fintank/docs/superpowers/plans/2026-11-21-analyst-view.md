# Analyst View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an analyst panel to `stock-data/[ticker]`. It shows forward estimates, ratings and price targets. For TSX stocks, ratings and targets fall back to the US listing, with a source label and a CAD conversion.

**Architecture:** The data is fetched live from FMP `stable` when a stock page is opened, then cached in Redis. This is the same pattern as `stock-quote`. A pure shaping module chooses the source symbol, drops stale targets and converts USD to CAD. A thin cache layer and Django views sit on top of it. On the frontend, an SWR hook feeds a new `AnalystView` component. The quarterly estimates are fetched only when the toggle is opened.

**Tech Stack:** Django REST Framework, django-redis (LocMem in tests), `requests`, Next.js Pages Router, swr@1, react-bootstrap, `node --test` for the frontend's pure helpers.

**Spec:** `docs/superpowers/specs/2026-11-21-analyst-view-design.md`

**Not needed for this plan:** Claude API credits. Those are only for the earnings notes (feature 1). Franc will add them after the lean run is approved and the earnings-note infrastructure is built.

## Global Constraints

- Use stable endpoints only, through `backend/utils/fmp_stable.py`. Never write an `api/v3` URL.
- Cache lifetimes:
  - The analyst payload and the quarterly estimates live **24 h** (`86400`).
  - The US-listing lookup and the reporting currency live **30 days** (`2592000`).
  - The USDCAD rate lives **24 h** and is shared by every stock.
- **Stale-target rule:** hide the price target when `price-target-summary.lastYearCount < 3`. A missing summary counts as 0.
- Annual estimates show the **next 3** fiscal periods. Quarterly estimates show the **next 4**. "Next" means a `date` on or after today. Sort oldest first.
- Fields shown: revenue, EPS and EBITDA, each with low, avg and high.
- **Fallback label copy:** `Target $178 USD (≈ $255 CAD) · from SHOP's NYSE listing`. Exchange short names: `New York Stock Exchange` → `NYSE`. Any name starting with `NASDAQ` or `Nasdaq` → `Nasdaq`.
- **No data at all** (no estimates, no ratings, no target) returns a 404, and the frontend renders nothing. On a 404 or 502, the panel is hidden.
- Error contract, same as `get_stock_quote`: `KeyError` → 404, `AnalystUnavailable` → 502 through `client_safe_message`.
- Work on a feature branch in a git worktree. **Do not push, merge or deploy:** pushing to `main` deploys, and the `lean-20261121-1529` run is waiting for approval.
- Stage exact paths. Never `git commit -a`, because the monorepo root holds Franc's own uncommitted files.
- Never start the dev servers (Django, Next, Celery). Franc starts them himself. Run `next build` only in a throwaway worktree.

## Review Focus

1. **TSX-only stock** (ATD.TO; no US variant). Show estimates; `ratings` and `target` are `null`. Owned by Task 2.
2. **FMP returns past and far-future periods, newest first** (TD.TO's first row was 2029). The shaped output must be the next N periods in ascending order. Owned by Task 2.
3. **Symbol case and whitespace** (`" ry.to "`). Normalize to `RY.TO` before building cache keys and calling FMP. Owned by Task 3.
4. **Null fields from FMP** (for example `ebitdaLow: null`). Keep them as `null` in the payload, and render them as `—` rather than `$NaN`. Owned by Tasks 2 and 5.
5. **USDCAD fetch fails** while a US-listing target exists. Still show the USD target; `target.cad` is `null`, and the label leaves out the `(≈ … CAD)` part. Owned by Tasks 2, 3 and 5.

---

### Task 1: FMP client functions

**Files:**
- Modify: `backend/utils/fmp_stable.py` (append)
- Test: `backend/analyzer/test_fmp_stable.py` (append to `FmpStableTests`; reuse `fake_response`)

**Interfaces:**
- Produces:
  - `analyst_estimates(symbol: str, period: str, *, limit: int, timeout=15) -> list[dict]`. `period` is `"annual"` or `"quarter"`.
  - `grades_consensus(symbol: str, *, timeout=15) -> dict | None`
  - `price_target_consensus(symbol: str, *, timeout=15) -> dict | None`
  - `price_target_summary(symbol: str, *, timeout=15) -> dict | None`
  - `exchange_variants(symbol: str, *, timeout=15) -> list[dict]`
  - `reported_currency(symbol: str, *, timeout=15) -> str | None`. Reads `income-statement?limit=1` and returns `reportedCurrency`.
  - `fx_rate(pair: str = "USDCAD", *, timeout=15) -> float | None`. Reads `quote?symbol=`.
- The single-row functions return the first row, or `None` for `[]`. All of them use `_get_list`, so HTTP errors raise `requests.HTTPError`.

- [ ] **Step 1: Write failing tests**
  - `test_analyst_estimates_sends_period_and_limit`: the URL is `STABLE_BASE + "analyst-estimates"`, and the params include `symbol`, `period="quarter"` and `limit=12`.
  - `test_single_row_helpers_return_none_on_empty`: `grades_consensus("ATD.TO")` returns `None` when the body is `[]`.
  - `test_price_target_summary_returns_first_row`
  - `test_fx_rate_returns_float_price`: the body `[{"symbol":"USDCAD","price":1.434}]` gives `1.434`.
  - `test_reported_currency_reads_income_statement`: the URL ends `income-statement`, `limit=1`, and the result is `"USD"`.
- [ ] **Step 2: Run them and confirm they fail.** Run `cd backend && python manage.py test analyzer.test_fmp_stable -v 2`. Expected: ImportError.
- [ ] **Step 3: Implement the seven functions** in `utils/fmp_stable.py`.
- [ ] **Step 4: Run them and confirm they pass.** Same command. Expected: OK.
- [ ] **Step 5: Commit**
```bash
git add backend/utils/fmp_stable.py backend/analyzer/test_fmp_stable.py
git commit -m "feat(analyst-view): stable FMP client for estimates, grades, targets, variants, fx"
```

### Task 2: Pure shaping module

**Files:**
- Create: `backend/analyzer/analyzer_utils/analyst_view.py`
- Test: `backend/analyzer/test_analyst_view.py`

**Interfaces:**
- Consumes: nothing from FMP. The inputs are the raw rows from Task 1.
- Produces:
  - `US_EXCHANGES: dict[str, str]`, the full exchange name mapped to its short label (`NYSE` or `Nasdaq`).
  - `MIN_TARGET_COUNT = 3`
  - `pick_us_listing(symbol: str, variants: list[dict]) -> dict | None`. For a symbol ending in `.TO`, it returns `{"symbol": "CNI", "exchange": "NYSE"}` for the first variant whose `exchange` maps to a US label. Otherwise it returns `None`.
  - `shape_estimates(rows: list[dict], period: str, today: date) -> list[dict]`. It keeps rows dated on or after `today`, sorts them oldest first, and takes 3 (annual) or 4 (quarter). Each item is `{"date", "revenue": {"low","avg","high"}, "eps": {...}, "ebitda": {...}}`. The FMP keys are `revenueLow/Avg/High`, `epsLow/Avg/High` and `ebitdaLow/Avg/High`. A missing or `None` value stays `None`.
  - `shape_ratings(row: dict | None) -> dict | None`. It returns `{"strongBuy","buy","hold","sell","strongSell","consensus","total"}`, or `None` when the row is missing or `total == 0`.
  - `shape_target(consensus: dict | None, summary: dict | None, *, from_us: bool, usdcad: float | None) -> dict | None`. It returns `None` when `consensus` is `None` or `(summary or {}).get("lastYearCount", 0) < MIN_TARGET_COUNT`. Otherwise it returns `{"consensus","median","low","high","count_last_year","currency","cad"}`. When `from_us` is true, `currency` is `"USD"` and `cad` is `{"consensus","median","low","high"}` multiplied by `usdcad`, or `None` if `usdcad` is `None`. When `from_us` is false, `currency` is `None` (the stock's own trading currency) and `cad` is `None`.
  - `build_payload(symbol, *, estimates_annual, ratings, target, source, reporting_currency) -> dict`. It returns `{"symbol","estimates":{"annual":[...]},"ratings","target","source","reporting_currency"}`, where `source` is the `pick_us_listing` result or `None`. It raises `KeyError` when the annual estimates are empty and both `ratings` and `target` are `None`.

- [ ] **Step 1: Write failing tests** (`SimpleTestCase`, with `today=date(2026, 11, 21)`):
  - `test_pick_us_listing_maps_cnr_to_cni`: the variants `[{"symbol":"CNI","exchange":"New York Stock Exchange"},{"symbol":"CNR.TO","exchange":"Toronto Stock Exchange"}]` give `{"symbol":"CNI","exchange":"NYSE"}`.
  - `test_pick_us_listing_none_for_tsx_only`: only a TSX variant gives `None`. This covers Review Focus 1.
  - `test_pick_us_listing_none_for_us_symbol`: `"AAPL"` gives `None` whatever the variants are.
  - `test_shape_estimates_takes_next_three_ascending`: rows dated 2029, 2028, 2027, 2026-10-31 and 2025 (newest first) give `["2027…", "2028…", "2029…"]`, with 2026-10-31 dropped as past. This covers Review Focus 2.
  - `test_shape_estimates_quarter_takes_four`
  - `test_shape_estimates_keeps_none`: `ebitdaLow: None` gives `["ebitda"]["low"] is None`. This covers Review Focus 4.
  - `test_target_hidden_when_fewer_than_three_last_year`: RY's case, `lastYearCount = 1`, gives `None`.
  - `test_target_hidden_when_summary_missing`
  - `test_target_from_us_converts_to_cad`: a consensus of 178.25 with `usdcad = 1.434` gives `cad["consensus"] == approx 255.6`, and `currency == "USD"`.
  - `test_target_from_us_without_fx_keeps_usd`: `usdcad = None` gives a non-`None` target with `cad is None`. This covers Review Focus 5.
  - `test_build_payload_raises_keyerror_when_nothing`
  - `test_build_payload_tsx_only_keeps_estimates`: estimates present, ratings and target `None`, gives a payload with `source is None`.
- [ ] **Step 2: Run them and confirm they fail.** Run `cd backend && python manage.py test analyzer.test_analyst_view -v 2`. Expected: ImportError.
- [ ] **Step 3: Implement the functions above** in `analyzer_utils/analyst_view.py`. No Django, cache or network imports.
- [ ] **Step 4: Run them and confirm they pass.** Same command. Expected: OK.
- [ ] **Step 5: Commit**
```bash
git add backend/analyzer/analyzer_utils/analyst_view.py backend/analyzer/test_analyst_view.py
git commit -m "feat(analyst-view): pure shaping — US-listing pick, next-N estimates, stale-target rule, CAD conversion"
```

### Task 3: Cached getters

**Files:**
- Modify: `backend/analyzer/analyzer_utils/analyst_view.py` (add the cached layer below the pure functions)
- Test: `backend/analyzer/test_analyst_view.py` (new class, `@override_settings(CACHES=LOCMEM_CACHE)`; copy `LOCMEM_CACHE` from `analyzer/tests.py`)

**Interfaces:**
- Consumes: the Task 1 functions (patch them at `analyzer.analyzer_utils.analyst_view.<name>`) and the Task 2 functions.
- Produces:
  - `class AnalystUnavailable(Exception)`
  - `PAYLOAD_TTL = 86400`, `LISTING_TTL = 2592000`, `FX_TTL = 86400`
  - Cache keys:
    - `stock:analyst:{SYMBOL}:v1` for the annual payload
    - `stock:analyst:quarter:{SYMBOL}:v1`
    - `stock:analyst:listing:{SYMBOL}:v1` holding `{"source": ..., "reporting_currency": ...}`
    - `stock:analyst:missing:{SYMBOL}:v1`, cached for `PAYLOAD_TTL`, so a no-coverage stock costs one set of calls a day
    - `fx:usdcad:v1`
  - `get_analyst_view(symbol: str) -> dict`, the annual payload. Raises `KeyError` or `AnalystUnavailable`.
  - `get_quarterly_estimates(symbol: str) -> dict`, returning `{"symbol", "estimates": {"quarter": [...]}}`. Raises `KeyError` when the list is empty.
- Behavior:
  - Normalize with `symbol.strip().upper()`.
  - Ratings and targets are fetched for `source["symbol"]` when a US listing exists, and otherwise for the symbol itself. Estimates always use the symbol itself.
  - A `requests.RequestException` or `ValueError` from FMP raises `AnalystUnavailable`, and nothing is cached. The exception is the FX fetch: if it fails, use `usdcad = None` and still build the payload.

- [ ] **Step 1: Write failing tests**
  - `test_second_call_served_from_cache`: the FMP mocks are called once across two `get_analyst_view("RY.TO")` calls.
  - `test_symbol_is_normalized`: `" ry.to "` and `"RY.TO"` share one fetch. This covers Review Focus 3.
  - `test_interlisted_uses_us_symbol_for_grades_and_targets`: for `RY.TO` with variants including `RY` on the NYSE, `grades_consensus` is called with `"RY"`, and `analyst_estimates` is called with `"RY.TO"`.
  - `test_listing_lookup_cached_30_days`: the `cache.set` call for the listing key uses `timeout=LISTING_TTL`.
  - `test_fmp_error_raises_unavailable_and_caches_nothing`
  - `test_fx_failure_still_returns_usd_target`. This covers Review Focus 5.
  - `test_no_coverage_raises_keyerror_and_caches_missing`
  - `test_quarterly_fetched_separately`: `get_analyst_view` makes no `period="quarter"` call.
- [ ] **Step 2: Run them and confirm they fail.** Run `cd backend && python manage.py test analyzer.test_analyst_view -v 2`.
- [ ] **Step 3: Implement** `get_analyst_view`, `get_quarterly_estimates` and the private `_listing(symbol)` and `_usdcad()` helpers.
- [ ] **Step 4: Run them and confirm they pass.** Same command. Expected: OK.
- [ ] **Step 5: Commit**
```bash
git add backend/analyzer/analyzer_utils/analyst_view.py backend/analyzer/test_analyst_view.py
git commit -m "feat(analyst-view): Redis-cached getters (24h payload, 30d listing, shared daily fx)"
```

### Task 4: API endpoints

**Files:**
- Modify: `backend/analyzer/views.py`. Add two `@api_view(['GET'])` views next to `get_stock_quote`, with the same try/except shape.
- Modify: `backend/analyzer/urls.py`. Add:
  - `path('analyst-view/<str:symbol>/', views.get_analyst_view, name='analyst_view')`
  - `path('analyst-view/<str:symbol>/quarterly/', views.get_analyst_quarterly, name='analyst_quarterly')`
- Test: `backend/analyzer/test_analyst_view.py` (new class, using `django.test.Client` or DRF `APIClient`)

**Interfaces:**
- Consumes: `get_analyst_view`, `get_quarterly_estimates` and `AnalystUnavailable` from Task 3.
- Produces:
  - `GET /api/analyst-view/<symbol>/` returns 200 with the Task 2 payload, 404 `{"detail": "No analyst data for 'X'"}` or 502 `{"detail": ...}`.
  - `GET /api/analyst-view/<symbol>/quarterly/` follows the same contract.

- [ ] **Step 1: Write failing tests**: `test_view_200`, `test_view_404_on_keyerror`, `test_view_502_on_unavailable` (the body must not contain the FMP URL or `apikey`) and `test_quarterly_route_200`. Patch the getters at `analyzer.analyzer_utils.analyst_view`.
- [ ] **Step 2: Run them and confirm they fail.** Run `cd backend && python manage.py test analyzer.test_analyst_view -v 2`.
- [ ] **Step 3: Implement the views and routes.**
- [ ] **Step 4: Run all analyzer tests and confirm they pass.** Run `cd backend && python manage.py test analyzer -v 1`. Expected: OK, with no regressions.
- [ ] **Step 5: Commit**
```bash
git add backend/analyzer/views.py backend/analyzer/urls.py backend/analyzer/test_analyst_view.py
git commit -m "feat(analyst-view): /api/analyst-view/<symbol>/ and /quarterly/ endpoints"
```

### Task 5: Frontend panel

**Files:**
- Modify: `src/utils/stockApi.js`. Add `fetchAnalystView(symbol)` and `fetchAnalystQuarterly(symbol)` through `request()`.
- Create: `src/hooks/useAnalystView.js`. Add `useAnalystView(symbol)` and `useAnalystQuarterly(symbol, enabled)`, using SWR with `revalidateOnFocus: false`, no `refreshInterval`, and `shouldRetryOnError: (e) => e?.status !== 404`. A `null` key when `!enabled` makes the quarterly fetch lazy. Wrap them with `withIsLoading` like `useStockQuote`.
- Create: `src/utils/analystViewFormat.mjs` (pure helpers) and `src/utils/analystViewFormat.test.mjs`
- Create: `src/componentsLegacy/StockDetail/AnalystView.js`
- Modify: `src/pages/stock-data/[ticker].js`. Render `<AnalystView symbol={symbol} currency={profile.currency} />` directly after `<StatementsSection symbol={symbol} />`.

**Interfaces:**
- Consumes: the Task 4 endpoints and their payload shape (Task 2 `build_payload`).
- Produces, in `analystViewFormat.mjs`:
  - `targetLabel(target, source) -> string | null`. Gives `"Target $178 USD (≈ $255 CAD) · from SHOP's NYSE listing"`. Without `target.cad`, it gives `"Target $178 USD · from SHOP's NYSE listing"`. It returns `null` when `source` is `null`. Round to whole dollars.
  - `upsidePct(targetConsensus, price) -> number | null`. Gives `(t / p - 1) * 100`, or `null` when either input is missing or `price <= 0`.
  - `fmtRange({low, avg, high}, formatter) -> string`. Uses `EMPTY` (`'—'`) for null parts. Import `EMPTY` from `@utils/stockQuoteFormat` only if it resolves under `node --test`; otherwise use a local `'—'`.

- [ ] **Step 1: Write failing tests** in `analystViewFormat.test.mjs` (`node:test` plus `assert/strict`, header `// Run: node --test src/utils/analystViewFormat.test.mjs`):
  - `targetLabel` returns the exact copy from Global Constraints for `{consensus:178.25, cad:{consensus:255.61}}` with `{symbol:"SHOP", exchange:"NYSE"}`.
  - `targetLabel` without `cad` drops the CAD part. This covers Review Focus 5.
  - `targetLabel` with `source = null` gives `null`.
  - `upsidePct(225, 150)` gives `50`. `upsidePct(225, 0)` and `upsidePct(null, 150)` give `null`.
  - `fmtRange({low:null, avg:2, high:3}, String)` contains `'—'` and never `NaN`. This covers Review Focus 4.
- [ ] **Step 2: Run them and confirm they fail.** Run `node --test src/utils/analystViewFormat.test.mjs`. Expected: a module-not-found failure.
- [ ] **Step 3: Implement `analystViewFormat.mjs`, the API functions and the hooks.**
- [ ] **Step 4: Run them and confirm they pass.** Same command. Expected: all pass.
- [ ] **Step 5: Implement `AnalystView.js`.**
  - Bootstrap `text-block` section titled "Analyst view", matching the `StatementsSection` styling.
  - Return `null` while loading with no data, and on any error. This hides the panel on 404 and 502.
  - Estimates table: rows Revenue, EPS and EBITDA; columns are the periods; each cell shows `avg` with `low – high` beneath it. Add an Annual/Quarterly `ButtonGroup`; Quarterly turns on `useAnalystQuarterly`. Show a caption with `reporting_currency` when present.
  - Ratings bar: a stacked `ProgressBar` from strong buy to strong sell, with the consensus word and `total analysts`. Only when `ratings` is non-null.
  - Price target: consensus, median and low–high range, plus upside % using `useStockQuote(source?.symbol || symbol)`'s price. For a US-listing source, use the US listing's price for the upside, so both sides are in USD. Show `targetLabel` beneath. Only when `target` is non-null.
  - Footnote: "Consensus from analysts covering the stock, via Financial Modeling Prep."
- [ ] **Step 6: Lint.** Run `npm run lint` and `npx prettier --check src/componentsLegacy/StockDetail/AnalystView.js src/hooks/useAnalystView.js src/utils/analystViewFormat.mjs src/utils/stockApi.js "src/pages/stock-data/[ticker].js"`. Expected: no errors in the touched files.
- [ ] **Step 7: Commit**
```bash
git add src/utils/stockApi.js src/hooks/useAnalystView.js src/utils/analystViewFormat.mjs src/utils/analystViewFormat.test.mjs src/componentsLegacy/StockDetail/AnalystView.js "src/pages/stock-data/[ticker].js"
git commit -m "feat(analyst-view): stock page panel — estimates toggle, ratings bar, target with US-listing label"
```

### Task 6: Hand-off check (Franc runs the servers)

- [ ] **Step 1:** Ask Franc to start Django and Next himself. List the commands in full:
  - `cd backend && python manage.py runserver`
  - `npm run dev`
- [ ] **Step 2:** Once he confirms they're running, make one `curl` each against `http://localhost:8000/api/analyst-view/<SYM>/` for `AAPL`, `RY.TO`, `SHOP.TO` and `ATD.TO`, plus `/quarterly/` for `TD.TO`. Expected:
  - AAPL: full panel data.
  - RY.TO: `source.symbol == "RY"`, ratings present, `target` `null` (stale rule).
  - SHOP.TO: a target with `cad`.
  - ATD.TO: estimates only.
  - TD.TO: 4 quarters.

  That's 5 symbols, about 20 FMP calls in total.
- [ ] **Step 3:** Ask Franc to look at `http://localhost:8020/stock-data/SHOP.TO` and `/stock-data/ATD.TO`.
- [ ] **Step 4:** Use `superpowers:finishing-a-development-branch`. **Do not merge or push** until Franc approves the lean run and says go.
