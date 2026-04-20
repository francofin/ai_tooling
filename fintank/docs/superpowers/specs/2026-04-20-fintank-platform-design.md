# Fintank — Full Platform Specification

## Context

Fintank is an existing financial data platform built on Django + DRF (backend) and Next.js (frontend). A significant portion of the platform is already operational: market data ingestion via FMP and S3, Redis/gzip caching, Celery periodic tasks, sector/index dashboards, spread analysis, news categorization, watchlists, stock screener, and JWT-based authentication.

This document is the canonical platform specification — a full-vision reference that covers both what exists and what must be built. The goal is a comprehensive financial intelligence platform serving two user tiers (internal analysts and external clients), delivering proprietary quantitative analytics, real-time and scheduled data pipelines, and curated multi-source news aggregation.

The platform is explicitly designed as an **evolving product**: new analytics modules, data sources, and features will be added continuously as research matures. Monetisation via Stripe is a planned future milestone — certain premium analyses and features will be gated behind paid tiers.

---

## 1. Platform Overview

| Dimension | Decision |
|-----------|----------|
| Backend | Django + DRF, Celery (async computation), PostgreSQL + PostGIS |
| Frontend | Next.js (Pages Router for finance pages, App Router for Solana) |
| Analytics pattern | App-wide async serving: Celery workers pre-compute on schedule → S3 + Redis → all users see same cached result |
| Users | Two tiers: internal analysts (EMPLOYEE/ADMIN) + external clients (SUBSCRIBER) |
| Backtesting | Phased: signal backtesting V1, full strategy simulation V2 |
| News engine | Multi-source (FMP + secondary API), normalised schema, ticker/sector/theme linking |
| Storage | PostgreSQL (user + security data), Redis (24h cache), S3 (parquet + analytics outputs + news JSON) |

---

## 2. App-Wide Data Serving Model

A core architectural principle of the platform is that **Celery performs all data computation on behalf of the application, not on behalf of individual users.** No analytical computation is triggered by a user's page load. Instead:

1. Celery beat tasks run on fixed schedules (market-hours-aware via existing `is_market_open_now()`)
2. Workers fetch, compute, and store results to S3 (durable) and Redis (fast cache)
3. Django API endpoints serve the pre-computed result from cache — all users hitting the same endpoint receive identical data regardless of when they load the page
4. If the cache is cold (first run or TTL expired), the endpoint returns the most recent S3 result rather than triggering a live computation

**Consequences of this model:**
- Data freshness is determined by Celery schedule, not by user request timing (e.g. index performance refreshes every 10 min, factor scores weekly)
- The system scales horizontally — adding users does not increase backend computation load
- On-demand jobs (backtesting) are the only exception: they are user-initiated, but still run asynchronously via Celery and do not block the API thread
- All endpoints must document their expected data freshness so users understand the staleness contract

This pattern is already established for market data, news, and sector snapshots. All new features must follow the same model.

---

## 3. Monetisation Roadmap (Stripe)

The platform will eventually gate certain premium features behind paid subscriptions, integrated via Stripe. This is a future milestone — the architecture must be designed to accommodate it without major refactoring.

**Planned approach:**
- Stripe Checkout or Payment Element for subscription purchase
- Stripe webhook handler updates `UserProfile.stripe_account_id` (field already exists) and sets role to a paid tier
- New role or subscription flag: e.g. `PREMIUM_SUBSCRIBER` or a `subscription_tier` field on `UserProfile`
- DRF permission class `HasActiveSubscription` gates premium endpoints
- Free tier: market overview, news feed, basic screener
- Paid tier (examples): factor engine, backtesting, decile analysis, advanced spread tools, downloadable data

**Design requirements now (so Stripe integration is not a rewrite later):**
- All analytics endpoints must already check a permission class — even if that class currently allows all authenticated users, swapping it for a subscription check requires no structural change
- The `UserProfile` model must carry a `subscription_tier` field from the start (add in the `watchlist/` or next migration)
- The custom analytics module framework must declare which tier each module requires in its config so the nav menu can show lock icons for unpaid users

Stripe integration implementation is explicitly deferred but the permission scaffolding and `subscription_tier` field ship with the core build.

---

## 4. Feature Extensibility

The platform is designed for continuous growth. New analytics modules, data sources (additional APIs, alternative data), and dashboard pages will be added over time as research evolves. Section 9 (Custom Analytics Module Framework) defines the contract every new module must satisfy to ensure additions remain modular and do not require core refactoring.

