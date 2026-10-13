import useSWR from "swr"
import axios from "axios"
import { withIsLoading } from "./swrLoading"

/**
 * Watchlist data for the profile dashboard.
 *
 * Both hooks go through the Next proxy at `/api/watchlist/[...path]` rather than
 * calling Django directly: the JWT lives in an httpOnly cookie the browser
 * cannot attach itself. The route names match the proxy's allowlist.
 *
 * The server serves a daily close from a 24h cache, so there is nothing to gain
 * from polling — these revalidate on focus and otherwise sit still. That is also
 * the point of the feature's cost design; see
 * docs/superpowers/plans/2026-08-22-watchlist-performance.md.
 */
const DAILY = { revalidateOnFocus: true, refreshInterval: 0 }

const fetcher = async (url) => {
  const res = await axios.get(url)
  return res.data
}

/** The signed-in user's watchlist: `[{ symbol, name, date_added }]`. */
const WATCHLIST_KEY = "/api/watchlist/mywatchlist"

export const useWatchlist = () => withIsLoading(WATCHLIST_KEY, useSWR(WATCHLIST_KEY, fetcher, DAILY))

/**
 * Price history and returns for one watchlist symbol.
 *
 * A falsy symbol suspends the request — SWR treats a null key as "not ready" —
 * so nothing is fetched before the user has picked one.
 */
export const useWatchlistPerformance = (symbol) => {
  const key = symbol ? `/api/watchlist/watchlistperformance/${encodeURIComponent(symbol)}` : null
  return withIsLoading(key, useSWR(key, fetcher, DAILY))
}
