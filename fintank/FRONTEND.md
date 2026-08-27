# Fintank Frontend — State of Play

Context handoff document. Everything here was verified against source on **2026-08-03**;
where a claim is inherited rather than re-checked, it says so.

> **Update 2026-08-13 — no frontend work has shipped since.** The only change in flight is the
> portfolio backtester, and it is **backend-only so far**: the numerical engine is built and
> tested, the Django API and the whole UI are not. `/backtest-portfolio` still renders
> `ComingSoon`. See [Portfolio backtester](#portfolio-backtester--in-flight-backend-only).

**How to use this doc:** read "Architecture" and "Conventions & gotchas" first — they explain
why the code looks the way it does. Then jump to "Route inventory" or "Endpoint map" for
whatever you're touching. "Known broken" is the working list of what needs fixing next.

> ⚠️ `docs/FRONTEND_BREAKDOWN.md` is an earlier auto-generated survey and contains at least one
> **confirmed-wrong** claim (it says `/economic-data/` is unregistered; it is registered and live).
> Prefer this file. Treat that one as unverified.

---

## Stack

| Concern | Choice |
|---|---|
| Framework | Next.js 15.4.1, **Babel** (not SWC — `.babelrc` present) |
| Routing | Pages Router (primary) + App Router (Solana only) |
| State | Redux + redux-persist + redux-thunk (`src/store.js`) |
| Data fetching | SWR + axios in `src/hooks/` |
| Styling | Bootstrap 5 / react-bootstrap + SCSS |
| Charts | Chart.js (`react-chartjs-2`), ApexCharts, custom canvas in `src/utils/` |
| Backend | Django REST at `NEXT_PUBLIC_FINTANK_API_URL` (default `http://localhost:8000/api`) |

```bash
npm run dev            # http://localhost:8020
npm run build          # ⚠️ see "Build is memory-hungry" below
npm run lint
npm run format
```

**Path aliases** (`tsconfig.json`) — note there is **no `@components/*`**:

```
@/*                  ./src/*
@componentsLegacy/*  ./src/componentsLegacy/*
@utils/*             ./src/utils/*
@hooks/*             ./src/hooks/*
@data/*              ./src/data/*
@context/*           ./src/context/*
```

---

## Architecture

### Two routers coexist — do not mix them

- **`src/pages/`** — Pages Router. **All financial UI lives here.** Entry `_app.js`, wraps in
  Redux `Provider` → `PersistGate` → legacy `Layout`.
- **`src/app/`** — App Router. Solana dApp only (`/account`, `/counter`, `/dashboard`).
  Entry `layout.tsx` → `AppProviders` (wallet, React Query, theme) → `AppLayout`.

### Component directories

- **`src/componentsLegacy/`** — 80 `.js` files, Bootstrap + Chart.js. The real app.
  Subfolders: `Homepage/`, `Header/`, `StockDetail/`, `CapitalMarkets/`.
- **`src/components/`** — 34 `.tsx` files, shadcn/Tailwind, Solana wallet UI. App Router only.

These two share **zero component names**. Overlap is functional (header/footer/layout), not
duplication. Real duplication lives *inside* `componentsLegacy` (see "Known broken").

### Data flow

`Layout` reads `nav` and `title` off `pageProps`, so **every page must return those** from
`getStaticProps`/`getServerSideProps`.

Three patterns are in use, in decreasing order of preference:

1. **ISR** — `getStaticProps` + `revalidate`, wrapped in try/catch. Currently only
   `capital-markets.js`. **This is the pattern to copy.**
2. **SSR** — `getServerSideProps`. Used by `index.js`, `indexes/[slug].js`. Several are
   unguarded and will 500 the route if the backend hiccups.
3. **Client SWR** — hooks in `src/hooks/`, one hook per endpoint.

---

## Route inventory

| Route | File | Data source | Status |
|---|---|---|---|
| `/` | `index.js` | SSR: `gainers-losers/`, `get_articles/fmp` | working |
| `/capital-markets` | `capital-markets.js` | **ISR**: `economic-data/` | ✅ rebuilt 2026-08-03 |
| `/markets` | `markets.js` | `UseIndex`, `useEtf`, `useCryptoPerformance` | working |
| `/indexes/[slug]` | `indexes/[slug].js` | SSR: `getstockvaluations/` | ❌ **500s — endpoint doesn't exist** |
| `/universe/[slug]` | `universe/[slug].js` | `useUniverseProfiles` | working; slug mismatch (below) |
| `/stock-data/[ticker]` | `stock-data/[ticker].js` | `useStockData` (direct FMP) | working; rewire spec written |
| `/newsarticles/[slug]` | `newsarticles/[slug].js` | news API | working; raw `dangerouslySetInnerHTML` |
| `/user-account` | `user-account.js` | auth BFF | fixed 2026-08-03 (bad `Icon` import) |
| `/login`, `/signup`, `/completesignup` | — | Next API auth routes | working |
| `/about`, `/faq`, `/research-posts`, `/404` | — | static | working |
| `/backtest-portfolio` | `backtest-portfolio.js` | none yet | `ComingSoon` — [engine built, UI not started](#portfolio-backtester--in-flight-backend-only) |
| `/watchlist`, `/create-alerts` | — | none | `ComingSoon` |
| `/account`, `/counter`, `/dashboard` | `src/app/` | Solana | App Router |

**Next.js API routes** (`src/pages/api/`) act as a BFF: `auth/login|logout|user|userprofile`,
`auth/uploadImages|removeImages`, `articlefetcher`, `imagefetcher`.

---

## Backend endpoint map

All under `/api/`. Verified against `backend/*/urls.py`.

### Registered **and** consumed by the frontend

| Endpoint | App | Consumed by |
|---|---|---|
| `all-stock-names/` | analyzer | `useStockNames` (5 importers) |
| `index-performance/` | analyzer | `useHomeIndex`, `UseIndex` |
| `index-history/<symbol>/` | analyzer | `useIndexChart` |
| `etf-performance/` | analyzer | `useEtf` |
| `crypto-performance/` | analyzer | `useCryptoPerformance` |
| `gainers-losers/` | analyzer | `index.js` (inline SSR) |
| `sector-industry/<exchange>/` | analyzer | `UseSectorData` |
| `economic-data/` | analyzer | `capital-markets.js` (ISR) |
| `constituent-returns/<universe>/` | analyzer | `useIndexHeatMap` |
| `universe-profiles/<universe>/` | analyzer | `useUniverseProfiles` |
| `get_articles/<item>/` | news | `index.js` |

### Registered but **not yet consumed** — backend is ahead of the frontend

`company-profiles/<symbol>/`, `stock-profile/<symbol>/`, `stock-prices/<symbol>/`,
`stock-prices-monthly/<symbol>/`, `financial-statements/<symbol>/<statement_type>/`,
`financial-statements/<symbol>/<universe>/<statement_type>/`, `upload/<model_name>/` (stockuploader).

These are exactly what the **stock detail S3 rewire** spec is for —
`docs/superpowers/specs/2026-07-31-stock-detail-s3-rewire-design.md`.

### Auth

`auth/register/`, `users/me/`, `users/me/update/`, `users/me/change-password/`,
`users/me/profile/`, `users/me/profile/update/`, `users/me/profile/avatar/`,
`auth/token/`, `auth/token/refresh/`, `auth/token/verify/`, `auth/` (dj-rest-auth),
`auth/registration/`.

### Backend caching model

`analyzer/views.py` reads a gzipped JSON blob from Redis (`home:{type}:{qualifier}:v1`),
populated by Celery beat jobs. On cold cache the view rebuilds from S3 parquet
(`s3://thetradingfloor`) or live FMP. `economic-data/` is special: it returns the **raw gzip
bytes** when the client sends `Accept-Encoding: gzip`, skipping a decompress→parse→re-render
round trip on a ~460 KB payload.

---

## Hooks → endpoint status (43 hooks)

### ✅ Working

`useStockNames`, `useHomeIndex`, `UseIndex`, `useIndexChart`, `useEtf`,
`useCryptoPerformance`, `UseSectorData`, `useIndexHeatMap`, `useUniverseProfiles`

### ❌ Point at endpoints that do not exist

| Hook | Requests | Used by |
|---|---|---|
| `useTopPerformer` | `gettopperformers/<index>` | `indexes/[slug].js` |
| `useIndexMetrics` | `gettopperformers/<index>` | `indexes/[slug].js` |
| `useIndexPagePrices` | `getindexpageprices/<index>/` | `indexes/[slug].js` |
| `UseMovers` | `movers/` | unused (use `gainers-losers/`) |
| `UseSectorTS` | `sector-timeseries/<freq>/` | unused |
| `useHeatMap` | `heat-map` | unused |
| `useChartResources` | `gettopperformers/`, `index-prices/` | unused |
| `useLocationService` | `getgeocode/<address>` | unused |
| `useNewsGenerator` | `newsarticles/<topic>/` | unused (real one is `get_articles/`) |

### ⚠️ Call FMP directly from the browser

`useIndexPerformance`, `useStockData`, `useCommodityData`, `useETFData`, `useStockArticles`,
`useWatchList` — all interpolate `NEXT_PUBLIC_FMP_API` into the query string, so **the FMP key
ships in the client bundle.** Migrating these behind Django is unfinished work.

### Unused (20)

`UseHover`, `UseMovers`, `UseSectorTS`, `useAccounts`, `useAddChart`, `useCandleStick`,
`useChartResources`, `useChartUpdater`, `useCommodityData`, `useCovarWatchList`, `useETFData`,
`useHeatMap`, `useLocationService`, `useNewsGenerator`,
`useSectorExposure`, `useStockArticles`, `useStockCharts`, `useStockReturns`, `useWatchList`,
`useWatchListLineChart`

(`useNewCandleSticks` was deleted by the technical charting comparison rebuild;
`src/componentsLegacy/Comparison/PriceChart.js` renders candlesticks now.)

---

## Capital markets rebuild (2026-08-03) — the reference pattern

`/capital-markets` was rebuilt from ~1,380 lines across 4 files to ~350 lines + 2 JSON
registries. **Copy this structure for the other chart-heavy pages.**

```
src/data/capitalMarkets/economicSeries.json   13 × {id,dataKey,title,label,color,blurb}
src/data/capitalMarkets/equitySeries.json     20 × {id,packKey,title,label,color,blurb}
src/utils/capitalMarkets/chartOptions.js      ChartJS.register (once), shared options, frequencies
src/utils/capitalMarkets/chartBuilders.js     pure: buildLineChart, selectFrequencySeries
src/componentsLegacy/CapitalMarkets/
  TimeSeriesChartCard.js  FrequencySelect.js  ChartGrid.js
  EconomicSection.js      EquitySection.js
  LastUpdated.js          DataUnavailable.js
```

The ideas that carried the win:

1. **Chart definitions are data, not JSX.** 33 near-identical blocks collapsed into two JSON
   registries + one card component.
2. **Chart building is a pure function, not a hook.** The old `useCapitalMarketCharter` /
   `useEquitySpreadCharter` built charts inside effects that *also* set label/colour via
   `setState`, so charts were assembled from the previous render's values, and the equity one
   read a stale `selectedFrequency` — changing the dropdown drew the **previously** selected
   frequency. No state means nothing can be stale.
3. **One state map, not 20 `useState`.** `EquitySection` keeps `{[id]: frequency}`.
4. **ISR over SSR.** Data refreshes once daily via Celery; per-request SSR was repeat work.
   ISR also means a backend outage keeps serving the last good page instead of a 500.
5. **Only the active tab mounts**, so the inactive tab's Chart.js canvases are never created.

**Deleted:** `EquityCharts.js`, `EconomicCharts.js`, `useEquitySpreadChart.js`,
`useCapitalMarketsCharts.js`.

**Verified:** all 33 registry keys resolve against the live API; 20 canvases on the equity tab
and 13 on the economic tab; frequency changes redraw on the first interaction; per-chart state
stays independent; `gsp: true` confirms ISR.

**Not verified:** `next build` (see below).

**Backend contract** is documented in
`backend/analyzer/analyzer_utils/CorePerformanceTools.py` — `YIELD_SERIES_COLUMNS`,
`MACRO_SERIES_COLUMNS`, `RELATIVE_PERF_PACKS`. The registry `dataKey`/`packKey` values must
match those maps exactly.

---

## Portfolio backtester — in flight, backend only

**Nothing in this section is on screen yet.** Recorded here so the next person doesn't start the
UI from scratch or wire hooks the wrong way.

- **Design:** `docs/superpowers/specs/2026-08-11-portfolio-backtest-design.md`
- **Plan:** `docs/superpowers/plans/2026-08-11-portfolio-backtest.md` — 20 tasks, **1–10 done**
- **Branch:** `feat/portfolio-backtest`

Backend Tasks 1–10 delivered the numerical engine (190 tests). Tasks 11–14 build the Django API;
**Tasks 15–19 are the frontend and none of them has started.**

### The route already exists

`/backtest-portfolio` is live in the Pages Router, inside `ProfileLayout`, currently rendering
`ComingSoon`. Its `ProfileSideNav` entry carries `built: false`. The feature replaces that body —
**no new route is created**, deliberately, because the page is already wired into the profile nav
and carries the user's mental model. The platform spec's `src/pages/backtester.js` is explicitly
*not* to be built.

Do **not** delete `ComingSoon.js` when the flag comes off — `create-alerts.js` and `watchlist.js`
still render it.

### The one thing that will bite you: the JWT is httpOnly

`src/pages/api/auth/login.js:22-28` sets the `access` cookie with `httpOnly: true`. **Client JS
cannot read it**, so a hook cannot send `Authorization: Bearer` — and every authenticated call has
to go through a Next API route that reads the cookie server-side, the pattern
`src/pages/api/auth/userprofile.js` already uses.

The plan therefore adds **one catch-all proxy**, `src/pages/api/backtester/[...path].js`, rather
than nine near-identical BFF files. It forwards GET/POST/PATCH/DELETE and passes 402/410/422
bodies through verbatim (`validateStatus: () => true`), because the UI needs to read them:

| Status | Means |
|---|---|
| 402 | Free backtest allowance spent — render the upgrade prompt |
| 410 | Results expired from cache — offer a re-run |
| 422 | Bad request, or the run failed with a readable reason |

### Planned surface

Endpoints under `/api/backtester/` — `portfolios/`, `portfolios/<id>/`,
`portfolios/<id>/duplicate/`, `run/`, `status/<task_id>/`, `results/<task_id>/`, `history/`,
`search-symbols/`, `quota/`. **None routes yet.**

Hooks: `usePortfolios`, `useBacktestRun` (submit → poll 1s backing off to 3s → fetch),
`useSymbolSearch` (debounced), `useBacktestQuota`.

Components in `src/componentsLegacy/Backtest/` — twelve, `.js` not `.tsx`, Bootstrap +
ApexCharts to match the surrounding legacy tree. `react-apexcharts` must be dynamically imported
with `{ ssr: false }`, as in `Homepage/MoversSection.js:9`.

### Two UI rules from the spec, not stylistic preferences

1. **`critical` diagnostics render *above* the results, not below.** A backtest that is really a
   single-asset dot-com drawdown wearing a 60/40 label must say so before it shows the number.
   The engine already returns findings sorted critical-first.
2. **The allocation-over-time chart is not behind a disclosure.** It is where staggered inception
   becomes legible rather than merely disclosed, and it is the most informative view on the page.

Everything else advanced — optimizer choice, covariance method, constraints, costs, lookback, gap,
inception policy — sits behind an **Advanced settings** collapse. The defaults are meant to be good
enough that a novice can press Run within 30 seconds.

### Metering, and why it should not feel hostile

Three rules the UI has to reflect, or the meter reads as punitive:

- Re-running an **identical** request is free (served from cache, no credit spent) — so toggling a
  chart option costs nothing.
- Saving, loading, duplicating and deleting portfolios are **always** free. Only execution meters.
- Failed runs are refunded.

`QuotaBanner` shows remaining runs and says the second point out loud.

---

## Known broken / next targets

**1. `/indexes/[slug]` is down.** `getServerSideProps` fetches `getstockvaluations/<slug>`,
which is registered nowhere, with no try/catch — the route 500s. It also calls three dead
hooks (`useIndexPagePrices` ×2, `useTopPerformer`, `useIndexMetrics`) and one direct-FMP hook.
**This is the natural next job, and it's the same shape as the capital-markets fix.**

**2. Universe slug mismatch.** `@data/universe.json` offers
`allstocks, commodities, cryptos, dj, etfs, eurostocks, nasdaq, sp500, sptsx`; the backend's
`UNIVERSE_PROFILE_SLUGS` are
`sp500, nasdaq, tsx, tsx_small_cap, r2000, rmicro, msci_eafe, msci_sm, etfs`. Only
`sp500, nasdaq, etfs` overlap — the other six 400.

In practice `menu.json` links just four of them (`/universe/sp500`, `/universe/nasdaq`,
`/universe/etfs`, `/universe/dj`), so **`dj` is the only user-reachable break**. The backend
also exposes six universes the frontend never surfaces (`tsx`, `tsx_small_cap`, `r2000`,
`rmicro`, `msci_eafe`, `msci_sm`) — cheap win to add.

**3. Dead routes linked from live UI** *(inherited, not re-verified)*: `/index-chart/<symbol>`,
`/stocks/<symbol>` (real route is `/stock-data/`), `/screener`, `/comm-data/[ticker]`.

**4. FMP key in the client bundle.** See the ⚠️ hook list above.

**5. Auth token refresh never happens.** The login BFF stores only the `access` token and never
calls the registered `TokenRefreshView`, so sessions go stale silently *(inherited)*.

**6. Duplication inside `componentsLegacy`** *(inherited)*: `Sentiments.js` ≈ `PriceTarget.js`
(both declare `const MoverReturns`), and three copies of the same paginator.

---

## Conventions & gotchas

**Nothing server-renders.** `_app.js` wraps everything in redux-persist's `PersistGate`, which
renders `null` on the server. The served HTML has an **empty `<div id="__next">`** for every
Pages Router route. Consequences:

- You cannot verify a page by curling it — use a browser.
- SSR/ISR buys **no** first-paint or SEO benefit today. It still avoids per-request backend work
  and removes the 500 risk, which is why `capital-markets` uses it.
- Shipping large props is pure transfer cost. Next warns that `/capital-markets` page data is
  **2.33 MB**. Splitting `economic-data/` per tab, or fetching client-side, is the open
  improvement here.

**Build is memory-hungry.** `npm run build` gets OOM-killed on a machine with ~1.2 GB free, even
with `--max-old-space-size=6144`. A killed build **wipes `.next/`**, which breaks any running dev
server until it's restarted. If a dev server starts 500ing on every route with
`ENOENT: routes-manifest.json`, that's what happened — restart it.

**Always return `nav` and `title`** from a page's props function, or `Layout` renders wrong.

**Hydration:** format dates deterministically (UTC), not with `toLocaleString`. See
`LastUpdated.js`.

**react-select** needs the whole `{value,label}` option as `value`, not a bare string. Passing a
string is why older code fakes the selection through `placeholder`.

---

## Related docs

| Path | What |
|---|---|
| `CLAUDE.md` | Repo-wide guidance, commands, env vars |
| `docs/BACKEND_BREAKDOWN.md` | Django side |
| `docs/FRONTEND_BREAKDOWN.md` | Earlier survey — **contains errors**, prefer this file |
| `docs/superpowers/specs/2026-07-31-stock-detail-s3-rewire-design.md` | Next planned feature |
| `docs/superpowers/specs/2026-08-11-portfolio-backtest-design.md` | Portfolio backtester — in flight |
| `docs/superpowers/plans/2026-08-11-portfolio-backtest.md` | Its 20-task plan; 1–10 done, frontend is 15–19 |
| `docs/superpowers/specs/2026-06-15-markets-universe-toggle-design.md` | Shipped |
| `docs/superpowers/plans/2026-06-07-homepage-component-refactor.md` | Shipped |
| `specs/homepage_data_calls.md` | Homepage data contract |
