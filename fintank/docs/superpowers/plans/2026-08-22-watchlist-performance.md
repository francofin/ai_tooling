# Watchlist performance on the profile dashboard

**Date:** 2026-08-22
**Status:** approved, implementing

Adds a watchlist performance panel to the third post box on `/profile`: a dropdown
of the user's watchlist stocks that loads a price chart, a row of period returns,
and the return since the stock was added to the watchlist.

## Cost constraint

The driving requirement is that this must not grow the FMP bill before the product
is profitable. **It adds zero FMP calls.**

Daily price history for every symbol is already in S3 parquet at
`stock_data/stock_prices/daily/{SYMBOL}_prices.parquet`, and
`CorePerformanceTools.get_stock_price_data()` already caches it gzipped in Redis
for 24 hours under `stock:prices:{SYMBOL}:v1`. That cache is keyed by symbol, not
by user, so a symbol held by a thousand users is still one S3 read per day.
Everything this feature reports — period returns and the since-added return — is
arithmetic over that series.

### Pre-existing cost leak (not addressed here, flagged deliberately)

`src/hooks/useWatchList.js` (`useUserWatchList`) calls FMP directly from the
browser with `NEXT_PUBLIC_FMP_API` on `refreshInterval: 10000` — a request every
ten seconds per open tab, with the key exposed to anyone who opens devtools. One
idle tab is ~360 calls an hour. `src/hooks/useStockArticles.js` has the same
shape.

Decision: leave both in place for now and record them here. This feature does not
use them and does not make them worse. They remain the largest avoidable FMP cost
in the frontend.

## What already exists

- `ProfileStock.date_added` (`auto_now_add=True`) — the since-added feature needs
  **no migration**; the timestamp has been recorded since the model was written.
- `add_to_watchlist` / `delete_from_watchlist` / `stock_on_watchlist` in
  `stockuploader/views.py`.
- `/api/stock-prices/<symbol>/` serving the cached daily series.
- `IndexChartView` and `sliceChartData` from the index chart work, both reusable.

## What is missing

- No endpoint lists a user's watchlist. Only add/remove/verify exist.
- No endpoint returns performance for a watchlist entry.

## Design

### Endpoints

Both apps mount under `/api/`, so these join one flat namespace.

`GET /api/watchlist/` — `IsAuthenticated`

```json
[{ "symbol": "AAPL", "name": "Apple Inc.", "date_added": "2026-03-04T11:20:00Z" }]
```

Lives in `stockuploader/views.py` beside the other watchlist CRUD.

`GET /api/watchlist/performance/<symbol>/` — `IsAuthenticated`

```json
{
  "symbol": "AAPL",
  "name": "Apple Inc.",
  "dates": ["2025-08-22", "..."],
  "prices": [227.4, "..."],
  "periods": { "1D": 0.42, "1W": -1.1, "1M": 3.8, "3M": 7.2, "YTD": 12.4, "1Y": 22.9 },
  "since_added": { "date": "2026-03-04", "start_price": 210.11, "return": 8.2 }
}
```

Lives in `analyzer/views.py` with the other cached market data. Returns 404 when
the symbol is not on the requesting user's watchlist, so the endpoint cannot be
used to read arbitrary symbols' precomputed stats.

### Caching

| Layer | Key | TTL | Scope |
|---|---|---|---|
| S3 parquet → JSON | `stock:prices:{SYMBOL}:v1` | 24h | per symbol (**exists**) |
| Period returns | `watchlist:perf:{SYMBOL}:{market_date}:v1` | 24h | per symbol |
| Since-added return | none | — | computed per request |

The period returns are cached per symbol rather than per user, so the arithmetic
runs once per symbol per trading day no matter how many users hold it. The
since-added return depends on the caller's own `date_added`, but it is one index
lookup and one division over an already-cached series, so it does not earn a
cache entry of its own.

The dropdown loads one symbol at a time, so a 30-stock watchlist costs one
request on open, not thirty.

### Periods

`1D`, `1W`, `1M`, `3M`, `YTD`, `1Y`, plus since-added.

`1D` is derived from the last two closes in the daily parquet, so it is
previous-close to close, **not** live intraday. The UI must not imply otherwise.

### Since-added edge cases

- Added before the price history begins → fall back to the first available close
  and mark the return as covering a shorter window than claimed.
- Added today, or after the last close → return `null`, render as `—`.
- Added on a non-trading day → use the first close on or after `date_added`.

### Frontend

- `src/hooks/useWatchlist.js` — SWR list, long refresh interval.
- `src/hooks/useWatchlistPerformance.js` — SWR per symbol, long refresh interval;
  the underlying data changes once per day.
- `src/componentsLegacy/Markets/WatchlistPerformance.js` — dropdown, chart via
  `IndexChartView`, period tiles, since-added tile.
- Rendered into the third post card on `/profile`, replacing the lorem ipsum.

### Empty and error states

- Empty watchlist → a prompt linking to the screener rather than an empty chart.
- Symbol with no parquet in S3 → "No price history for this symbol."
- Request failure → the panel says so; it must not render a chart of zeros.

## Out of scope

- Retiring the two direct-to-FMP hooks (recorded above).
- Multi-stock comparison overlay.
- Intraday/live pricing.
