# Fintank Backend Breakdown

A map of the Django REST backend in [backend/](backend/) — what each app does, how data reaches the API, and where the gaps are.

Everything below was read from source or introspected from a live Django instance. The endpoint table comes from walking `get_resolver()`, not from reading `urls.py` by hand, so it reflects what is actually routable. Anything unverified is in [Gaps & Notes](#gaps--notes) rather than stated as fact.

**Counts:** 7 local apps (one inert, one API-less) · 25 project API endpoints — 16 analyzer, 7 users, 1 news, 1 stockuploader (+ `dj-rest-auth` / `allauth` / SimpleJWT includes) · 12 Celery tasks (3 with a static beat entry) · 14 database models · 18 Redis cache-key families.

> **In progress (2026-08-13):** the `backtester` app exists but is **numerical core only** — no models, no views, no URLs, no Celery tasks yet, so the endpoint and model counts above are unchanged. See [backtester](#backtester--portfolio-simulation-engine).

---

## Overview

The backend is a **read-mostly cache server in front of S3 and FMP**, plus a conventional Django auth/admin app bolted to the same project.

Almost none of the market data lives in Postgres. The request path for a typical market-data endpoint is:

```
Frontend  →  Django view  →  Redis (gzipped JSON blob)  →  Response
                    ↓ (only on cold cache)
              CorePerformanceTools warmer  →  S3 parquet / FMP REST
                    ↓
              writes the blob back to Redis
```

Celery Beat runs the warmers on a schedule so the cold path is rare. The design goal throughout is that **a user request never touches S3 or FMP** — it reads one pre-built blob out of Redis.

Postgres holds users, a symbol directory, and a set of financial-statement tables populated by spreadsheet import. It is not on the hot path for market data.

### Three data tiers

| Tier | Holds | Read by |
|---|---|---|
| **Redis** (db 15) | Gzipped JSON payloads, keyed `home:*` / `stock:*` / `company:*` | Every API view |
| **S3** `thetradingfloor` | Parquet price/fundamental/econ files, constituent JSON, news JSON | `CorePerformanceTools` warmers via `GetData` |
| **Postgres + PostGIS** | Users, profiles, `Stock`/`ETF`/`Crypto` directory, statement tables | Auth views, `all-stock-names`, admin |

### Stack

Django 5.2 · DRF · SimpleJWT · dj-rest-auth + allauth · Celery + Redis · django-celery-beat / -results · PostGIS · boto3 + s3fs + pyarrow · pandas · django-import-export · whitenoise · django-storages.

---

## Apps

| App | Models | Purpose |
|---|---|---|
| [analyzer/](backend/analyzer/) | **none** | The market-data API. Pure read layer over Redis + S3 + FMP. All 16 market endpoints and 11 of 12 Celery tasks live here |
| [stockuploader/](backend/stockuploader/) | 11 | Symbol directory (`Stock`, `ETF`, `Crypto`) + financial-statement tables. Bulk import via `django-import-export` |
| [users/](backend/users/) | 3 | `CustomUser` (email-unique, role choices), `UserProfile`, `AvatarPreset`. JWT auth + profile/avatar management |
| [news/](backend/news/) | none | Serves 28 pre-scraped news article sets from S3, cached in Redis |
| [pages/](backend/pages/) | none | Server-rendered HTML for the staff upload portal (login, dashboard) |
| [backtester/](backend/backtester/) | none *(yet)* | Portfolio simulation engine. **Numerical core only so far** — `engine/` is complete and tested, the Django surface is not built. No endpoints, no models, no tasks |
| [journal/](backend/journal/) | — | **Inert.** In `INSTALLED_APPS`, but `urls.py` is empty and the include is commented out in the root URLconf |

---

## The caching pattern

Every market-data endpoint follows one shape, established in [CorePerformanceTools.py](backend/analyzer/analyzer_utils/CorePerformanceTools.py):

**Warmer function** — fetches from source, wraps in a context dict, gzips, writes to Redis with a 24h TTL:

```python
context = {"data": data, "last_updated": timezone.now().isoformat(),
           "market_open": is_market_open_now()}
cache.set(key, gzip.compress(json.dumps(context).encode("utf-8")), timeout=86400)
```

**View** — reads the blob, decompresses, returns. On a miss it calls the warmer once and serves that result directly:

```python
data = cache.get(key)
if data:
    return Response(json.loads(gzip.decompress(data)), status=200)
data = warmer()                      # cold path
if data:
    return Response(data, status=200)
return Response({"detail": "Data temporarily unavailable"}, status=503)
```

**Celery task** — calls the warmer on a schedule, usually behind a market-hours guard:

```python
@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=10)
def update_index_performance(self):
    if not is_market_open_now():
        return "Market closed – skipping update"
    return get_index_performance()
```

Gzip is used because these payloads are large and Redis stores them verbatim; `home:economic_data:v1` alone is 2.7 MB raw and 0.46 MB compressed.

**One endpoint deviates:** `/economic-data/` returns the cached bytes directly as the response body with `Content-Encoding: gzip` rather than decompressing and re-rendering through DRF. At 2.7 MB that round trip is pure waste on every SSR request; skipping it takes a warm response from ~200 ms to ~2 ms. See [Economic data](#economic-data-capital-markets).

### Market-hours gating

[market_hours.py](backend/analyzer/analyzer_utils/market_hours.py) uses `pandas_market_calendars` against the real NYSE calendar (holidays included), not a naive weekday/time check:

- `is_market_open_now()` — true only inside the actual session for today's schedule
- `get_effective_market_date()` — today if open, else the last trading day, looking back 10 days to clear long weekends

Tasks that pull live quotes return early when the market is closed, so the last good blob stays in Redis rather than being overwritten with stale duplicates. Tasks over static data (profiles, economic series) are deliberately ungated.

---

## Endpoint reference

All mounted under `/api/`.

### analyzer — market data

| Endpoint | Cache key | Source | Warmer |
|---|---|---|---|
| `GET /all-stock-names/` | `stock:names:v1` | **Postgres** `Stock` via `StockSerializer` | `get_all_stock_names` |
| `GET /index-performance/` | `home:index_performance:v1` | FMP v3 `quote` (25 index symbols) | `get_index_performance` |
| `GET /etf-performance/` | `home:etf_performance:v1` | FMP v3 `quote` (~100 ETFs) | `get_etf_performance` |
| `GET /crypto-performance/` | `home:crypto_performance:v1` | FMP v3 `quotes/crypto` (~100 pairs) | `get_crypto_performance` |
| `GET /gainers-losers/` | `home:gainers_losers:v1` | FMP stable `biggest-gainers` / `-losers` | `get_biggest_gainers_and_losers` |
| `GET /index-history/<symbol>/` | `home:index_chart:<symbol>:v1` | FMP v3 `historical-price-full`, 15 indices in 3 batched calls | `get_index_charts` |
| `GET /sector-industry/<exchange>/` | `home:sector_performance:<exchange>:v1` | FMP stable sector + industry snapshot, 5 exchanges | `get_sector_performance_snapshot` |
| `GET /economic-data/` | `home:economic_data:v1` | **S3** `econ_data/` (24 parquets) | `get_economic_data` |
| `GET /constituent-returns/<universe>/` | `home:universe_constituents_returns:<universe>:v1` | S3 constituents → FMP `batch-quote` | `get_universe_constituents_returns` |
| `GET /universe-profiles/<universe>/` | `home:universe_profiles:<universe>:v1` | S3 constituents ∩ cached company profiles | `get_universe_profiles` |
| `GET /company-profiles/<symbol>/` | `company:profiles:v1` (whole set) | S3 `company_profiles.parquet` | `get_company_profiles` |
| `GET /stock-profile/<symbol>/` | `stock:long_profile:<SYM>:v1` | S3 `long_profiles.parquet` | lazy, per symbol |
| `GET /stock-prices/<symbol>/` | `stock:prices:<SYM>:v1` | S3 `stock_prices/daily/<SYM>_prices.parquet` | lazy, per symbol |
| `GET /stock-prices-monthly/<symbol>/` | `stock:prices:monthly:<SYM>:v1` | S3 `stock_prices/monthly/…` | lazy, per symbol |
| `GET /financial-statements/<symbol>/<universe>/<type>/` | `stock:statements:<type>:<universe>:<SYM>:v1` | S3 `_model_part_` parquet | lazy, per symbol |
| `GET /financial-statements/<symbol>/<type>/` | same | as above, universe auto-resolved | lazy |

The last five are **lazy per-symbol** rather than beat-warmed: there are thousands of symbols, so the first request for a symbol pays the S3 read and every subsequent one is served from Redis for 24h.

`universe` and `statement_type` are validated against `VALID_UNIVERSES` / `VALID_STATEMENT_TYPES` and return **400** on an unknown value, distinct from the **404** for a symbol that isn't in the parquet.

### Other apps

| Endpoint | App | Notes |
|---|---|---|
| `GET /get_articles/<item>/` | news | 28 categories, `home:news_articles:<item>:v1`, S3 `news_json_articles/`. 404 on unknown category |
| `POST /upload/<model_name>/` | stockuploader | Staff-only. Accepts `.parquet`/`.xlsx`, imports via the matching `Resource`. 10 model names registered |
| `POST /auth/register/` | users | Open registration |
| `GET /users/me/`, `PATCH /users/me/update/` | users | JWT required |
| `GET /users/me/profile/`, `PATCH …/update/`, `PATCH …/avatar/` | users | Avatar accepts multipart |
| `PATCH /users/me/change-password/` | users | JSON only |
| `POST /auth/token/`, `…/refresh/`, `…/verify/` | SimpleJWT | 5-day access **and** refresh lifetime |
| `/auth/login/`, `/auth/logout/`, `/auth/password/…` | dj-rest-auth | |
| `/auth/registration/…` | dj-rest-auth | Email verification flow |

---

## Economic data (capital markets)

The newest endpoint, and the fullest example of the S3 → Redis pattern. It backs [`/capital-markets`](src/pages/capital-markets.js), which fetches it in `getServerSideProps`.

**Source:** 24 parquets written by `stock_data_getter_v2.ipynb` (see [DATA_UPLOAD.md](backend/class_files/DATA_UPLOAD.md)):

- `econ_data/yield_spreads.parquet` — daily treasury curve (2/5/10/30y), the ICE BofA HY yield, and 5 spreads in bps
- `econ_data/{cpi,nonfarm,unemployment}.parquet` — monthly macro with MoM/QoQ/YoY
- `econ_data/relative_perf/{pair}.parquet` × 20 — monthly index-vs-index return spreads

**Shape:** the payload key names are a hard contract with the chart components, which dereference them literally (`economicData?.tenvtwo?.dates`). Three maps in `CorePerformanceTools` encode it:

| Map | Maps | Consumer |
|---|---|---|
| `YIELD_SERIES_COLUMNS` | frontend key → `yield_spreads` column | `EconomicCharts.js` |
| `MACRO_SERIES_COLUMNS` | frontend key → (parquet, column) | `EconomicCharts.js` |
| `RELATIVE_PERF_PACKS` | parquet stem → `*_pack` key | `EquityCharts.js` |

```jsonc
{
  "economic": { "ten": { "dates": [...], "value": [...] }, ... },   // 13 series
  "equity_markets": {
    "sptsxpack": { "quarterly": {...}, "yearly": {...}, "threeyear": {...} }
  },                                                                 // 20 packs
  "last_updated": "..."
}
```

**NaN handling:** `_date_value_series` drops nulls **per series**, so each chart carries its own date axis. The legs start on different dates (DGS10 in 1962, the HY index in 1996) and the 30-year has a 2002–2006 gap, so a frame-wide `dropna` would clip every yield chart to the shortest leg — which is what the v1 implementation did. Values are rounded to 6 dp; raw float64 returns otherwise serialise to 17 significant digits and inflate the payload.

---

## backtester — portfolio simulation engine

**Status as of 2026-08-13: numerical core complete, Django surface not started.** Tasks 1–10 of
[the plan](docs/superpowers/plans/2026-08-11-portfolio-backtest.md) are done; 11–20 are not.
Design: [2026-08-11-portfolio-backtest-design.md](docs/superpowers/specs/2026-08-11-portfolio-backtest-design.md),
which supersedes Phase 10 of the master implementation plan.

This is the first app in the backend that is **not** a cache server over S3. It computes.

### What exists

1,771 lines across `engine/`, with 2,028 lines of tests — **190 tests, all passing**.

| Module | Lines | Responsibility |
|---|---|---|
| `engine/config.py` | 290 | `BacktestRequest` / `Holding` / `OptimizerConfig` dataclasses, `validate_request`, canonical `normalized_payload` for the run-dedupe hash |
| `engine/prices.py` | 224 | `PricePanel`, the S3→FMP→Redis loader, and the availability/eligibility masks |
| `engine/covariance.py` | 75 | Sample and Ledoit–Wolf shrinkage, implemented directly (no scikit-learn) |
| `engine/optimizers.py` | 224 | The six weighting schemes behind one signature, plus the `OPTIMIZERS` registry |
| `engine/backtest.py` | 365 | The simulation loop, drift, rebalancing, turnover, contributions, inception and delisting |
| `engine/metrics.py` | 253 | The full performance table, IRR, contribution decompositions |
| `engine/diagnostics.py` | 214 | Thirteen seven-sins findings in plain language |
| `engine/frontier.py` | 126 | Efficient frontier sampling |

### The design rule that matters

**Everything under `engine/` is pure functions over numpy/pandas.** No Django imports, no S3, no
Redis — `prices.py` is the single exception, and all of its I/O funnels through one function,
`_fetch_symbol_series`, which every test monkeypatches. That is why 190 tests run in ~5 seconds
against no infrastructure.

This is the opposite of the `analyzer` convention and deliberately so: `analyzer` is a read layer
where the interesting behaviour *is* the caching, whereas here the interesting behaviour is
arithmetic that has to be right.

### The timing contract

The single most important thing in the app, and the one most commonly got wrong:

> Weights decided for date `t` may use data only through `t − 1 − gap_days`.
> The portfolio return realized at `t` is `R_t = w_{t−1}ᵀ · r_t`.

Multiplying `w_t` by `r_t` means rebalancing into the winners on the day you observe them
winning. It produces spectacular fictional returns and **no crash, no exception, no downstream
symptom** — just good news. `tests/test_backtest.py::LookAheadRegressionTests` is the permanent
guardrail, and it has been observed failing against two deliberately broken loops (drift computed
before the return; post-rebalance weights applied to the same day's return). Do not reorder that
loop without re-running it.

### Two wealth series, deliberately not one

| Series | Definition | Feeds |
|---|---|---|
| `index` | time-weighted growth of $1, contribution-free | **every** risk and return statistic |
| `nav` | actual account balance, includes deposits | ending balance, total gain, IRR |

Conflating them is the second-easiest way to produce wrong numbers: a CAGR off `nav` measures the
deposit schedule as much as the strategy, and a drawdown off `nav` lets a well-timed deposit paper
over a real loss.

### Validation against live data

Reproduces the prototype notebook's 60/40 SPY/AGG reference (`class_files/backtester_portfolio.ipynb`,
which is gitignored along with the rest of `class_files/`):

| | Engine | Notebook |
|---|---|---|
| Max drawdown | −0.339949 | −0.339949 |
| CAGR | 8.2008% | 8.2203% |

Drawdown dates come out 2007-10-09 → 2009-03-09, recovered 2010-11-04 — the correct S&P 500 GFC
peak, trough and recovery, which nothing in the code was fitted to.

**Comparisons need `inception_policy='common_start'`.** The engine's default is phase-in, which for
SPY/AGG starts in 1999 with SPY alone and admits AGG when it lists in 2003. That run reports 6.36%
CAGR and a **−47.5%** drawdown, and is a different question rather than a bug — the notebook used
intersection.

That phase-in run is also the best demonstration of why the diagnostics exist: the −47.5% is a
dot-com single-stock drawdown wearing a 60/40 label, and `single_asset_period` fires as **critical**
to say so.

### Changes to existing code

| File | Change |
|---|---|
| `utils/StockCalculations.py` | `load_stock_prices` gained an optional `columns=` parameter, pushed into `pq.read_table` — mirrors `load_index_parquet`. Additive: `columns=None` reproduces prior behaviour, and both existing call sites pass none |
| `fintank_backend/settings.py` | `INSTALLED_APPS` += `backtester.apps.BacktesterConfig`; new `BACKTEST_MAX_WORKERS` (8) and `FREE_TIER_BACKTEST_LIMIT` (10), both env-overridable |

The price parquets carry 52 columns and the backtester needs two, so the projection avoids reading
~26× more bytes than necessary per symbol — which matters at 30 symbols a panel.

### New cache-key family

| Key | TTL | Written by |
|---|---|---|
| `prices:panel:{SYMBOL}:v1` | 24h | `engine/prices.py` — gzipped `[date, adjClose]` pairs |

Reserved but not yet written: `backtest:{task_id}:v1` (72h) and `backtest:symbol_index:v1` (24h),
both landing with Tasks 13–14.

### Not built yet

Models (`Portfolio`, `PortfolioHolding`, `BacktestRun`), the `UserProfile.subscription_tier` field
and its serializer guard, `quota.py`, `views.py`, `urls.py`, `tasks.py`, and the whole frontend.
`/api/backtester/` does not route.

> 🔒 **When Task 11 lands, the field and the guard must be in the same commit.**
> `UserProfileSerializer` is `fields = "__all__"` and `users/views.py` feeds it `request.data`
> directly, so adding `subscription_tier` without marking it `read_only` ships a subscription tier
> any authenticated user can `PATCH` themselves into, defeating the meter entirely.

---

## Celery

`celery -A fintank_backend worker -B -l info` (or worker and beat separately). Redis must be up first.

### Fork safety

[celery.py](backend/fintank_backend/celery.py) hooks `worker_process_init` to reset fsspec state in every forked child:

```python
fsspec.asyn.reset_lock()
s3fs.S3FileSystem.clear_instance_cache()
```

fsspec keeps a module-global event loop and an instance cache created in the parent before the pool forks. Children inherit a loop bound to a thread that doesn't exist for them, and any cached `S3FileSystem` raises *"This class is not fork-safe."*

The same hazard is handled a second way in [StockCalculations.py](backend/utils/StockCalculations.py): `get_fs()` keys the filesystem by PID and rebuilds it lazily, and `GetData.fs` is a **property** rather than an attribute so module-level `GetData()` instances (built at import, before the fork) resolve the filesystem in whichever process is actually using it.

### Tasks

| Task | Market-hours gated | Beat entry |
|---|---|---|
| `update_index_performance` | yes | — |
| `update_etf_performance` | yes | — |
| `update_crypto_performance` | yes | — |
| `update_gainers_losers` | yes | — |
| `update_market_datasets` (index charts) | yes | — |
| `update_sector_industry_snapshot` | yes | — |
| `update_universe_constituent_performance` | yes | — |
| `get_stock_names` | no | — |
| `company_profiles` | no | — |
| `update_universe_profiles` | no | **86400** |
| `update_economic_data` | no | **86400** |
| `news.tasks.update_news_articles` | no | **86400** |

Only three tasks have a static `CELERY_BEAT_SCHEDULE` entry — see [Gaps](#2-nine-of-twelve-celery-tasks-have-no-schedule-in-version-control).

---

## S3 layout

Bucket `thetradingfloor`, region `us-east-1`. Read through `GetData` (pyarrow + s3fs) except news, which uses a boto3 client directly.

| Prefix | Reader | Pipeline status |
|---|---|---|
| `econ_data/`, `econ_data/relative_perf/` | `load_econ_parquet`, `load_relative_performance_parquet` | **v2, current** |
| `stock_data/stock_prices/{daily,monthly}/` | `load_stock_prices{,_monthly}` | **v2, current** |
| `index_data/constituents/` | `get_index_constituents` | **v2, current** |
| `news_json_articles/` | `GetNewsArticles` | current |
| `index_data/index_prices_v1/` | `load_parquet` | **v1 — v2 uploaded, not cut over** |
| `index_data/contr_to_var/` | *(none)* | **v2, uploaded, no reader** |

### Reader/writer mismatch

Three read paths point at v1 **aggregate** objects while the v2 pipeline writes fresh **per-symbol** files into the same prefixes. Both generations coexist on S3, and the backend reads the older one:

| Endpoint reads | Modified | v2 file sitting alongside it | Modified |
|---|---|---|---|
| `company_profiles/company_profiles.parquet` (6.6 MB) | 2026-06-04 | `company_profiles/{SYM}_profile.parquet` × 13,448 | **2026-08-02** |
| `long_profiles/long_profiles.parquet` (4.4 MB) | 2026-06-04 | same per-symbol files (mapped with the `long_profiles` field set) | **2026-08-02** |
| `{type}/{region}/{universe}/…_model_part_….parquet` × 8 | 2026-06-06 | `{type}/{SYM}_{type}.parquet` × ~6,036 per type | **2026-08-02** |

So `/company-profiles/`, `/stock-profile/` and `/financial-statements/` are serving two-month-old data with a current copy of the same data unread next to it. The `_model_part_` aggregates are superseded and no longer maintained. This is a **reader cutover**, not a data-availability problem — the fix is in `GetData`, not the notebook.

Price and constituent keys are **flat and symbol-addressable** (`stock_prices/daily/AAPL_prices.parquet`) — the frontend asks by symbol, not by index membership, so the sub-universe folder is dropped at upload time.

### Universe resolution

[universe_lookup.py](backend/analyzer/analyzer_utils/universe_lookup.py) exists because `long_profiles` carries no universe column and `exchange_short_name` can't substitute — NASDAQ-listed symbols are spread across sp500, nas, r2000 and rmicro. It builds a reverse index from the constituent lists (cached 24h at `stock:universe_index:v1`) and returns **candidates in priority order**, because a symbol legitimately belongs to several universes and index membership doesn't guarantee the statement parquet carries it. `get_financial_statements_resolved` walks the candidates until one yields data.

Note the naming seam it papers over: the constituent lists say `nasdaq`, the statement parquets say `nas`.

---

## Database

### stockuploader (11 models)

`Stock` (symbol, name, exchange, sector, industry, country, `is_etf`) · `ETF` · `Crypto` · `ProfileStock` (user↔stock watchlist join) · `IncomeStatement` · `CashFlowStatement` · `BalanceSheet` · `FundamentalMetric` · `FundamentalRatio` · `FundamentalMetricTTM` · `FundamentalRatioTTM`.

The four statement/fundamental families are wide (~80–120 columns) with `UniqueConstraint(symbol, date)` and `ordering = ['-date']`. They're populated by spreadsheet/parquet import through `django-import-export`, either from the admin or `POST /api/upload/<model_name>/`.

**Only `Stock` is on an API path** — `all-stock-names` serialises it. The statement tables are not read by any endpoint; statements are served from S3 parquet instead.

### users (3 models)

`CustomUser(AbstractUser)` — unique email, `user_security_identifier` UUID, `role` from `UserRole` (subscriber / employee / admin / institutional_investor), indexed on role and created_at. `UserProfile` — one-to-one, company details, Stripe account id, and an `avatar_url` property preferring an upload over a preset. `AvatarPreset` — admin-managed avatars, auto-slugged.

---

## Configuration

| Setting | Value | Note |
|---|---|---|
| `CACHES["default"]` | `redis://127.0.0.1:6379/**15**` | Hardcoded override, applied *after* the dict is built — the `REDIS_URL` env var (default db 1) is read but discarded |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | Assigned twice; the redis value wins over the earlier `"django-db"` |
| `SIMPLE_JWT` | access **and** refresh = 5 days | Access-token lifetime is unusually long |
| `DEBUG` | `os.environ.get('DEBUG', 'True') == 'True'` | Defaults to **True** when unset |
| `ALLOWED_HOSTS` | heroku + localhost only | Narrower than `CORS_ALLOWED_ORIGINS` |
| `DEFAULT_FILE_STORAGE` | FileSystem in DEBUG, S3 otherwise | Media only |
| Database | PostGIS | Needs `GEOS_LIBRARY_PATH` / `GDAL_LIBRARY_PATH` |

DRF is configured with JWT-only authentication and a custom exception handler at `utils.custom_exception_handler`. There is no `DEFAULT_PERMISSION_CLASSES`, so views are open unless they declare otherwise — every market-data endpoint is intentionally public.

---

## utils/

| Module | Importers | Status |
|---|---|---|
| `StockCalculations.py` | 4 | **Live** — `GetData`, the S3 access layer. Fourth importer is `backtester/engine/prices.py` |
| `IndexFileMappers.py` | 2 | Imported, but the resulting `index_mappers` is unused at both sites |
| `custom_exception_handler.py` | 1 | Live, wired via `REST_FRAMEWORK` |
| `DailyFunctions.py` | 2 | Only imported by other dead modules |
| `UniverseCalculations.py` | 0 | **Dead.** Holds `CapitalMarketsDataPackage`, the v1 pickle-based ancestor of `/economic-data/` — useful as a reference for the payload contract |
| `Rankings.py`, `RunCovar.py`, `Technicals.py`, `PeerCalculations.py`, `uploadImages.py`, `error_views.py` | 0 | **Dead** |
| `legacy_code/GetPrices.py`, `legacy_code/IndexMaps.py`, `legacy_code/IndexYaml.py` | 0 | **Dead**, quarantined |

---

## Gaps & Notes

### 1. Three endpoints read superseded aggregates while fresh data sits unread

The highest-value fix in this document. `load_parquet_stock_profiles`, `load_long_profiles` and `load_financial_statements` in [StockCalculations.py](backend/utils/StockCalculations.py) point at v1 aggregate objects last written 2026-06-04/06. The v2 pipeline refreshed the same data on **2026-08-02** into per-symbol keys in the same prefixes — 13,448 `{SYM}_profile.parquet` and ~6,036 `{SYM}_{type}.parquet` per statement type — and nothing reads them.

For `/stock-profile/` and `/financial-statements/` the cutover is direct: both are already keyed by symbol and lazily cached per symbol, so reading `{SYM}_profile.parquet` replaces a 6.6 MB whole-file read with one small object. `load_stock_prices` is the pattern to copy.

`/company-profiles/` and `/universe-profiles/` need more care, because they are **bulk** consumers — `get_company_profiles` warms one `company:profiles:v1` blob containing every symbol, and `get_universe_profiles` filters that blob down to a universe's 500–3,500 members. Fetching 13,448 individual objects to rebuild it would be far worse than the single aggregate read it replaces. The clean version is to scan the per-symbol prefix as one pyarrow dataset inside the daily `company_profiles` task and build the same Redis blob from it, leaving both views untouched. Watch for the legacy `company_profiles.parquet` sitting in that prefix with a different schema — it needs excluding from the scan, or deleting once the cutover lands.

`index_data/index_prices_v1/` is a genuine pending cutover of the same kind (v2 uploaded, reader unchanged), though there the v1 files are still being maintained.

### 2. Nine of twelve Celery tasks have no schedule in version control

`CELERY_BEAT_SCHEDULE` contains three entries. The other nine tasks — including every market-hours-gated quote refresh — are registered (if at all) as `django_celery_beat.PeriodicTask` rows in the database, which are not in the repo. A fresh deployment gets a worker that can run them and a beat that never asks. Worth reconciling into settings or a documented fixture.

### 3. `get_index_charts` maps symbols by list position

[CorePerformanceTools.py](backend/analyzer/analyzer_utils/CorePerformanceTools.py) requests 5 symbols per call and then indexes `raw_dataframe_one[0]`, `[1]`, … assuming FMP returns them in request order. If FMP drops or reorders one, every chart after that point is mislabelled — and the result is cached for 24 hours. Mapping by the `symbol` field in each element would be a small, safe fix.

### 4. `index_data/contr_to_var/` has no reader

Eight per-index volatility-decomposition parquets are uploaded and unconsumed. Wiring them would follow the `/economic-data/` shape exactly.

### 5. Dead module-level S3 clients

`CorePerformanceTools.py` builds a module-level `fs = s3fs.S3FileSystem(...)` that is never used — and is exactly the fork-unsafe pattern `StockCalculations.get_fs()` exists to avoid. `StockCalculations.py` likewise builds an unused `s3 = boto3.resource("s3")`. Both should go; the live paths use `GetData.fs`.

### 6. `get_etf_universe_data` has an unreachable mapping

It builds an `exchanges` short-name → full-name dict and never uses it: the filter compares the caller's raw argument against FMP's full exchange names, so `'nyse'` and `'tsx'` silently return `[]`. `'nyse'` is also defined twice in that dict.

### 7. Missing request timeout

`get_heat_map_data` calls `requests.get(url)` with no timeout inside a batch loop. Every other outbound call in `CorePerformanceTools` passes `timeout=10`.

### 8. No response compression middleware

`GZipMiddleware` is not installed, so every endpoint except `/economic-data/` (which compresses itself) ships uncompressed JSON. Adding it would shrink several large payloads for free.

### 9. Hardcoded credentials in quarantined code and in notebooks

`utils/legacy_code/GetPrices.py` still contains a literal FMP key and FRED key. The module is dead and still untracked — strip these before it is ever committed, to avoid a history rewrite later.

Two notebooks in `class_files/` also carry live credentials in plaintext:

| File | Holds | Status |
|---|---|---|
| `class_files/portfolio_analyzer.ipynb` | FMP key (7 occurrences) | Superseded by `backtester/`. Scheduled for deletion in Task 20 of the backtest plan, after rotation |
| `class_files/homepage_data.ipynb` | FMP **and** AWS keys | **Outstanding.** Separate finding, not addressed by any current work |

**Verified 2026-08-13:** `backend/class_files/` is gitignored (`.gitignore:58`) and has **never** been tracked — `git log --all -- backend/class_files/` is empty. So neither key is in git history, and deleting a file genuinely removes its key rather than merely hiding it. That is the opposite of the usual leaked-credential situation and makes the cleanup much cheaper. Rotation is still warranted: both keys sat in plaintext on a developer machine and may have been synced or backed up.

The same gitignore rule means notebooks in `class_files/` cannot be committed — including the backtester's prototype notebook, which lives on disk only.

### 10. Sector snapshot assumes exactly 11 sectors

`get_sector_performance_snapshot` compares `greater_than_zero == 11` to decide the "All Sectors Are Positive" message. If FMP returns a different sector count for an exchange, that branch silently never fires.

### 11. `journal` is half-wired

Listed in `INSTALLED_APPS` with an empty `urls.py` and a commented-out include in the root URLconf.