When adding a new feature:
- It gets its own Django app (or a clearly bounded module within an existing app)
- It follows the app-wide Celery serving model (section 2)
- It declares its permission tier (free / paid) at the config level
- It registers itself in the frontend nav via `src/data/index.json`

---

## 5. User Roles & Access Control

The existing `CustomUser` model already defines roles: `SUBSCRIBER`, `EMPLOYEE`, `ADMIN`, `INSTITUTIONAL_INVESTOR`.

| Role | Access |
|------|--------|
| ADMIN | Full platform, user management, analytics config |
| EMPLOYEE | Full analytics and data access |
| INSTITUTIONAL_INVESTOR | Full analytics, read-only |
| SUBSCRIBER | Curated dashboards, limited analytics, no admin |

**Implementation pattern:** DRF permission classes (`IsAuthenticated`, custom `IsInternalUser`, `IsSubscriber`) applied per view. JWT via `rest_framework_simplejwt` (existing). No multi-tenancy required in V1.

---

## 6. Backend Architecture

### 6.1 Django App Structure

```
backend/
├── fintank_backend/      # project config, celery, urls
├── users/                # existing: CustomUser, UserProfile, JWT auth
├── stockuploader/        # existing: Stock, ETF, Crypto, financial statement models
├── analyzer/             # existing: FMP/S3 data fetching, sector/index APIs
├── news/                 # existing (enhanced): multi-source ingestion, ticker linking
├── watchlist/            # NEW: performance-tracked watchlist (split from stockuploader)
├── factor_engine/        # NEW: factor scoring, decile analysis
├── backtester/           # NEW: signal backtesting (V1) + strategy simulation (V2)
└── pages/                # existing: HTML views (staff portal)
```

### 6.2 Async Computation Pattern (All New Analytics Apps)

Every analytics computation follows this pipeline:

```
1. Celery task triggered (scheduled beat or on-demand API call)
2. Worker fetches raw data (DB → S3 parquet → FMP API, in that order)
3. Computation runs in worker process
4. Results serialized as Parquet (time-series) or JSON (aggregates)
5. Results written to S3 under organised prefix
6. Redis cache key set with result summary + TTL
7. Django view serves: Redis → S3 fallback → 202 "computing" if neither available
```

On-demand jobs (backtesting) return a `task_id` immediately; frontend polls `/backtester/results/<task_id>/` until status = `complete`.

### 6.3 Caching Strategy

Extend existing pattern (`home:{data_type}:{qualifier}:v1`) with:

| Cache key pattern | TTL | Source |
|-------------------|-----|--------|
| `factor:{universe}:{factor}:v1` | 24h | Celery weekly run |
| `decile:{universe}:{factor}:v1` | 24h | Celery weekly run |
| `backtest:{task_id}:v1` | 72h | On-demand Celery |
| `news:feed:{page}:v1` | 30m | Celery 30m run |
| `news:ticker:{symbol}:v1` | 30m | Celery 30m run |
| `watchlist:{user_id}:v1` | 60s | On write invalidate |

All cache values remain gzip-compressed JSON (existing pattern). S3 holds durable parquet/JSON output; Redis is the fast-path layer.

---

## 7. Feature Specifications

### 7.1 Market Overview Dashboard (Enhance Existing)

**Status:** Largely built. Enhance without breaking.

**Existing:** index performance table, gainers/losers, sector heatmap, news carousel.

**Additions:**
- Crypto performance module alongside equity indices
- Market breadth indicator (advancing vs declining)
- VIX + bond yield summary strip at top of page
- News carousel enhanced to show ticker tags on each article card

**Files touched:**
- `src/pages/index.js`
- `src/componentsLegacy/CardNews.js` (add ticker tag display)
- `backend/analyzer/analyzer_utils/CorePerformanceTools.py` (add breadth function)

---

### 7.2 Asset Detail Pages

**Status:** `/src/pages/stock-data/` directory exists but empty. Build out.

#### Stock Detail Page (`/stock-data/[ticker]`)
Sections:
1. **Header strip** — current price, 1D change, market cap, sector, exchange
2. **Price chart** — OHLCV candlestick (1D/1W/1M/3M/1Y), volume bars overlay. Use existing `useNewCandleSticks` hook.
3. **Financial statements tabs** — Income Statement, Cash Flow, Balance Sheet pulled from existing `IncomeStatement`, `CashFlowStatement`, `BalanceSheet` models. Annual/TTM toggle.
4. **Valuation metrics** — from `FundamentalMetric` / `FundamentalMetricTTM`. Existing `MetricsTable.js` reused.
5. **Factor scores** — factor engine scores for this ticker (P/E rank, ROE rank, FCF yield rank, momentum). Small badge display.
6. **News feed** — paginated list from `/news/ticker/<symbol>/` endpoint.
7. **Analyst estimates** (if FMP endpoint available) — price target, consensus.

