# FMP stable migration: branch 1, the live site — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** remove every `api/v3` call from the live site's code paths (homepage cards and charts, the index page constituent quotes, and backtester prices) by switching them to FMP `stable`, with the payloads the frontend reads unchanged.

**Architecture:** a new module `backend/utils/fmp_stable.py` owns every `stable` URL and the field mapping back to the v3 shapes. `CorePerformanceTools`, `index_tools` and `backtester/engine/prices.py` call it instead of building v3 URLs. Tests patch `utils.fmp_stable.requests.get` and never touch the network.

**Tech Stack:** Django 5 / DRF, requests, pandas, Django `SimpleTestCase` + `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-11-19-fmp-stable-migration-design.md` (the Branch 1 section).

## Global Constraints

- No `financialmodelingprep.com/api/v3` or `api/v4` string may remain in `analyzer/analyzer_utils/CorePerformanceTools.py`, `analyzer/analyzer_utils/index_tools.py` or `backtester/engine/prices.py`.
- Base URL: `https://financialmodelingprep.com/stable/`. The key comes from `django.conf.settings.FMP_API` and is passed as the `apikey` query param, never interpolated into a URL string that gets logged or printed.
- Error output never includes exception text, because URLs carry the key. Print or log `type(error).__name__` only. This is the existing pattern; `analyzer/test_error_disclosure.py` enforces it.
- The v3 field name `changesPercentage` must stay in every quote payload. `stable` calls it `changePercentage`; write both.
- Tests never call FMP. They patch `utils.fmp_stable.requests.get`.
- Redis cache keys and payload shapes stay the same, so a deploy needs no cache flush.
- Run tests with `cd backend && ../../.venv/bin/python manage.py test <app> --noinput`. Never use `git stash`, `git commit -a`, or pattern-based kills.

## Review Focus

