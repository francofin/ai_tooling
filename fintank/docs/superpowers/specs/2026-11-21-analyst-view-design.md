# Analyst view on the stock page: design

Date: 2026-11-21. Status: **draft for Franc's approval**. Source plan: `docs/next_stable_features.md`, feature 2.

## Intent

Show what sell-side analysts expect for a stock: forward estimates, ratings and price targets. It goes on `stock-data/[ticker]`. It makes the page forward-looking where today it only shows reported statements. Its data will also feed the earnings hub (feature 1), whose "results vs consensus" section needs it.

Audience: US and Canadian users, with **Canadian primary**.

## Goals
- Show forward estimates for any stock that FMP covers, including TSX-only names.
- Show ratings and price targets for Canadian stocks that also trade in the US, taken from the US listing. Label them clearly and convert them to CAD.
- Never show an empty or misleading panel.

## Non-goals
- No new pipeline stage. Data is fetched live.
- No analyst-level detail (individual firms, upgrade/downgrade history).
- No quality scores and no peer table (on hold).

## Anti-goals (would count as failure even if it works)
- A stale or single-analyst price target shown as if it were a consensus.
- A USD target shown next to a CAD price with no label.
- A blank panel or "N/A" grid on stocks with no coverage.

## Data (stable endpoints, all probed 2026-11-21)

| Need | Endpoint | Notes |
|---|---|---|
| Estimates | `analyst-estimates?symbol=&period=annual\|quarter` | Works for .TO symbols (TD.TO and DOL.TO go out to 2029–30). Low, average and high for revenue, EBITDA, EBIT, net income and EPS. |
| Ratings | `grades-consensus?symbol=` | Mostly empty for .TO symbols. The US listing has data (RY: 30 analysts). |
| Price target | `price-target-consensus`, `price-target-summary` | Mostly empty for .TO. US listing: SHOP has data; RY has 1 target in a year, which counts as stale. |
| US listing of a .TO stock | `search-exchange-variants?symbol=` | CNR.TO → CNI. Handles tickers that differ between exchanges. The two listings share an ISIN. |
| USD→CAD rate | `quote?symbol=USDCAD` | 1.434 on 2026-11-21 |

## Approaches considered
1. **Live fetch per stock page, cached in Redis for 24 hours.** Chosen. This is the same pattern as `stock-quote`. It covers any ticker, needs no pipeline change, and estimates move slowly.
2. **Bulk pull in the weekly pipeline to S3.** Rejected for now. It covers only pipeline universes and adds pipeline risk. Revisit it if the screener needs estimates across all stocks.
3. **Canadian listing only, with no US fallback.** Rejected, because ratings and targets would disappear for most Canadian stocks.

## Decisions

**Franc's decisions:**
- Estimates lead the panel, and ratings and targets appear only when they exist.
- Ratings and targets for .TO stocks fall back to the **US listing**. A label names that listing, and the target is **converted to CAD** (option A, 2026-11-21).

**Claude's proposals (Franc did not object):**
- Live fetch, Redis cache with a 24-hour TTL.
- Panel order:
  1. **Estimates.** Revenue, EPS and EBITDA, each with low, average and high. An **Annual** (next 3 fiscal years, the default) / **Quarterly** (next 4 quarters) toggle. Quarterly data is fetched only when the toggle is opened.
  2. **Ratings bar.** Strong buy through strong sell counts, the consensus word and the analyst count.
  3. **Price target.** Consensus, median and low–high range compared with the current price, with the implied % upside.
- **Stale-target rule:** hide the price target when fewer than **3** targets were set in the last year (`price-target-summary.lastYearCount`).
- **Label for fallback data**, for example: "Target $178 USD (≈ $255 CAD) · from SHOP's NYSE listing". The CAD figure uses that day's USDCAD rate.
- Estimates are shown in the company's reporting currency, with a currency label. They always come from the .TO symbol when one exists.
- If no estimates, ratings or targets are available, the panel is not rendered at all.

## FMP call budget

Page loads read from Redis. FMP is called only when the cached copy is missing or has expired.

| Call | When it is made |
|---|---|
| `analyst-estimates` annual | Once per stock per day, on the first view |
| `analyst-estimates` quarterly | Once per stock per day, **only when the Quarterly toggle is opened** (lazy) |
| `grades-consensus`, `price-target-consensus`, `price-target-summary` | Once per stock per day. For a .TO stock with a US listing, these go to the US symbol. |
| `search-exchange-variants` | Once per .TO stock per **30 days**. Cross-listings rarely change. |
| `income-statement?limit=1` (reporting currency for the estimates label) | Once per stock per **30 days**, cached with the listing lookup. Added in the plan. |
| `quote?symbol=USDCAD` | Once per day for the whole site |

- **Per stock per day:** about 4 calls (5 if the quarterly toggle is opened).
- **Example:** 200 different stocks viewed in a day comes to about 800–1,000 FMP calls, however many times the pages are loaded.
- Ultimate has no per-call charge and its per-minute limit is far above this.
- **Why not S3:** S3 would need a pipeline stage to fill it. Redis already holds the site's live data, and a Redis restart only means the next view fetches again.

## Shape (proposal)
- **Backend:** add `GET /api/analyst-view/<symbol>/` in `analyzer`. It calls `backend/utils/fmp_stable.py` and returns `{symbol, estimates.annual, ratings, target (with cad), source, reporting_currency}`. A separate `/quarterly/` route serves `estimates.quarter`. The plan holds the exact shape. The variant lookup and the FX rate get their own Redis keys, following the `home:{type}:{qualifier}:v1` pattern.
- **Frontend:** add a `fetchAnalystView` in `src/utils/stockApi.js` and an `AnalystView` component in `src/componentsLegacy/StockDetail/`, placed next to `StatementsSection`.

## Left to the builder
- Exact cache keys and TTLs for the variant map and FX rate. The variant map can be cached for a long time.
- Chart or table styling, matching the existing `StockDetail` components.
- Error handling that follows `get_stock_quote`: a 404 for an unknown symbol, a 502 when FMP fails. The frontend hides the panel on any error.
- Tests: backend tests using mocked FMP responses for a US stock, an interlisted .TO stock, a TSX-only .TO stock, and a stale-target case.

## Constraints
- Use stable endpoints only. Re-map field names; never write a v3 URL.
- The site stays free until FMP's Data Display and Licensing Agreement is in place. Analyst data falls under that agreement, so it must be settled before Stripe goes live.
- Pushing to `main` deploys. Don't merge while a pipeline run is waiting for approval unless Franc says so.