**ETF Detail Page (`/etf/[ticker]`):**
- Price chart, holdings top-10, sector exposure bar chart (reuse `useSectorExposure`), performance vs benchmark.

**Index Detail Page (`/indices/[symbol]`):**
- Price chart, constituents heatmap (reuse existing `/constituent-returns/` endpoint), top movers within index.

**Crypto Detail Page (`/crypto/[symbol]`):**
- Price chart, market cap, 24h volume, basic metrics.

---

### 7.3 News Aggregation Engine (Enhance Existing `news/` App)

**Current state:** `GetNewsArticles` class pulls category JSON from S3. No ticker linking, no multi-source.

**Target state:**

**Ingestion:**
- Source 1: FMP news API (`/v3/stock_news`, `/v3/general_news`)
- Source 2: NewsAPI.org or Benzinga (configurable via `NEWS_SECONDARY_SOURCE` env var)
- Celery task `update_news_articles` expanded to fetch both sources every 30 minutes

**Normalisation (`backend/news/normalizer.py` — new):**
```python
# Common schema for all articles
{
  "id": str,           # hash of url
  "title": str,
  "summary": str,
  "url": str,
  "source": str,       # "fmp" | "newsapi" | "benzinga"
  "published_at": iso8601,
  "tickers": [str],    # extracted + FMP-provided
  "sectors": [str],
  "themes": [str]      # e.g. "earnings", "macro", "fed", "crypto"
}
```

**Ticker extraction (`backend/news/ticker_extractor.py` — new):**
- Regex scan of headline + body against known ticker list (from Redis `stock:names:v1` cache)
- Merge with tickers already provided by FMP in their news response
- Filter false positives using minimum word-length and capitalisation rules

**Storage:**
- Normalised articles written as JSON to S3: `news_json_articles/normalised/{YYYY-MM-DD}.json`
- Index (ticker → article IDs) stored in Redis with 30m TTL

**New API endpoints:**
- `GET /news/feed/?page=1&ticker=AAPL&sector=Technology&theme=earnings` — paginated feed with filters
- `GET /news/ticker/<symbol>/` — articles linked to a specific ticker (used by asset detail pages)

---

### 7.4 Spread Analysis & Capital Markets (Enhance Existing)

**Status:** `EquityCharts.js` and `EconomicCharts.js` are built. Enhance.

**Additions:**
- Persist user-defined custom spread pairs (ticker A vs ticker B) in user profile
- Export chart data to CSV button
- Add credit spread data (HY vs IG) if available from FMP
- Ensure all existing spreads (Russell Value/Growth, S&P vs Nasdaq, yield curves) remain intact

**Files touched:**
- `src/componentsLegacy/EquityCharts.js`
- `src/componentsLegacy/EconomicCharts.js`
- `backend/users/models.py` (add `saved_spreads` JSON field to UserProfile)

---

### 7.5 Watchlist & Performance Tracking (New `watchlist/` App)

**Current state:** `ProfileStock` in `stockuploader` links user to stock, but no entry price/date tracking.

**New Django app (`backend/watchlist/`):**

```python
# models.py
class WatchlistEntry(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    symbol = models.CharField(max_length=20)
    asset_type = models.CharField(choices=["stock","etf","crypto","index"])
    added_at = models.DateTimeField(auto_now_add=True)
    entry_price = models.DecimalField(...)  # price at time of addition
    notes = models.TextField(blank=True)
```

**API endpoints:**
- `GET /watchlist/` — list entries with current price + % change from entry
- `POST /watchlist/add/` — add symbol (auto-fetches current price as entry_price)
- `DELETE /watchlist/<id>/remove/`
- `GET /watchlist/performance/` — aggregate P&L, volatility contribution (uses existing covariance hooks)

**Frontend page (`src/pages/watchlist.js` — new):**
- Table: symbol, asset type, entry date, entry price, current price, % change, notes
- Chart: portfolio-level line chart from entry to today (aggregate)
- Sector exposure bar chart (reuse `useSectorExposure`)
- Volatility contribution (reuse `useCovarWatchList`)

---