1. **Symbol strings with embedded whitespace:** the ETF and crypto lists in `CorePerformanceTools` contain `" \` line continuations, so their joined strings hold spaces and newlines. They must be split, stripped, and empties dropped before reaching `symbols=`. Otherwise FMP silently returns fewer rows. Owned by Task 2.
2. **One index failing in `get_index_charts`:** today one bad bucket fails all 15 charts. After this change a failed symbol is skipped, and the other 14 are still cached. Owned by Task 2.
3. **A constituent missing from the factor metrics:** it gets `pe = None` and `eps = None`, is excluded from valuations, and is still in movers. Owned by Task 3.
4. **`pe` ≤ 0 in the factor metrics:** `eps` stays `None` rather than a negative or infinite `price / pe`. Owned by Task 3.
5. **History order:** `stable` returns newest-first (probed). `format_index_prices` and the backtester expect oldest-first. Owned by Tasks 1 and 4.

---

### Task 1: `utils/fmp_stable.py`, the shared stable client

**Files:**
- Create: `backend/utils/fmp_stable.py`
- Test: `backend/analyzer/test_fmp_stable.py` (`utils` is not an installed app, so its tests live in `analyzer`)

**Interfaces:**
- Produces:
  - `STABLE_BASE = "https://financialmodelingprep.com/stable/"`
  - `split_symbols(raw: str | list[str]) -> list[str]`: splits on commas, strips whitespace, drops empties and keeps order.
  - `batch_quotes(symbols: list[str], *, timeout: int = 15) -> list[dict]`: GET `batch-quote` with `symbols=",".join(symbols)`, `raise_for_status()`, and every row passed through `to_v3_quote`.
  - `to_v3_quote(row: dict) -> dict`: a copy of `row` with `changesPercentage = row.get("changePercentage")` added. All `stable` keys are kept.
  - `index_history(symbol: str, *, timeout: int = 15) -> list[dict]`: GET `historical-price-eod/full?symbol=`. Returns the rows **oldest-first**, each with `adjClose = close` added when `adjClose` is absent.
  - `adjusted_history(symbol: str, *, timeout: int = 20) -> list[dict]`: GET `historical-price-eod/dividend-adjusted?symbol=`. Returns the rows oldest-first (they already carry `adjClose`).
  - Each function raises `requests.HTTPError` on a non-2xx response, and `ValueError` when the body isn't a JSON list.

- [ ] **Step 1: Write the failing tests** (`SimpleTestCase`; patch `utils.fmp_stable.requests.get` with a fake response whose `.json()` returns the fixture):
  - `test_split_symbols_strips_whitespace_and_empties`: `split_symbols("A, B,\n   C,,") == ["A", "B", "C"]`.
  - `test_batch_quotes_adds_v3_change_name`: fixture `[{"symbol": "^GSPC", "changePercentage": 0.5, "price": 1.0}]`. The result's row has `changesPercentage == 0.5` and `changePercentage == 0.5`.
  - `test_batch_quotes_sends_symbols_and_key_as_params`: assert `requests.get` was called with the URL `STABLE_BASE + "batch-quote"` and `params` holding `symbols == "A,B"` and an `apikey`. The URL string doesn't contain the key.
  - `test_index_history_is_oldest_first_with_adjclose`: fixture newest-first `[{"date": "2026-11-19", "close": 2.0, "volume": 1}, {"date": "2026-11-18", "close": 1.0, "volume": 1}]`. The result's dates are `["2026-11-18", "2026-11-19"]`, and `adjClose` equals `close` in each row.
  - `test_adjusted_history_is_oldest_first`: same shape, with `adjClose` already present and unchanged.
  - `test_http_error_propagates`: the fake's `raise_for_status` raises `requests.HTTPError`, and `batch_quotes` raises it.
  - `test_non_list_body_raises_value_error`: `.json()` returns `{"Error Message": "x"}`, and `batch_quotes` raises `ValueError`.
- [ ] **Step 2: Run the tests and see them fail.** `../../.venv/bin/python manage.py test analyzer.test_fmp_stable --noinput`: ImportError.
- [ ] **Step 3: Implement** the module per the Interfaces block. Sort history by `date` string ascending; ISO dates sort correctly as strings.
- [ ] **Step 4: Run the tests and see them pass.**
- [ ] **Step 5: Commit** `git add backend/utils/fmp_stable.py backend/analyzer/test_fmp_stable.py`, message `feat(fintank): stable FMP client with v3-shape mapping`.

### Task 2: the homepage cards and charts in `CorePerformanceTools`

**Files:**
- Modify: `backend/analyzer/analyzer_utils/CorePerformanceTools.py`: `get_index_performance` (~L76), `get_etf_performance` (~L97), `get_crypto_performance` (~L120), `get_index_charts` (~L605)
- Test: `backend/analyzer/test_fmp_stable_homepage.py`

**Interfaces:**
- Consumes: `split_symbols`, `batch_quotes`, `index_history` from Task 1.
- Produces: unchanged function names, return values and cache keys (`home_index_cache`, `home_etf_cache`, `home_crypto_cache`, `home:index_chart:{key}:v1`).

- [ ] **Step 1: Write the failing tests** (patch `utils.fmp_stable.requests.get`, use `LOCMEM` cache via `override_settings`, and patch `CorePerformanceTools.is_market_open_now`):
  - `test_index_performance_is_one_batch_call_with_v3_field`: `get_index_performance()` makes exactly **one** GET. `params["symbols"]` holds `^GSPC` and `TX60.TS` and no whitespace. `result["data"][0]` has `changesPercentage`.
  - `test_etf_and_crypto_symbol_lists_have_no_whitespace`: for `get_etf_performance` and `get_crypto_performance`, `params["symbols"]` contains no `" "` and no `"\n"`, and contains `"EWC"` / `"BTCUSD"` respectively.
  - `test_index_charts_cache_each_index_oldest_first`: the fake returns newest-first rows for every symbol. After `get_index_charts()`, the cached `home:index_chart:sp500:v1` decompresses to `{"data": [...], "name": "S&P 500"}` with oldest-first dates and `adjClose` present. Exactly 15 GETs.
  - `test_index_charts_skip_a_failing_symbol`: the fake raises `requests.HTTPError` only for `^N225`. `home:index_chart:nik:v1` isn't set, `home:index_chart:sp500:v1` is set, and the function returns `"ok"`. The printed or logged output contains `HTTPError` and not the URL.
- [ ] **Step 2: Run the tests and see them fail.**
- [ ] **Step 3: Implement.**
  - The three quote functions call `batch_quotes(split_symbols(<existing string>))`, and `context["data"]` is that list.
  - `get_index_charts` keeps its 15 `(cache_key, symbol, display name)` triples as one module-level tuple in the existing order:
    - sp500 ^GSPC, nas ^IXIC, tsx ^GSPTSE, tsx_60 TX60.TS, rus_2000 ^RUT;
    - rus_1000 ^RUI, dj ^DJI, nik ^N225, hsi ^HSI, nsei ^NSEI;
    - ftse ^FTSE, short_term ^IRX, ten_year ^TNX, thirty_year ^TYX, vix ^VIX.
  - For each triple, it fetches `index_history(symbol)` (already oldest-first, so the old `[::-1]` goes), `compress_series({'data': rows, 'name': name})`, and sets the cache. A `requests.RequestException` or `ValueError` for one symbol is printed as `f"index_charts: {key} failed: {type(e).__name__}"` and skipped.
  - Remove the three v3 URLs.
- [ ] **Step 4: Run** `manage.py test analyzer --noinput`. The new tests and all existing analyzer tests pass.
- [ ] **Step 5: Commit** both files: `fix(fintank): homepage index, ETF, crypto and charts use FMP stable`.

### Task 3: the index page constituent quotes in `index_tools.get_index_quotes`

**Files:**
- Modify: `backend/analyzer/analyzer_utils/index_tools.py` (`get_index_quotes` ~L495, its docstring, and the `fmp_api` import if unused afterwards)
- Modify: `backend/analyzer/tests.py` (`IndexQuotesTests`, ~L300) and `backend/analyzer/test_error_disclosure.py` (~L140) to patch the new seams

**Interfaces:**
- Consumes: `batch_quotes` from Task 1; `data_getter.load_factor_metrics(config['risk_key'])` (exists: one row per constituent with `symbol`, `pe`).
- Produces: the same payload keys. Each record holds exactly `QUOTE_FIELDS = ['symbol', 'name', 'pe', 'eps', 'changesPercentage', 'price', 'marketCap']`.

Behaviour:
- Quotes come from `batch_quotes(batch_symbols)`, using the existing `_batch_symbols` batches split back into lists. A failed batch is printed with its type name and skipped, as today.
- `pe` comes from the factor metrics frame by symbol. Load it with a cached helper `_pe_by_symbol(risk_key) -> dict[str, float]`, using the cache key `index:pe_map:{risk_key}:v1` and `CACHE_TTL`. Non-finite values are dropped.
- `eps = round(price / pe, 4)` only when `pe > 0` and `price` is a number. Otherwise `None`.
- If `load_factor_metrics` raises, log the type name, use an empty map (every `pe` is `None`), and still return the movers.

- [ ] **Step 1: Update and add the tests.**
  - `IndexQuotesTests._run` patches `utils.fmp_stable.requests.get` to return the quotes **without** `pe`/`eps` (use `changePercentage`, the stable name). It also patches `index_tools.data_getter.load_factor_metrics` to return `pd.DataFrame({'symbol': ['AAA', 'BBB', 'DDD'], 'pe': [30.0, 10.0, -500.0]})`.
  - The existing tests must still pass on that input: movers order, valuations `['BBB', 'AAA']`, the field set, and empty quotes raising `KeyError`.
  - Add `test_eps_is_price_over_positive_pe`: BBB has `eps == 5.0`, and DDD and CCC have `eps is None`.
  - Add `test_missing_factor_metrics_still_returns_movers`: `load_factor_metrics` raises `FileNotFoundError`, `top_performers` is non-empty, and `valuations == []`.
  - In `test_error_disclosure.py`, the index-quotes test patches `utils.fmp_stable.requests.get` with `side_effect=requests.ConnectionError(LEAKY_MESSAGE)` and patches `load_factor_metrics` to return an empty frame. Same assertions as before.
- [ ] **Step 2: Run the tests and see them fail.**
- [ ] **Step 3: Implement** per the Behaviour list. Rewrite the docstring: quotes come from `stable` `batch-quote`, and `pe` from the factor metrics because `stable` quotes carry no `pe`/`eps`.
- [ ] **Step 4: Run** `manage.py test analyzer --noinput`. Everything passes.
- [ ] **Step 5: Commit** the modified files: `fix(fintank): index constituent quotes use FMP stable, P/E from factor metrics`.

### Task 4: backtester prices

**Files:**
- Modify: `backend/backtester/engine/prices.py` (`_fetch_from_fmp`, ~L89)
- Test: `backend/backtester/tests/test_prices.py` (add tests)

**Interfaces:**
- Consumes: `adjusted_history` from Task 1.
- Produces: `_fetch_from_fmp(symbol) -> pd.Series`, unchanged signature: an `adjClose` series indexed by date, ascending.

Behaviour:
- `rows = adjusted_history(symbol)`. Empty rows raise `FileNotFoundError(f"FMP returned no history for {symbol}")`, as today. `_series_from_frame(pd.DataFrame(rows))`.
- **The basis changes:** the backtester now gets dividend-adjusted closes, the same basis as the S3 parquets it prefers (they call the column `adjClose`). The old v3 `serietype=line` returned raw closes, which understated total return for dividend payers. Mention this in the commit body.

- [ ] **Step 1: Write the failing tests** (patch `utils.fmp_stable.requests.get`):
  - `test_fetch_from_fmp_uses_dividend_adjusted_series`: the fake returns newest-first `[{"symbol": "SPY", "date": "2026-11-19", "adjClose": 2.0, ...}, {"date": "2026-11-18", "adjClose": 1.0, ...}]`. The returned series is ascending, `[1.0, 2.0]`. The called URL ends with `historical-price-eod/dividend-adjusted`.
  - `test_fetch_from_fmp_empty_raises_file_not_found`.
- [ ] **Step 2: Run** `manage.py test backtester --noinput` and see them fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `manage.py test backtester analyzer --noinput`. Everything passes (except the known `test_allauth_uses_the_last_proxy_hop`, which fails locally only, if it's in scope).
- [ ] **Step 5: Commit** `fix(fintank): backtester FMP fallback uses stable dividend-adjusted prices`.
- [ ] **Step 6: Verify the Global Constraint.** `grep -n "api/v3\|api/v4" backend/analyzer/analyzer_utils/CorePerformanceTools.py backend/analyzer/analyzer_utils/index_tools.py backend/backtester/engine/prices.py` prints nothing.
