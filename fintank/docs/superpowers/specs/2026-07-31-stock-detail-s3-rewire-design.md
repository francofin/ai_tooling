# Stock Detail Page — S3 Data Rewire

**Date:** 2026-07-31
**Status:** Approved

## Summary

Rebuild the data loading on `src/pages/stock-data/[ticker].js` around the S3-backed Django endpoints that already implement `backend/class_files/get_stock_data.ipynb`. Split the 580-line page into focused components, and delete the sections whose backends no longer exist.

## Context

The page 500s on every request. `getServerSideProps` calls five endpoints, none of which exist in the Django backend:

| Frontend call | Status |
|---|---|
| `/stock-data/{ticker}` | no route — unguarded, kills the page |
| `/getdailydata/{ticker}` | no route — unguarded, kills the page |
| `/getpeerlist/{ticker}` | no route — swallowed by `catch` |
| `/getkeymetrics/{ticker}` | no route — swallowed by `catch` |
| `/getpricetargets/{ticker}` | no route — swallowed by `catch` |

The watchlist calls in `src/context/authContext.js` (`addtowatchlist`, `deletefromwatchlist`, `stockonwatchlist/<t>/verify`) have no Django routes either.

Meanwhile `analyzer/urls.py` and `analyzer/analyzer_utils/CorePerformanceTools.py` already mirror the notebook's `GetStockData` class, with gzip+Redis caching layered on:

| Notebook method | Endpoint | Payload |
|---|---|---|
| `get_long_profile` | `stock-profile/<symbol>/` | flat dict of the 14 `LONG_PROFILE_FIELDS` |
| `get_stock_prices` | `stock-prices/<symbol>/` | `{dates: [], series: {…20 columns}}` |
| (monthly variant) | `stock-prices-monthly/<symbol>/` | `{dates: [], series: {…}}` |
| `get_financial_statement` | `financial-statements/<symbol>/<universe>/<statement_type>/` | `{symbol, universe, statement_type, data: []}` |

No new data plumbing is needed for profile, prices, or statements. This is a frontend rewire plus one backend convenience endpoint.

### Measured payload sizes (AAPL)

| Data | Size |
|---|---|
| Profile | 2 KB |
| Daily prices | 22 KB |
| Income statement | 179 KB (163 rows) |
| All three statements | ~500 KB |

### Data quality findings

Every one of the 12,904 daily price parquets holds exactly 84 rows spanning **2025-12-22 → 2026-04-23** (verified: AAPL, MSFT, SHOP.TO, JPM). Consequences:

- `200_day_ma` and `120_day_ma` are entirely null for every symbol
- `50_day_ma` has 35 non-null points out of 84
- `stock-prices-monthly` returns 5 data points
- The data is three months stale, and no Celery beat task writes these files

The design accommodates this rather than waiting on it. See "Out of scope".

## Design

### 1. Backend — universe resolution

`financial-statements` requires a `universe` path param, but nothing maps a symbol to its universe. `long_profiles` has no universe column, and `exchange_short_name` cannot disambiguate — NASDAQ symbols span `sp500`, `nas`, `r2000`, and `rmicro`.

New module `backend/analyzer/analyzer_utils/universe_lookup.py`:

- **`build_symbol_universe_index()`** — iterates the 8 constituent lists via `data_getter.get_index_constituents()`, mapping each entry's `asset` field to the universes containing it (~10,231 symbols). Cached gzipped in Redis under `stock:universe_index:v1`, 24h TTL, matching the existing `CorePerformanceTools` cache pattern.
- **`resolve_universes(symbol)`** — returns candidate universes in priority order: `sp500 → nas → r2000 → rmicro → tsx → tsx_small_cap → msci_eafe → msci_sm`. Returns a list, not a single value, because symbols legitimately appear in several (AAPL is in both `sp500` and `nasdaq`). Translates the constituent-map key `'nasdaq'` to the universe key `'nas'` that the statements path expects.

`get_financial_statements(symbol, universe, statement_type)` gains an optional `universe`. When omitted, it walks the candidate list and returns the first parquet actually containing the symbol, so a symbol whose index membership doesn't match its statement file still resolves. Raises `KeyError` only when no candidate contains it.

New route `financial-statements/<symbol>/<statement_type>/` alongside the existing explicit-universe route, which is unchanged.

### 2. Frontend data layer