### 7.6 Factor Engine & Decile Analysis (New `factor_engine/` App)

**Django app (`backend/factor_engine/`):**

**Factors computed on SP500 / TSX / NASDAQ universes:**

| Factor | Metric | Source |
|--------|--------|--------|
| Value | P/E, P/B, EV/EBITDA, FCF yield | FundamentalMetricTTM |
| Quality | ROE, ROIC, Gross Margin, D/E | FundamentalRatioTTM |
| Growth | Revenue growth YoY, EPS growth YoY | IncomeStatement |
| Momentum | 1M, 3M, 12M-1M price return | FMP quote history |
| Composite | Z-score average of above | computed |

**Computation flow:**
1. Celery task `compute_factor_scores(universe)` runs weekly (or on-demand)
2. Fetches all constituent metrics from DB (existing models have this data)
3. Z-score normalises each factor within universe
4. Ranks and bins into deciles (1 = lowest, 10 = highest)
5. Stores output Parquet to S3: `factor_scores/{universe}/{YYYY-MM-DD}.parquet`
6. Sets Redis cache `factor:{universe}:{factor}:v1`

**API endpoints:**
- `GET /factor-engine/scores/<universe>/` — full factor score table (ticker, each factor score, composite)
- `GET /factor-engine/deciles/<universe>/<factor>/` — decile distribution with median return per decile
- `GET /factor-engine/ticker/<symbol>/` — factor scores for a single ticker

**Frontend page (`src/pages/factor-rankings.js` — new):**
- Universe selector (SP500, TSX, NASDAQ, EAFE)
- Factor selector (Value, Quality, Growth, Momentum, Composite)
- Sortable table: ticker, sector, composite score, individual factor scores
- Decile bar chart: median forward return per decile (key "does this factor work?" visual)
- Scatter: factor score vs 3M forward return

---

### 7.7 Backtesting Engine (New `backtester/` App — Phased)

#### V1: Signal Backtesting

**Concept:** Given a factor and universe, does ranking stocks by that factor predict forward returns?

**Celery task `run_signal_backtest(params)`:**
```
Inputs:
  universe: str (e.g. "SP500")
  factor: str (e.g. "fcf_yield")
  date_range: [start, end]
  rebalance_freq: str ("monthly" | "quarterly")
  n_quintiles: int (5)

Process (for each rebalance date):
  1. Rank universe by factor value
  2. Assign quintile
  3. Calculate forward return to next rebalance date
  4. Record quintile return

Outputs (JSON to S3):
  - IC (information coefficient) per period
  - Hit rate (% periods where Q1 > Q5 or Q5 > Q1 depending on factor direction)
  - Quintile return chart data
  - Max drawdown per quintile
  - Summary stats table
```

**API endpoints:**
- `POST /backtester/run/` — submit job, returns `{task_id, status: "queued"}`
- `GET /backtester/status/<task_id>/` — `{status: "queued|running|complete|failed"}`
- `GET /backtester/results/<task_id>/` — full result JSON
- `GET /backtester/history/` — user's past backtest runs

**Frontend page (`src/pages/backtester.js` — new):**
- Parameter form: universe, factor, date range, rebalance frequency
- Submit → polling spinner → results panel
- Results: IC time series chart, quintile return bar chart, summary stats table
- Save/compare: ability to save a run and compare two runs side-by-side

#### V2: Strategy Simulation (Future Phase)

Extend V1 with:
- Position sizing rules (equal weight, factor-weighted, volatility-scaled)
- Transaction cost model (bps per trade)
- Benchmark comparison (buy-and-hold index)
- Full equity curve with drawdown chart
- Output: CAGR, Sharpe, Sortino, max drawdown, annual turnover

V2 is specced here for awareness but not implemented until V1 signal backtesting is validated.

---

### 7.8 Stock Screener (Enhance Existing)

**Status:** `Screener.js` exists with sector filtering. Enhance.

**Additions:**
- Filter by factor score range (e.g. "composite score > 7")
- Filter by market cap range, P/E range, country
- Sort by any column
- Link each result row to the new stock detail page `/stock-data/[ticker]`

**Files touched:**
- `src/componentsLegacy/Screener.js`
- `src/componentsLegacy/ScreenerPagination.js`
- `backend/analyzer/views.py` (extend screener endpoint with new filter params)

---

### 7.9 Custom Analytics Module Framework

Design pattern for adding future research modules without refactoring:

