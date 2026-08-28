# Fintank Frontend Breakdown

A map of the Next.js frontend at the repo root and how it connects to the Django REST backend in `backend/`.

Everything below was read from source. Endpoint paths are only stated where they were verified in both the frontend caller and `backend/*/urls.py`; anything that could not be matched is listed under [Gaps & Notes](#gapsnotes) rather than assumed to exist.

**Counts:** 13 route pages (Pages Router) + 4 pages (App Router) · 8 API routes · 74 legacy components · 45 hooks · 24 registered backend URL patterns (+ `dj-rest-auth` includes).

---

## Overview

### Two coexisting routing systems

| System | Directory | Entry | What lives there |
|---|---|---|---|
| **Pages Router** (legacy, primary) | [src/pages/](src/pages/) | [_app.js](src/pages/_app.js) | All financial UI: homepage, markets, capital markets, stock detail, universe screener, news, auth |
| **App Router** (new) | [src/app/](src/app/) | [layout.tsx](src/app/layout.tsx) | Solana dApp only: `/account`, `/counter`, and a `DashboardFeature` at `/` |

The two overlap at `/`: [src/pages/index.js](src/pages/index.js) (Pages Router) wins for the root route, and [src/app/dashboard/page.tsx](src/app/dashboard/page.tsx) is effectively unreachable. See Gaps.

`_app.js` wraps every Pages Router page in: Redux `Provider` → `PersistGate` → `DjangoAuthProvider` → legacy `Layout`. `app/layout.tsx` wraps App Router pages in `AppProviders` (Solana wallet + React Query + theme) → `AppLayout`. The two provider trees never meet.

### State management

- **Redux** — [src/store.js](src/store.js): `legacy_createStore` + `redux-persist` (localStorage, key `root`) + `next-redux-wrapper`, middleware `redux-thunk` + `redux-promise`, devtools via `redux-devtools-extension`.
- **Reducers** — [rootReducer.js](src/reducers/rootReducer.js) combines `idx` ([idxData.js](src/reducers/idxData.js), a no-op stub), `screener` ([screenerReducer.js](src/reducers/screenerReducer.js)), `bucket` ([bucketReducer.js](src/reducers/bucketReducer.js)). [fmp.js](src/reducers/fmp.js) exists but is commented out of the root reducer.
- **Actions** — [screenerAction.js](src/actions/screenerAction.js) (POSTs a screen), [bucketAction.js](src/actions/bucketAction.js) (pure payload passthrough).
- **React Context** — [src/context/authContext.js](src/context/authContext.js) holds the actual auth state (`DjangoAuthContext`), *not* Redux. Also `accountContext.js`, `screenerContext.js`.
- **SWR** — most data hooks use `swr` / `swr/immutable`. Redux is not used for market data.

### Styling & charts

- **Bootstrap** via `react-bootstrap` + SCSS at `src/scss/style.default.scss`
- **Chart.js** via `react-chartjs-2` — homepage index charts, stock detail, capital markets
- **ApexCharts** via `react-apexcharts` (dynamically imported, `ssr: false`) — treemap heat map, candlesticks
- **Swiper** for carousels, `react-select` for dropdowns, `sweetalert` for alerts, `dompurify` for news HTML
- **Tailwind + shadcn/ui** (`src/components/ui/*.tsx`) — App Router side only

### API base URL

All Django calls go through **`process.env.NEXT_PUBLIC_FINTANK_API_URL`** (default `http://localhost:8000/api`, only defaulted in [src/utils/stockApi.js](src/utils/stockApi.js); every other caller assumes it is set).

A second family of hooks bypasses Django entirely and calls FMP directly using `NEXT_PUBLIC_FMP_*` env vars — see [Gaps](#3-hooks-that-bypass-django-and-call-fmp-directly).

### Path aliases (from `jsconfig.json`)

`@/*` → `src/*` · `@componentsLegacy/*` · `@utils/*` · `@hooks/*` · `@data/*` · `@context/*` · `@project/anchor` → `anchor/src`

---

## Pages (Pages Router)

| Route | File | Renders | Components used | Data source |
|---|---|---|---|---|
| `/` | [index.js](src/pages/index.js) | Homepage: hero carousel, index charts grid, sector performance, movers + heat map, news grid, jumbotron | `RichSwiper`, `IndexReturnsSidePanel`, `IndexChartsSection`, `SectorPerformanceSection`, `MoversSection`, `NewsSection`, `JumbotronSection` | `getServerSideProps` → `GET /api/gainers-losers/` and `GET /api/get_articles/fmp`; children fetch client-side |
| `/markets` | [markets.js](src/pages/markets.js) | Quote cards for Equity / Crypto / ETF, toggled by a pill button group | react-bootstrap only | `useIndex`, `useEtfPerformance`, `useCryptoPerformance` → `/index-performance/`, `/etf-performance/`, `/crypto-performance/` |
| `/capital-markets` | [capital-markets.js](src/pages/capital-markets.js) | Hero + index-returns swiper + tabbed equity-spread / economic charts | `Swiper`, `EquityCharts`, `EconomicCharts` | `getServerSideProps` → `/economic-data/`; also `useHomeIndex`, `useStockNames` |
| `/stock-data/[ticker]` | [stock-data/[ticker].js](src/pages/stock-data/[ticker].js) | Stock detail: profile header, price + MA chart, momentum panels, statements, sector news. Renders its own "Symbol not found" body with a 404 status rather than `notFound: true` | `StockHeader`, `PriceChart`, `MomentumCharts`, `StatementsSection`, `SectorNews` | SSR via `fetchProfile` → `/stock-profile/<symbol>/` and `fetchPrices` → `/stock-prices/<symbol>/`; children lazy-load statements + news |
| `/universe/[slug]` | [universe/[slug].js](src/pages/universe/[slug].js) | Universe constituent list with ticker autocomplete, sector filter, and a modal stock screener form. Redux-connected | `StockListPagination`, `react-select` | `useUniverseProfiles` → `/universe-profiles/<slug>/`; `useStockNames` → `/all-stock-names/`; screener submit → `screenerAction` (POST `/screen/`, **not registered**) |
| `/newsarticles/[slug]` | [newsarticles/[slug].js](src/pages/newsarticles/[slug].js) | News topic page: hero banner, featured block stories, image carousel, text-only list, in-place article modal | `Swiper`, `PopularCities`, `ArticleModal`, `CustomImage` | `getServerSideProps` → `GET /api/get_articles/<topic>/` |
| `/login` | [login.js](src/pages/login.js) | Sign-in split screen. Firebase email/password + Google popup, then hands credentials to `DjangoAuthContext.login()` | `CustomImage`, `Icon` | `POST /api/auth/login` (BFF) → Django `POST /api/auth/token/` |
| `/signup` | [signup.js](src/pages/signup.js) | Email-link signup — sends a Firebase sign-in link, stores email in `localStorage` | `CustomImage`, `Icon` | Firebase only |
| `/completesignup` | [completesignup.js](src/pages/completesignup.js) | Completes the Firebase email-link flow, sets a password, then registers with Django | `CustomImage`, `Icon` | `DjangoAuthContext.register()` → `POST /api/auth/register/` |
| `/user-account` | [user-account.js](src/pages/user-account.js) | Static dashboard tile grid from `@data/user-account.json` | `Icon` (**imported from `@components/Icon`, which does not exist — see Gaps**) | none |
| `/about` | [about.js](src/pages/about.js) | Team page: hero, founder cards, quote block | `CardTeam`, `CustomImage` | static `@data/team.json` |
| `/faq` | [faq.js](src/pages/faq.js) | FAQ grouped into two-column question blocks | `CustomImage` | static `@data/faq.json` |
| `/404` | [404.js](src/pages/404.js) | Pages Router not-found boundary. Exists specifically so `notFound: true` doesn't fall through to the App Router (which has no not-found boundary and 500s) | react-bootstrap | none |

Framework files: [_app.js](src/pages/_app.js) (provider tree), [_document.js](src/pages/_document.js) (fonts, favicon, OG meta).

### API routes (`src/pages/api/`)

These are Next.js server handlers, not Django.

| Route | File | Purpose |
|---|---|---|
| `POST /api/auth/login` | [auth/login.js](src/pages/api/auth/login.js) | BFF: proxies `{username, password}` to Django `POST /api/auth/token/`, stores the `access` JWT in an httpOnly `access` cookie (5 days, SameSite=Lax) |
| `POST /api/auth/logout` | [auth/logout.js](src/pages/api/auth/logout.js) | Clears the `access` cookie |
| `GET /api/auth/user` | [auth/user.js](src/pages/api/auth/user.js) | Reads the cookie, calls Django `GET /api/users/me/` with `Authorization: Bearer` |
| `GET /api/auth/userprofile` | [auth/userprofile.js](src/pages/api/auth/userprofile.js) | Same pattern against `GET /api/users/me/profile/` |
| `POST /api/auth/uploadImages` | [auth/uploadImages.js](src/pages/api/auth/uploadImages.js) | Base64 → S3 `thetradingfloor` upload via `aws-sdk` |
| `POST /api/auth/removeImages` | [auth/removeImages.js](src/pages/api/auth/removeImages.js) | S3 `deleteObject` |
| `GET /api/imagefetcher?url=` | [imagefetcher.js](src/pages/api/imagefetcher.js) | Image proxy for third-party news thumbnails (Content-Type checked, 1-day cache) |
| `GET /api/articlefetcher?url=` | [articlefetcher.js](src/pages/api/articlefetcher.js) | Reader-mode extraction via `@extractus/article-extractor`; SSRF guard, 10s timeout, 3 MB cap, in-memory LRU (100 entries / 1 h) |

The JWT lives in an httpOnly cookie and is read server-side by these BFF routes — no component reads a token from `localStorage`.

### App Router pages

| Route | File | Renders |
|---|---|---|
| `/` (shadowed) | [app/dashboard/page.tsx](src/app/dashboard/page.tsx) | `DashboardFeature` — unreachable, `pages/index.js` takes `/` |
| `/account` | [app/account/page.tsx](src/app/account/page.tsx) | `AccountListFeature` — Solana wallet account list |
| `/account/[address]` | [app/account/[address]/page.tsx](src/app/account/[address]/page.tsx) | `AccountDetailFeature` |
| `/counter` | [app/counter/page.tsx](src/app/counter/page.tsx) | `CounterFeature` — Anchor counter program scaffold |

---

## componentsLegacy

74 `.js` files. Backend dependency is listed only where the component (or a hook it calls) actually reaches Django.

### Homepage sections — [src/componentsLegacy/Homepage/](src/componentsLegacy/Homepage/)

| Component | What it does | Backend |
|---|---|---|
| [IndexChartsSection.js](src/componentsLegacy/Homepage/IndexChartsSection.js) | 5×3 grid of index charts. Registers the Chart.js scales/elements once, then renders `IndexChartCard` per slug (`sp500`, `nas`, `dj`, `rus_1000`, `tsx`, `tsx_60`, `rus_2000`, `ftse`, `nik`, `nsei`, `hsi`, `vix`, `short_term`, `ten_year`, `thirty_year`) | via child |
| [IndexChartCard.js](src/componentsLegacy/Homepage/IndexChartCard.js) | One combo chart (price line + volume bars) plus a colored latest-price footer, green/red by last-vs-previous close | `useIndexCharter` → `GET /api/index-history/<symbol>/` |
| [IndexReturnsSidePanel.js](src/componentsLegacy/Homepage/IndexReturnsSidePanel.js) | Floating dark glass panel over the hero with the first 7 index quotes; each links to `/index-chart/<symbol>` (**route does not exist**) | `useHomeIndex` → `GET /api/index-performance/` |
| [IndexReturnsSection.js](src/componentsLegacy/Homepage/IndexReturnsSection.js) | Full-width swiper of index return cards. Not imported by any page — superseded by the side panel | `useHomeIndex` → `GET /api/index-performance/` |
| [SectorPerformanceSection.js](src/componentsLegacy/Homepage/SectorPerformanceSection.js) | Exchange picker (NASDAQ/NYSE/AMEX/TSX/LSE) driving a tile grid of average sector change, with an up/down background image per tile | `useSectorData` → `GET /api/sector-industry/<exchange>/` |
| [MoversSection.js](src/componentsLegacy/Homepage/MoversSection.js) | Gainers swiper + losers swiper + an ApexCharts treemap heat map with an index selector; handles loading/empty states for the treemap | `useIndexHeatMaps` → `GET /api/constituent-returns/<universe>/`; movers data passed down from the page's SSR `gainers-losers` call |
| [NewsSection.js](src/componentsLegacy/Homepage/NewsSection.js) | Grid of up to 64 `NewsPost` cards; clicking one opens `ArticleModal` in place | articles passed as props from SSR `get_articles/fmp` |
| [JumbotronSection.js](src/componentsLegacy/Homepage/JumbotronSection.js) | Full-bleed CTA with a "Discover A Company" button that routes to a random NASDAQ/TSX/NYSE/CBOE ticker | `useStockNames` → `GET /api/all-stock-names/` |
| [HeroSection.js](src/componentsLegacy/Homepage/HeroSection.js) | Hero slider + random-ticker button. Not imported by any page (the homepage inlines `RichSwiper` instead) | `useStockNames` → `GET /api/all-stock-names/` |

### Stock detail — [src/componentsLegacy/StockDetail/](src/componentsLegacy/StockDetail/)

| Component | What it does | Backend |
|---|---|---|
| [StockHeader.js](src/componentsLegacy/StockDetail/StockHeader.js) | Name/symbol headline, exchange · country, "data as of" badge, sector / market cap / employees / beta list, description, website link | profile from page SSR |
| [PriceChart.js](src/componentsLegacy/StockDetail/PriceChart.js) | Adjusted-close line plus up to 4 moving averages, chosen by priority and filtered to series that actually carry data; tells the user how many MAs were hidden | series from page SSR |
| [MomentumCharts.js](src/componentsLegacy/StockDetail/MomentumCharts.js) | Four independent panels (rolling returns, up/down day ratio, return-to-risk, volatility), each on its own axis; panels with no data are dropped | series from page SSR |
| [StatementsSection.js](src/componentsLegacy/StockDetail/StatementsSection.js) | Click-to-load statements with income / balance sheet / cash flow tabs, 12 periods, curated headline rows, and a distinct message for 404 vs other errors | `useFinancialStatements` → `GET /api/financial-statements/<symbol>/<statement_type>/` |
| [SectorNews.js](src/componentsLegacy/StockDetail/SectorNews.js) | Six sector-news cards, explicitly labelled as sector (not company) coverage since the feed is keyed by topic | `fetchSectorNews` → `GET /api/get_articles/<category>/` |
| [chartTheme.js](src/componentsLegacy/StockDetail/chartTheme.js) | Shared chart styling: a fixed 4-color CVD-validated categorical palette, ink reference color, `lineDataset`/`baseOptions` factories, `asPercent`/`asRatio`/`asPrice` formatters | — |

### Layout & navigation

| Component | What it does | Backend |
|---|---|---|
| [Layout.js](src/componentsLegacy/Layout.js) | Page shell: `SSRProvider`, `Head` (title/favicon), route progress bar, conditional Header/Footer, optional `FormProvider`/`BookingProvider`, SVG sprite | — |
| [Header/index.js](src/componentsLegacy/Header/index.js) | Navbar from `@data/menu.json`; highlights the active dropdown parent, hides items marked `hideToLoggedUser`, swaps in `UserMenu` when authenticated | reads `DjangoAuthContext` |
| [Header/SearchForm.js](src/componentsLegacy/Header/SearchForm.js) | Ticker autocomplete (symbol or name substring), keyboard navigation, routes to `/stock-data/<ticker>` | `useStockNames` → `GET /api/all-stock-names/` |
| [Header/UserMenu.js](src/componentsLegacy/Header/UserMenu.js) | Avatar dropdown from `@data/user-menu.json` + logout (Firebase `signOut` then `DjangoAuthContext.logout()`) | `POST /api/auth/logout` (BFF) |
| [Header/DropdownMenuItem.js](src/componentsLegacy/Header/DropdownMenuItem.js) | Renders simple dropdowns and multi-column megamenus with icons/images | — |
| [Footer.js](src/componentsLegacy/Footer.js) | Multi-column footer from `@data/footer.json` + newsletter input + social icons | — |
| [ActiveLink.js](src/componentsLegacy/ActiveLink.js) | `next/link` wrapper that applies `activeClassName` when `asPath` matches | — |
| [NextNProgress.js](src/componentsLegacy/NextNProgress.js) | NProgress bar bound to router events | — |
| [SvgIcons.js](src/componentsLegacy/SvgIcons.js) / [Icon.js](src/componentsLegacy/Icon.js) | Injects the Orion SVG sprite; `Icon` renders `<use xlink:href="#id">` | — |
| [CustomImage.js](src/componentsLegacy/CustomImage.js) | Swaps `next/image` for a plain `<img>` when `production_type === "static"`. The most-reused component in the tree (26 importers) | — |

### Charts (market/economic)

| Component | What it does | Backend |
|---|---|---|
| [EquityCharts.js](src/componentsLegacy/EquityCharts.js) | ~750 lines of equity spread charts (EAFE, ACWI, Russell, S&P vs Nasdaq, sector-vs-total-market, TSX cuts) with a Quarterly/Yearly/Three-Year frequency selector | consumes props from the `capital-markets` SSR payload; `useEquitySpreadCharter` is a pure transform |
| [EconomicCharts.js](src/componentsLegacy/EconomicCharts.js) | Yield curve, spread and macro charts (10Y/5Y/2Y/30Y, MLHY, 2v10, CPI, UNEMP, NONFARM) | same SSR payload; `useCapitalMarketCharter` is a pure transform |
| [MetricsTable.js](src/componentsLegacy/MetricsTable.js) | Transposed fundamentals table (date/period rows, per-share metrics). **Unused** | — |
| [ValuationTable.js](src/componentsLegacy/ValuationTable.js) | P/E, EPS, % change, price, market cap table linking to `/stock-data/[ticker]`. **Unused** | — |

### Cards & tiles

| Component | What it does |
|---|---|
| [MarketReturns.js](src/componentsLegacy/MarketReturns.js) | Index quote card with a large trend arrow, symbol/name, and change % |
| [MoverReturns.js](src/componentsLegacy/MoverReturns.js) | Compact gainer/loser card (same shape, 3x arrow) |
| [PriceTarget.js](src/componentsLegacy/PriceTarget.js) | Analyst-grade card keyed on `newGrade` (Buy/Overweight/Outperform → green) |
| [Sentiments.js](src/componentsLegacy/Sentiments.js) | Near-duplicate of `PriceTarget` — same internal name `MoverReturns`, same grade logic |
| [CardNews.js](src/componentsLegacy/CardNews.js) | News card that routes its thumbnail through `/api/imagefetcher`, falls back to a static market image, and reports load failures via `onImageError` so the parent can demote the article |
| [NewsPost.js](src/componentsLegacy/NewsPost.js) | Homepage news card; strips HTML tags from the teaser and supports in-place modal open |
| [ArticleModal.js](src/componentsLegacy/ArticleModal.js) | Reader-mode modal. Normalizes the differing article shapes (bing/fmp/stock/crypto), fetches full text from `/api/articlefetcher`, **sanitizes with DOMPurify** against a tag/attr allowlist and forces `target=_blank rel=noopener` on links |
| [Avatar.js](src/componentsLegacy/Avatar.js) | Sized circular avatar (xxs→xxl), image or initials |
| [Stars.js](src/componentsLegacy/Stars.js) | 5-star rating row |
| [CardTeam.js](src/componentsLegacy/CardTeam.js) | Team member card — used by `/about` |
| [CardPoster.js](src/componentsLegacy/CardPoster.js), [CardProperty.js](src/componentsLegacy/CardProperty.js), [CardRestaurant.js](src/componentsLegacy/CardRestaurant.js), [CardRoom.js](src/componentsLegacy/CardRoom.js), [CardReview.js](src/componentsLegacy/CardReview.js), [CardTestimonial.js](src/componentsLegacy/CardTestimonial.js), [CardPost.js](src/componentsLegacy/CardPost.js) | Travel/directory template leftovers. Only reachable through `Swiper` variant props; `CardPost` has no importer at all |

### Carousels & galleries

| Component | What it does |
|---|---|
| [Swiper.js](src/componentsLegacy/Swiper.js) | The workhorse carousel. A boolean prop picks the slide renderer: `indexReturns`→`MarketReturns`, `moverReturns`→`MoverReturns`, `newsCards`→`CardNews`, plus `cards`/`imgCards`/`simple` template variants |
| [RichSwiper.js](src/componentsLegacy/RichSwiper.js) | Parallax + fade hero slider with overlay content — the homepage hero |
| [SwiperGallery.js](src/componentsLegacy/SwiperGallery.js) | Lightbox gallery (`yet-another-react-lightbox`). **Unused** |
| [SwiperTestimonial.js](src/componentsLegacy/SwiperTestimonial.js), [Gallery.js](src/componentsLegacy/Gallery.js), [Instagram.js](src/componentsLegacy/Instagram.js), [Brands.js](src/componentsLegacy/Brands.js) | Template carousels/grids; only `Brands` still has an importer |

### Pagination & lists

| Component | What it does |
|---|---|
| [StockPagination.js](src/componentsLegacy/StockPagination.js) | The live one — paginated universe constituent list (`react-paginate`), 20/page, scroll-to-top, `-` placeholder for null fields, links to `/stock-data/[ticker]` |
| [ScreenerPagination.js](src/componentsLegacy/ScreenerPagination.js) | Same pattern for screener results |
| [CommodPagination.js](src/componentsLegacy/CommodPagination.js) | Same pattern, switches to `/comm-data/[ticker]` on the `/commodity` route. **Unused, and neither route exists** |
| [RankingPagination.js](src/componentsLegacy/RankingPagination.js) | Bucketed factor-ranking list. **Unused** — also exports a stray `getStaticProps` that does nothing outside `pages/` |
| [Pagination.js](src/componentsLegacy/Pagination.js) | Hardcoded 1-2-3 pager. **Unused**, and the file ends with a stray `s` character after the export |

### Search, filters & forms

| Component | What it does |
|---|---|
| [Screener.js](src/componentsLegacy/Screener.js) | Redux-connected screener results view. **Unused** — the screener form now lives inline in `universe/[slug].js` and opens a `/screener` page that doesn't exist |
| [SearchBar.js](src/componentsLegacy/SearchBar.js) | Styled ticker search bar with custom `react-select` styling |
| [SortBy.js](src/componentsLegacy/SortBy.js) | Sort dropdown |
| [ResultsTopBar.js](src/componentsLegacy/ResultsTopBar.js) | Results count + sort row. **Unused**, and the count is hardcoded to `12` |
| [ReviewForm.js](src/componentsLegacy/ReviewForm.js), [Reviews.js](src/componentsLegacy/Reviews.js) | Review collapse form and list. **Unused** |

### Context providers & misc

| Component | What it does |
|---|---|
| [FormContext.js](src/componentsLegacy/FormContext.js), [BookingContext.js](src/componentsLegacy/BookingContext.js) | Empty `useState` contexts consumed only by `Layout`'s conditional wrappers |
| [PopularCities.js](src/componentsLegacy/PopularCities.js) | Repurposed as the news "featured block stories" grid on `/newsarticles/[slug]` |
| [Discover.js](src/componentsLegacy/Discover.js) | Icon + copy feature blocks |
| [Guides.js](src/componentsLegacy/Guides.js), [LastMinute.js](src/componentsLegacy/LastMinute.js), [Support.js](src/componentsLegacy/Support.js) | Template marketing sections. **Unused** |
| [Map.js](src/componentsLegacy/Map.js) / [MapLeaflet.js](src/componentsLegacy/MapLeaflet.js) | Leaflet map, dynamically imported with `ssr: false`, drag/tap disabled under 700px. **Unused** — no page renders a map |

---

## Hooks → backend endpoint mapping

### A. Hooks that hit the Django API (verified against `backend/analyzer/urls.py` and `backend/news/urls.py`)

| Hook | File | Method + path | Django view | Returns |
|---|---|---|---|---|
| `useStockNames` | [useStockNames.js](src/hooks/useStockNames.js) | `GET /api/all-stock-names/` | `analyzer.views.get_all_stock_names_available` | `{stocks: [{symbol, name, exchange, exchange_short_name, universe}]}` |
| `useIndexCharter` | [useIndexChart.js](src/hooks/useIndexChart.js) | `GET /api/index-history/<symbol>/` | `analyzer.views.get_index_history_task` | `{data: {dates, prices, volume}, index_name}` → built into a Chart.js combo config |
| `useIndex` | [UseIndex.js](src/hooks/UseIndex.js) | `GET /api/index-performance/` | `analyzer.views.get_index_performance_task` | Array of index quotes (unwraps `.data` if present); 10 min refresh |
| `useHomeIndex` | [useHomeIndex.js](src/hooks/useHomeIndex.js) | `GET /api/index-performance/` | same | Raw response (`{data: [...]}`); 20 s refresh |
| `useEtfPerformance` | [useEtf.js](src/hooks/useEtf.js) | `GET /api/etf-performance/` | `analyzer.views.get_etf_performance_task` | Array of ETF quotes; 10 min refresh |
| `useCryptoPerformance` | [useCryptoPerformance.js](src/hooks/useCryptoPerformance.js) | `GET /api/crypto-performance/` | `analyzer.views.get_crypto_performance_task` | Array of crypto quotes; 10 min refresh |
| `useSectorData` | [UseSectorData.js](src/hooks/UseSectorData.js) | `GET /api/sector-industry/<exchange>/` | `analyzer.views.get_sector_industry_task` | `{message, sectors: [{sector, averageChange}], ...}`; 15 min refresh |
| `useIndexHeatMaps` | [useIndexHeatMap.js](src/hooks/useIndexHeatMap.js) | `GET /api/constituent-returns/<universe>/` | `analyzer.views.get_constituent_returns` | `{universe_data, heat_map}` → ApexCharts treemap series + options |
| `useUniverseProfiles` | [useUniverseProfiles.js](src/hooks/useUniverseProfiles.js) | `GET /api/universe-profiles/<slug>/` | `analyzer.views.get_universe_profiles_task` | `{universe, count, data: [{symbol, name, sector, industry, market_cap, country, beta, exchange_short_name, is_etf, last_range}], last_updated}` |
| `useFinancialStatements` | [useFinancialStatements.js](src/hooks/useFinancialStatements.js) via [stockApi.js](src/utils/stockApi.js) | `GET /api/financial-statements/<symbol>/<statement_type>/` | `analyzer.views.get_financial_statements_auto` | `{data: [...rows], universe}`; deferred behind a null SWR key until the section is opened |
| — (`fetchProfile`) | [stockApi.js](src/utils/stockApi.js) | `GET /api/stock-profile/<symbol>/` | `analyzer.views.get_stock_long_profile` | Long profile: symbol, name, isin, cusip, exchange_short_name, sector, country, no_of_employees, description, beta, market_cap, website, ceo, image |
| — (`fetchPrices`) | [stockApi.js](src/utils/stockApi.js) | `GET /api/stock-prices/<symbol>/` | `analyzer.views.get_stock_price_data` | `{dates, series: {adjClose, 10/20/50/200_day_ma, 30/60_day_returns, up_down_days_*, *_return_to_risk, *_volatility}}` |
| — (`fetchSectorNews`) | [stockApi.js](src/utils/stockApi.js) | `GET /api/get_articles/<category>/` | `news.views.get_articles` | Array of articles `{title, link, snippet, thumbnail, source, date}` |
| — (page SSR) | [index.js](src/pages/index.js) | `GET /api/gainers-losers/` | `analyzer.views.get_gainers_losers_task` | `{gainers: [...], losers: [...]}` |
| — (page SSR) | [index.js](src/pages/index.js), [newsarticles/[slug].js](src/pages/newsarticles/[slug].js) | `GET /api/get_articles/<item>/` | `news.views.get_articles` | Array of articles |
| — (auth) | [authContext.js](src/context/authContext.js) | `POST /api/auth/register/` | `users.views.register` | `{message, user}` |
| — (BFF) | [api/auth/login.js](src/pages/api/auth/login.js) | `POST /api/auth/token/` | `TokenObtainPairView` | `{access, refresh}` |
| — (BFF) | [api/auth/user.js](src/pages/api/auth/user.js) | `GET /api/users/me/` | `users.views.get_current_user` | `UserSerializer` |
| — (BFF) | [api/auth/userprofile.js](src/pages/api/auth/userprofile.js) | `GET /api/users/me/profile/` | `users.views.get_current_user_profile` | `UserProfileSerializer` |

`stockApi.js` also defines `StockApiError` with an `isNotFound` getter, which is what lets the stock page distinguish "unknown symbol" from a real failure.

### B. Hooks calling Django paths that are NOT registered

These will 404 against the current backend. Flagged rather than documented as working endpoints.

| Hook | File | Path it calls |
|---|---|---|
| `useMoversData` | [UseMovers.js](src/hooks/UseMovers.js) | `GET {API}/movers/` |
| `useHeatMap` | [useHeatMap.js](src/hooks/useHeatMap.js) | `GET {API}/heat-map` |
| `useTopPerformers` | [useTopPerformer.js](src/hooks/useTopPerformer.js) | `GET {API}/gettopperformers/<index>` |
| `useIndexPagePrices` | [useIndexPagePrices.js](src/hooks/useIndexPagePrices.js) | `GET {API}/getindexpageprices/<index>/` |
| `useNewsGenerator` | [useNewsGenerator.js](src/hooks/useNewsGenerator.js) | `GET {API}/newsarticles/<topic>/` (the real one is `/get_articles/<item>/`) |
| `useLocationService` | [useLocationService.js](src/hooks/useLocationService.js) | `GET {API}/getgeocode/<address>` |
| `useSectorReturnTS` | [UseSectorTS.js](src/hooks/UseSectorTS.js) | `GET {API}/sector-timeseries/<frequency>/` |
| `useChartResource` | [useChartResources.js](src/hooks/useChartResources.js) | `GET {API}/index-prices/<v>` or `{API}/other-asset-prices/<v>` |
| `useIndexMetric` | [useIndexMetrics.js](src/hooks/useIndexMetrics.js) | `GET {API}/<ep>/<index>` — endpoint segment is a caller-supplied string, so nothing can be verified |
| `screenerAction` | [screenerAction.js](src/actions/screenerAction.js) | `POST {API}/screen/` |
| `fmpReducer` | [fmp.js](src/reducers/fmp.js) | `GET {API}/newsarticles/fmp` |
| page SSR | [capital-markets.js](src/pages/capital-markets.js) | `GET {API}/economic-data/` |

### C. Hooks that bypass Django and call FMP directly

Each builds a URL from `NEXT_PUBLIC_FMP_*` env vars and appends `NEXT_PUBLIC_FMP_API` as a query param — meaning the FMP key ships to the browser.

| Hook | File | Base env var |
|---|---|---|
| `useStockData` | [useStockData.js](src/hooks/useStockData.js) | `NEXT_PUBLIC_FMP_STOCK_PROFILE` |
| `useStockArticles` | [useStockArticles.js](src/hooks/useStockArticles.js) | `NEXT_PUBLIC_FMP_STOCK_NEWS` |
| `useETFData` | [useETFData.js](src/hooks/useETFData.js) | `NEXT_PUBLIC_FMP_ETF_INFO` |
| `useCommodData` | [useCommodityData.js](src/hooks/useCommodityData.js) | `NEXT_PUBLIC_FMP_COMMOD_PROFILE` |
| `useIndexPerformance` | [useIndexPerformance.js](src/hooks/useIndexPerformance.js) | `NEXT_PUBLIC_FMP_INDEX_PERF` |
| `useUserWatchList` | [useWatchList.js](src/hooks/useWatchList.js) | `NEXT_PUBLIC_FMP_URL` |

### D. Pure transform / UI hooks (no network)

| Hook | File | Purpose |
|---|---|---|
| `useAvailableSeries` / `hasData` | [useAvailableSeries.js](src/hooks/useAvailableSeries.js) | Filters requested series keys down to those with non-null values, so all-null parquet columns don't render empty axes |
| `useCapitalMarketCharter` | [useCapitalMarketsCharts.js](src/hooks/useCapitalMarketsCharts.js) | Maps yield/macro codes (`10Y`, `MLHY`, `TWOVTEN`, `CPI`, `UNEMP`, `NONFARM`…) to display names + colors, builds the Chart.js config |
| `useEquitySpreadCharter` | [useEquitySpreadChart.js](src/hooks/useEquitySpreadChart.js) | Same for equity spread codes (`EAFEVSC`, `ACWI`, `R2V1`, `SPVNAS`, `USCAN`…), with Quarterly/Yearly/Three-Year switching |
| `useMetricCharts` / `useSingleMetric` | [useMetricCharts.js](src/hooks/useMetricCharts.js), [useSingleMetricCharts.js](src/hooks/useSingleMetricCharts.js) | Peer-comparison index sets per universe (S&P/TSX/Russell/Nasdaq/DJ) for MA, return-spread, vol-spread, beta and Sharpe metrics |
| `useVixCharts` | [useVixChart.js](src/hooks/useVixChart.js) | Dual-axis index-vs-VIX chart config |
| `useChartUpdater` | [useChartUpdater.js](src/hooks/useChartUpdater.js) | Two-asset relative comparison chart (dual y-axes) |
| `useStockChart` | [useStockCharts.js](src/hooks/useStockCharts.js) | Rolling-returns line config |
| `useStockReturns` | [useStockReturns.js](src/hooks/useStockReturns.js) | Picks label/return arrays by frequency (`30d`, `120d`, `quarter`…) |
| `useSectorBarChart` | [useSectorExposure.js](src/hooks/useSectorExposure.js) | Industry-exposure bar chart |
| `useBarChart` | [useBarCharts.js](src/hooks/useBarCharts.js) | Peer bar chart that highlights the selected ticker in a different color |
| `useCovarChart` / `useWatchListCovar` | [useCovarChart.js](src/hooks/useCovarChart.js), [useCovarWatchList.js](src/hooks/useCovarWatchList.js) | Contribution-to-volatility bar configs |
| `useWatchListLineChart` | [useWatchListLineChart.js](src/hooks/useWatchListLineChart.js) | Multi-symbol price lines with a 22-color rotation, alternating y-axes |
| `useCandleStick` / `useNewCandleStick` | [useCandleStick.js](src/hooks/useCandleStick.js), [useNewCandleSticks.js](src/hooks/useNewCandleSticks.js) | ApexCharts candlestick configs; the "new" one adds a brushed volume bar chart |
| `useUserAccounts` | [useAccounts.js](src/hooks/useAccounts.js) | Thin `AccountContext` reader |
| `useHover` | [UseHover.js](src/hooks/UseHover.js) | `[ref, isHovered]` |
| `useWindowSize` | [UseWindowSize.js](src/hooks/UseWindowSize.js) | `{width, height}` with SSR guard |
| `useAddChart` | [useAddChart.js](src/hooks/useAddChart.js) | Empty stub — declared, never implemented, never exported |

---

## Django backend surface

Root URLconf: [backend/fintank_backend/urls.py](backend/fintank_backend/urls.py). All app URLconfs mount under `api/`.

```
path("api/", include("users.urls", namespace="users"))
path("api/", include("stockuploader.urls"))
path("api/", include("analyzer.urls"))
# path("api/", include("journal.urls"))     <- commented out
path("api/", include("news.urls"))
path("api-auth/", include("rest_framework.urls"))
path("api/auth/token/",         TokenObtainPairView)
path("api/auth/token/refresh/", TokenRefreshView)
path("api/auth/token/verify/",  TokenVerifyView)
path("api/auth/",               include("dj_rest_auth.urls"))
path("api/auth/registration/",  include("dj_rest_auth.registration.urls"))
path("accounts/",               include("allauth.urls"))
path("",                        include("pages.urls", namespace="pages"))
```

### `analyzer` — [urls.py](backend/analyzer/urls.py) / [views.py](backend/analyzer/views.py)

All `GET`, all `@api_view` with no permission class (public). Every view checks Redis for a gzip-compressed JSON blob first and falls back to a `CorePerformanceTools` refresh, returning `503 {"detail": "Data temporarily unavailable"}` if that also fails.

| Path | View | Cache key | Underlying source |
|---|---|---|---|
| `all-stock-names/` | `get_all_stock_names_available` | `stock:names:v1` | Redis → `get_all_stock_names()` |
| `index-history/<symbol>/` | `get_index_history_task` | `home:index_chart:{symbol}:v1` | Redis → FMP `/api/v3/historical-price-full/` (batched in 3 buckets) |
| `index-performance/` | `get_index_performance_task` | `home:index_performance:v1` | Redis → FMP |
| `etf-performance/` | `get_etf_performance_task` | `home:etf_performance:v1` | Redis → FMP |
| `crypto-performance/` | `get_crypto_performance_task` | `home:crypto_performance:v1` | Redis → FMP |
| `gainers-losers/` | `get_gainers_losers_task` | `home:gainers_losers:v1` | Redis → FMP `/stable/biggest-gainers` + `/stable/biggest-losers` |
| `sector-industry/<exchange>/` | `get_sector_industry_task` | `home:sector_performance:{exchange}:v1` | Redis → FMP `/stable/sector-performance-snapshot` + `/stable/industry-performance-snapshot` |
| `company-profiles/<symbol>/` | `get_company_profile` | `company:profiles:v1` | Redis → **S3 parquet** (`load_parquet_stock_profiles`) |
| `constituent-returns/<universe>/` | `get_constituent_returns` | `home:universe_constituents_returns:{universe}:v1` | Redis → S3 (`get_heat_map_data`). Universes: `sp500`, `tsx`, `nasdaq`, `r2000`, `rmicro`, `tsx_small_cap` |
| `universe-profiles/<universe>/` | `get_universe_profiles_task` | `home:universe_profiles:{universe}:v1` | Redis → `company:profiles:v1`, else S3 parquet. Validated against `UNIVERSE_PROFILE_SLUGS` = `sp500, nasdaq, tsx, tsx_small_cap, r2000, rmicro, msci_eafe, msci_sm, etfs`; unknown slug → 400 |
| `stock-profile/<symbol>/` | `get_stock_long_profile` | `stock:long_profile:{SYMBOL}:v1` | Redis → S3 parquet; `KeyError` → 404 |
| `stock-prices/<symbol>/` | `get_stock_price_data` | — | **S3 parquet** per call |
| `stock-prices-monthly/<symbol>/` | `get_stock_price_data_monthly` | — | S3 parquet per call |
| `financial-statements/<symbol>/<universe>/<statement_type>/` | `get_financial_statements` | — | S3 parquet. Validates `universe` ∈ `{sp500, nas, r2000, rmicro, tsx, tsx_small_cap, msci_eafe, msci_sm}` and `statement_type` ∈ `{income_statements, balance_sheet_statements, cash_flow_statements}`; bad value → 400 |
| `financial-statements/<symbol>/<statement_type>/` | `get_financial_statements_auto` | — | Same, but resolves the universe server-side by trying candidate parquets until one carries the symbol |

Note that `index-performance` / `etf-performance` / `crypto-performance` return the cached payload directly on a hit but the *raw* getter result on a miss — which is why `UseIndex`/`useEtf`/`useCryptoPerformance` all defensively do `res.data?.data ?? res.data`.

### `news` — [urls.py](backend/news/urls.py) / [views.py](backend/news/views.py)

| Path | View | Notes |
|---|---|---|
| `get_articles/<item>/` | `get_articles` (`AllowAny`) | Cache key `home:news_articles:{item}:v1`; on miss calls `GetNewsArticles.cache_single_article(item)` which pulls JSON from S3. Unknown category → 404 |

Valid `item` values come from `GetNewsArticles.file_names`: `fmp`, `crypto`, `stock`, `forex`, `econ`, `global_news`, `tech`, `macro`, `politics`, `energy`, `oil`, `mid_east`, `south_america`, `us_stock`, `japan_stock`, `china_stock`, `canadian_stock`, `eu_markets`, `africa_economy`, `basic_materials`, `industrials`, `utilities`, `pharmaceuticals`, `consumer_trends`, `financials`, `real_estate`, `communications`, `digital_assets`.

### `users` — [urls.py](backend/users/urls.py) / [views.py](backend/users/views.py)

| Method | Path | View | Auth |
|---|---|---|---|
| POST | `auth/register/` | `register` | `AllowAny` |
| GET | `users/me/` | `get_current_user` | `IsAuthenticated` |
| PATCH | `users/me/update/` | `update_user` (JSON only) | `IsAuthenticated` |
| PATCH | `users/me/change-password/` | `change_password` (JSON only) | `IsAuthenticated` |
| GET | `users/me/profile/` | `get_current_user_profile` | `IsAuthenticated` |
| PATCH | `users/me/profile/update/` | `update_user_profile` (multipart/form/JSON) | `IsAuthenticated` |
| PATCH | `users/me/profile/avatar/` | `update_my_avatar` (multipart/form only) | `IsAuthenticated` |

### `stockuploader` — [urls.py](backend/stockuploader/urls.py)

| Method | Path | View | Notes |
|---|---|---|---|
| POST | `upload/<model_name>/` | `upload_file_for_model` | Staff-only (`_staff_only`), CSV → `django-import-export` `Dataset` |

### `journal` — not mounted

`backend/journal/urls.py` is an **empty file**, and the `include("journal.urls")` line in the root URLconf is commented out. No journal endpoints exist.

### `pages` — HTML, not API

`""` → `landing`, `login/`, `register/`, `logout/`, `dashboard/`. Server-rendered Django templates for the uploader portal; the Next.js app does not call these.

---

## Gaps & Notes

### 1. Frontend calls endpoints that don't exist in the backend

Verified by matching every `NEXT_PUBLIC_FINTANK_API_URL` call site against the registered URLconfs.

| Caller | Path called | Impact |
|---|---|---|
| [capital-markets.js](src/pages/capital-markets.js) `getServerSideProps` | `GET /economic-data/` | Endpoint now exists (`analyzer.views.get_economic_data_task`), but the call is still not wrapped in try/catch — any backend outage makes SSR throw and `/capital-markets` 500s. This route is linked from the main nav |
| [screenerAction.js](src/actions/screenerAction.js) | `POST /screen/` | Screener submit from `/universe/[slug]` fails; the `swal` success/error branches also sit *after* an unguarded `await`, so the error path never runs |
| [UseMovers.js](src/hooks/UseMovers.js) | `/movers/` | Hook is unused — no importer |
| [useHeatMap.js](src/hooks/useHeatMap.js) | `/heat-map` | Hook is unused |
| [useTopPerformer.js](src/hooks/useTopPerformer.js) | `/gettopperformers/<index>` | Hook is unused |
| [useIndexPagePrices.js](src/hooks/useIndexPagePrices.js) | `/getindexpageprices/<index>/` | Imported by `EconomicCharts` and `capital-markets` |
| [useNewsGenerator.js](src/hooks/useNewsGenerator.js) | `/newsarticles/<topic>/` | Only referenced from commented-out code in `newsarticles/[slug].js`. Correct path is `/get_articles/<item>/` |
| [useLocationService.js](src/hooks/useLocationService.js) | `/getgeocode/<address>` | Hook is unused |
| [UseSectorTS.js](src/hooks/UseSectorTS.js) | `/sector-timeseries/<frequency>/` | Hook is unused (377 lines) |
| [useChartResources.js](src/hooks/useChartResources.js) | `/index-prices/…`, `/other-asset-prices/…` | Hook is unused |
| [useIndexMetrics.js](src/hooks/useIndexMetrics.js) | `/<ep>/<index>` | Endpoint is a caller-supplied string — unverifiable by construction |
| [fmp.js](src/reducers/fmp.js) | `/newsarticles/fmp` | Reducer is `async` (invalid for Redux) and is commented out of `rootReducer` |

### 2. Backend endpoints with no frontend caller

| Endpoint | Note |
|---|---|
| `GET /api/company-profiles/<symbol>/` | Superseded by `/stock-profile/<symbol>/`, which the stock page uses |
| `GET /api/stock-prices-monthly/<symbol>/` | No caller |
| `GET /api/financial-statements/<symbol>/<universe>/<type>/` | Frontend only uses the 2-arg auto-resolving variant |
| `PATCH /api/users/me/update/` | No caller |
| `PATCH /api/users/me/change-password/` | No caller |
| `PATCH /api/users/me/profile/update/` | No caller |
| `PATCH /api/users/me/profile/avatar/` | No caller — `UserMenu` renders a hardcoded `/images/homepageImages/avatar.jpg` instead of `avatar_url` |
| `POST /api/auth/token/refresh/`, `/verify/` | No caller — the BFF stores only the `access` token and never the refresh token, so sessions die silently at expiry |
| `POST /api/upload/<model_name>/` | Admin/CSV portal only |
| `dj-rest-auth` routes (`/api/auth/login`, `/logout`, `/password/reset`…) | Unused; the app uses the SimpleJWT `token/` endpoint instead |

### 3. Broken imports and dead routes

- **[user-account.js](src/pages/user-account.js) imports `Icon` from `@components/Icon`** — that file does not exist (`@components` resolves nowhere; the alias set is `@/*`, `@componentsLegacy/*`, `@utils/*`, `@hooks/*`, `@data/*`, `@context/*`). The component lives at `@componentsLegacy/Icon`. This page cannot build as written.
- **Links to routes with no page file:**
  - `/index-chart/<symbol>` — every row of `IndexReturnsSidePanel` on the homepage
  - `/stocks/<symbol>` — the heat map's `dataPointSelection` handler in `useIndexHeatMap.js` (the real stock route is `/stock-data/<ticker>`)
  - `/screener` — opened via `window.open` after a screen submit in `universe/[slug].js`
  - `/comm-data/[ticker]`, `/commodity` — referenced by `StockPagination`, `ScreenerPagination`, `CommodPagination`
  - From `@data/menu.json`: `/build-comparison`, `/factor-performance`, `/research-posts`, `/euro`, `/tsx`, `/wallet-account`
  - From `@data/user-menu.json`: `/profile` (and `/account`, which only exists on the App Router side)
- **Root route collision:** `pages/index.js` and `app/dashboard/page.tsx` both claim `/`. Pages Router wins; `DashboardFeature` is unreachable.

### 4. Components with no backend link (static / mock data)

Driven entirely by JSON in [src/data/](src/data/): `about.js` (`team.json`), `faq.js` (`faq.json`), `user-account.js` (`user-account.json`), `Footer` (`footer.json`), `Header` (`menu.json`), `UserMenu` (`user-menu.json`), `RichSwiper` on the homepage (`index.json`), `newsarticles/[slug]` chrome (`news.json`, `banner.json`, `topic.json`, `markets.json`), `universe/[slug]` filter options (`universe.json`, `sectors-subsectors.json`), `capital-markets` tabs (`searchTabs.json`), plus `Guides` (`guides.json`), `LastMinute` (`lastminute.json`, `rooms-geojson.json`), `Instagram` (`instagram.json`), `PopularCities` (`popular_cities.json`).

Note that `universe/[slug]` slugs come from `universe.json` (`allstocks`, `commodities`, `cryptos`, `dj`, `etfs`, `eurostocks`, `nasdaq`, `sp500`, `sptsx`) while the backend's `UNIVERSE_PROFILE_SLUGS` are `sp500, nasdaq, tsx, tsx_small_cap, r2000, rmicro, msci_eafe, msci_sm, etfs` — **they only overlap on `sp500`, `nasdaq` and `etfs`.** The nav links `/universe/dj`, and `dj` is not a valid backend slug, so that page's profile fetch returns 400.

### 5. Unused / dead components

No importer anywhere in `src/`: `CardPost`, `CommodPagination`, `Gallery`, `Guides`, `Instagram`, `LastMinute`, `Map`, `MapLeaflet`, `MetricsTable`, `Pagination`, `RankingPagination`, `ResultsTopBar`, `ReviewForm`, `Reviews`, `Screener`, `Support`, `SwiperGallery`, `SwiperTestimonial`, `ValuationTable` (19 files). Also unused within `Homepage/`: `HeroSection` and `IndexReturnsSection` — both were superseded when the homepage was refactored to inline `RichSwiper` + `IndexReturnsSidePanel`.

Unused hooks: `UseMovers`, `useHeatMap`, `useTopPerformer`, `useLocationService`, `UseSectorTS`, `useChartResources`, `useNewsGenerator`, `useAddChart` (an empty stub), plus most of the pure chart-transform hooks in group D whose consuming pages no longer exist.

### 6. Duplication between `src/components` and `src/componentsLegacy`

The two directories serve different runtimes and share **no** component names — `src/components/*.tsx` is entirely Solana/shadcn (`app-header`, `app-footer`, `app-layout`, `ui/*`, `solana/*`, `counter/*`, `account/*`), while `src/componentsLegacy/*.js` is the Bootstrap financial UI. So there is no true duplicate pair. What does exist is *functional* overlap: `components/app-header.tsx` + `app-footer.tsx` + `app-layout.tsx` vs `componentsLegacy/Header/` + `Footer.js` + `Layout.js`, and `components/ui/table.tsx` vs the hand-rolled Bootstrap `Table` usage in `MetricsTable`/`ValuationTable`. The only cross-directory reference is the broken `@components/Icon` import noted above.

Within `componentsLegacy` there *is* real duplication: `Sentiments.js` and `PriceTarget.js` are near-identical (both declare `const MoverReturns = (props) =>`), and `StockPagination` / `ScreenerPagination` / `CommodPagination` are three copies of the same `react-paginate` list differing only in the destination route.

### 7. Other observations

- **FMP key exposure** — the six hooks in group C build FMP URLs client-side with `NEXT_PUBLIC_FMP_API` in the query string, so the key is shipped in the JS bundle. The Django-backed path avoids this.
- **Session expiry** — the login BFF persists only the `access` token; `TokenRefreshView` is registered but never called, so the cookie simply goes stale.
- **Dual auth systems** — Firebase (email link, Google popup) and Django JWT run side by side in `login.js` / `completesignup.js` / `authContext.js`. Firebase authenticates first, then the same credentials are replayed against Django.
- **XSS surface, handled** — news content is third-party HTML. `ArticleModal` sanitizes with DOMPurify against a tag/attribute allowlist. But `newsarticles/[slug].js` renders `message.name`, `message.provider[0].name` and `message.description` through raw `dangerouslySetInnerHTML` with no sanitization.
- **`markets.js` leaves a `console.log(cryptoData)` on every render**, and `useSectorExposure.js` / `useChartUpdater.js` log inside `useMemo`/`useEffect`.