New `src/lib/stockApi.js` — one function per endpoint, each returning parsed data or throwing a typed error:

- `fetchProfile(symbol)`
- `fetchPrices(symbol)`
- `fetchStatements(symbol, statementType)`
- `fetchSectorNews(sector)`

The page never constructs a URL. This replaces five inline `axios.get` calls with duplicated try/catch blocks.

`getServerSideProps` fetches profile and prices with `Promise.all` (~25 KB combined) so the page renders server-side with charts ready and stays indexable. A 404 on the profile returns `notFound: true`, rendering Next's 404 page instead of a 500.

Financial statements load client-side through a `useFinancialStatements` SWR hook when the section is opened, keeping ~500 KB out of the initial HTML.

### 3. Page structure

`[ticker].js` becomes a thin composition of components in `src/componentsLegacy/StockDetail/`:

| Component | Renders |
|---|---|
| `StockHeader` | name, symbol, exchange, sector, employees, description, data-as-of date |
| `PriceChart` | `adjClose` vs available moving averages |
| `MomentumCharts` | 30/60-day returns, up/down day ratio, return-to-risk |
| `StatementsSection` | tabbed income / balance / cash flow, lazy-loaded |
| `SectorNews` | sector-mapped topic feed |

Chart content mirrors notebook cells 10–11, which are already visually validated.

A shared `useAvailableSeries(series)` helper in `src/hooks/useAvailableSeries.js` filters out columns with no non-null values, so `200_day_ma` and `120_day_ma` self-hide today and appear automatically once the parquets are backfilled. No hardcoded exclusions.

The daily/monthly toggle is **deferred**, not built: `stock-prices-monthly` currently returns 5 data points, which is not chartable. It becomes worth adding once the price pipeline is fixed. Only `stock-prices` is wired in this pass.

`StockHeader` renders the last date present in the price series, making stale data visible rather than silent.

### 4. Sector-mapped news

`news/get_articles/<item>/` is topic-based, not ticker-based: `GetNewsArticles.file_names` is a fixed dict of categories, and an unknown key raises `KeyError` → 404. Passing a ticker does not work.

`SectorNews` maps the profile's `sector` to a news category (Technology→`tech`, Healthcare→`pharmaceuticals`, Financial Services→`financials`, Energy→`energy`, Basic Materials→`basic_materials`, Industrials→`industrials`, Utilities→`utilities`, Real Estate→`real_estate`, Communication Services→`communications`, Consumer Cyclical/Defensive→`consumer_trends`). Unmapped sectors fall back to `stock`. The section is labelled as sector news, not company news.

This keeps `NEXT_PUBLIC_FMP_API` out of the browser.

### 5. Deletions

| Removed | Reason |
|---|---|
| 12 `useBarChart` peer comparison charts | `getpeerlist` endpoint gone |
| `MetricsTable` usage | `getkeymetrics` endpoint gone |
| Price targets section | `getpricetargets` endpoint gone |
| `useStockData`, `useStockArticles` hooks | call FMP from the browser, exposing `NEXT_PUBLIC_FMP_API` |
| Watchlist button | its three Django routes do not exist |

`MetricsTable` and the hooks are only unwired from this page; other pages using them are untouched.

### 6. Error handling

Each section degrades independently. A failed statements or news fetch renders an inline message; only a missing profile is fatal, and that produces a 404 rather than a 500.

## Testing

The repo has no frontend test harness — no jest/vitest config, no test script in `package.json`. Building one is separate work.

- **Backend:** Django tests for `resolve_universes` (known symbol, multi-universe symbol, unknown symbol) and for statements resolution with `universe` omitted.
- **Frontend:** manual verification under `make dev` against tickers spanning universes (AAPL/`sp500`, SHOP.TO/`tsx`, an `msci_eafe` name), plus a nonexistent ticker for the 404 path.

## Out of scope

Flagged, not addressed here:

1. **The price pipeline.** Whatever writes `stock_data/stock_prices/daily/` produced 84-row files and last ran in April 2026. It is not among the Celery beat tasks. This is why the page has little to chart.
2. **Hardcoded AWS credentials.** `backend/class_files/get_stock_data.ipynb` cell 1 contains a live AWS access key and secret in plaintext. They should be rotated and read from `settings` as the rest of the backend does.
3. **Watchlist endpoints.** Rebuilding them is its own piece of work.
4. **Peer comparison, key metrics, price targets.** To be added back as their data sources land.