```
backend/{module_name}/
├── __init__.py
├── apps.py
├── models.py          # optional: store config/results metadata
├── tasks.py           # Celery computation task(s)
├── views.py           # DRF endpoints
├── urls.py
└── engine/            # pure computation, no Django dependencies
    └── compute.py

src/pages/{module-name}.js    # frontend page
src/hooks/use{ModuleName}.js  # data fetching hook
```

**Contract every module must satisfy:**
- `tasks.compute_{module}()` Celery task writes output to S3 under `{module}/` prefix
- At least one DRF endpoint (`GET /{module}/results/`) serves from Redis → S3
- Frontend page registered in nav menu via `src/data/index.json` menu config

---

## 8. Frontend Architecture

### 8.1 Routing

| Router | Hosts |
|--------|-------|
| Pages Router (`src/pages/`) | All financial dashboards |
| App Router (`src/app/`) | Solana dApp pages only (existing) |

New pages all go in Pages Router, following the existing Bootstrap + Chart.js pattern in `src/componentsLegacy/`.

### 8.2 New Pages Summary

| Route | Description | Status |
|-------|-------------|--------|
| `/stock-data/[ticker]` | Stock detail | Build |
| `/etf/[ticker]` | ETF detail | Build |
| `/indices/[symbol]` | Index detail | Build |
| `/crypto/[symbol]` | Crypto detail | Build |
| `/factor-rankings` | Factor/decile dashboard | Build |
| `/backtester` | Backtesting UI | Build |
| `/watchlist` | Enhanced watchlist | Build |
| `/` | Home dashboard | Enhance |
| `/screener` (or enhance index) | Stock screener | Enhance |
| `/spreads` | Capital markets spreads | Enhance |

### 8.3 New Hooks

| Hook | Purpose |
|------|---------|
| `useFactorScores.js` | Fetch factor scores for universe or ticker |
| `useDecileChart.js` | Decile return distribution data |
| `useBacktestResults.js` | Poll backtest status + fetch results |
| `useTickerNews.js` | News articles for a specific ticker |
| `useWatchlistPerformance.js` | Watchlist entries with live P&L |
| `useStockDetail.js` | Aggregate hook for stock detail page |

### 8.4 State Management

No changes to Redux structure. New pages use SWR (consistent with existing hooks) for server state. Watchlist additions/removals invalidate the watchlist cache via POST/DELETE → refetch pattern.

---

## 9. Data Architecture

```
PostgreSQL (via Django ORM)
├── User data: CustomUser, UserProfile, WatchlistEntry
├── Security metadata: Stock, ETF, Crypto
└── Financial statements: IncomeStatement, CashFlowStatement, BalanceSheet,
    FundamentalMetric, FundamentalRatio (and TTM variants)

Redis (gzip-compressed JSON)
├── Market data cache (24h): index performance, sector data, gainers/losers
├── Factor scores cache (24h): per universe/factor
├── News cache (30m): feed pages, per-ticker article lists
├── Backtest results cache (72h): per task_id
└── Watchlist cache (60s, invalidated on write): per user_id

AWS S3 (thetradingfloor bucket, us-east-1)
├── index_data/              # existing: historical index parquet
├── company_profiles/        # existing: company profile parquet
├── news_json_articles/      # existing (enhanced): normalised multi-source JSON
├── factor_scores/           # NEW: weekly factor score parquet by universe
├── backtest_results/        # NEW: on-demand backtest JSON outputs
└── analytics/{module}/      # NEW: future custom module outputs
```

---

## 10. Non-Functional Requirements

### Performance
- All read endpoints serve from Redis cache (p50 < 50ms)
- S3 fallback for cache misses (p50 < 500ms)
- Heavy computation always async (Celery); never blocks API thread
- FMP API calls rate-limited by existing TTL-based caching

### Security
- All endpoints require `IsAuthenticated` (JWT)
- SUBSCRIBER-role endpoints gated with `IsSubscriber` permission class
- No API keys in code; all via environment variables
- `CORS_ALLOWED_ORIGINS` restricted to known frontend domain(s)
- Rate limiting on API endpoints via `django-ratelimit` or DRF throttling

### Scalability
- Celery workers horizontally scalable (stateless computation)
- S3 storage scales unboundedly
- Redis Cluster upgrade path when single-node saturates
- Parquet columnar format optimised for large time-series reads

### Reliability
- Celery tasks retry on failure (max 3 retries, exponential backoff)
- `is_market_open_now()` guard prevents redundant off-hours computation (existing)
- S3 writes use atomic temp-file pattern to avoid partial reads
- Graceful degradation: if FMP API is down, serve stale cache; if no cache, return 503 with clear message

### Observability
- Structured logging in all Celery tasks (task_name, duration, result_size, cache_hit)
- Django logging to stdout (container-friendly)
- Error alerting: Celery task failure sends alert (email or Slack webhook via env config)

---

## 11. Environment Variables (Extended)

Existing vars documented in CLAUDE.md. Add:

| Variable | Purpose |
|----------|---------|
| `NEWS_SECONDARY_SOURCE` | `newsapi` or `benzinga` |
| `NEWS_SECONDARY_API_KEY` | API key for secondary news source |
| `RATELIMIT_ENABLE` | `true`/`false`, enable DRF throttling |
| `BACKTEST_MAX_WORKERS` | Celery concurrency for backtest tasks |
| `FACTOR_RECOMPUTE_SCHEDULE` | Cron expression for weekly factor runs |
| `STRIPE_SECRET_KEY` | Already exists — Stripe API key |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `STRIPE_PRICE_ID_PREMIUM` | Stripe Price ID for premium subscription product |

---

## 12. Critical Files — Existing (Reuse / Extend)

| File | Role |
|------|------|
| `backend/fintank_backend/settings.py` | Django config, add new apps here |
| `backend/fintank_backend/urls.py` | Register new app URL namespaces |
| `backend/fintank_backend/celery.py` | Add new Celery task registrations |
| `backend/analyzer/analyzer_utils/CorePerformanceTools.py` | Extend with breadth function |
| `backend/utils/StockCalculations.py` | Reuse `GetData` class for parquet reads in factor engine |
| `backend/utils/IndexFileMappers.py` | Reuse S3 file mappings |
| `backend/news/getNews.py` | Extend to call multi-source ingestion |
| `backend/stockuploader/models.py` | Source for factor engine input data |
| `src/hooks/useStockData.js` | Reuse in stock detail page |
| `src/hooks/useNewCandleSticks.js` | Reuse for OHLCV charts on detail pages |
| `src/hooks/useSectorExposure.js` | Reuse in watchlist and ETF detail |
| `src/hooks/useCovarWatchList.js` | Reuse in watchlist volatility section |
| `src/componentsLegacy/MetricsTable.js` | Reuse on stock detail page |
| `src/componentsLegacy/ValuationTable.js` | Reuse on stock detail page |
| `src/componentsLegacy/EquityCharts.js` | Enhance (add CSV export, custom pairs) |
| `src/componentsLegacy/EconomicCharts.js` | Enhance (add credit spreads) |
| `src/componentsLegacy/Screener.js` | Enhance (factor score filters) |

---

## 13. Build Sequence (Recommended Order)

1. **Stock detail page** — highest user value, reuses most existing components and hooks
2. **Enhanced news engine** — multi-source ingestion + ticker linking; unlocks news on detail pages
3. **Watchlist app** — split `ProfileStock` into dedicated app, add entry price tracking
4. **Factor engine** — decile analysis and factor scores; builds on existing DB models
5. **Backtesting V1** — signal backtesting; depends on factor engine being stable
6. **Market overview enhancements** — breadth, VIX strip, news ticker tags
7. **Screener enhancements** — add factor filters after factor engine is live
8. **ETF / Index / Crypto detail pages** — parallel to stock detail, similar pattern
9. **Custom analytics framework** — document the module contract once patterns are proven
10. **Backtesting V2** — strategy simulation after V1 validates the engine

---

## 14. Verification Checklist

- [ ] `python manage.py check` passes with all new apps registered
- [ ] `python manage.py migrate` runs cleanly (no conflicts)
- [ ] `npm run build` passes with no TypeScript/lint errors
- [ ] Each new Celery task runs manually: `celery call factor_engine.tasks.compute_factor_scores`
- [ ] Each new API endpoint returns expected schema (test with curl or Postman)
- [ ] Stock detail page renders candlestick chart, financial tables, factor scores, news
- [ ] Watchlist: add a stock, verify entry price recorded, verify % change displayed
- [ ] Backtester: submit a run, poll for completion, verify result JSON structure
- [ ] Factor rankings: load SP500 universe, sort by composite, decile chart renders
- [ ] News feed: verify ticker tagging on at least 3 known high-volume tickers (AAPL, TSLA, MSFT)
- [ ] External client (SUBSCRIBER role) cannot access admin-only endpoints
- [ ] Redis cache hit confirmed on second request (check gzip key exists in redis-cli)
