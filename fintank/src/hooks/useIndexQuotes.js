import useSWR from "swr"
import { fetcher, indexQuotesUrl } from "@/lib/indexApi"

/**
 * Constituent quotes: top and bottom movers plus the PE-ranked valuation table,
 * from one cached payload.
 *
 * Not immutable, unlike the parquet-backed hooks -- these are market quotes.
 * The backend caches them for 24h, so frequent polling only re-reads the same
 * cached payload. Poll every 30 minutes while the payload says the market is
 * open, and not at all once it is closed; a page load always fetches.
 */
const OPEN_MARKET_REFRESH_MS = 30 * 60 * 1000
// Module-level so SWR sees the same function every render; its polling
// effect restarts whenever refreshInterval changes identity.
const refreshInterval = (latest) => (latest?.market_open ? OPEN_MARKET_REFRESH_MS : 0)

export const useIndexQuotes = (slug) => {
  const key = slug ? indexQuotesUrl(slug) : null
  const { data, error } = useSWR(key, fetcher, {
    revalidateOnFocus: false,
    refreshInterval,
  })
  // SWR 1.3.0 has no `isLoading`; derive it. A null key is idle, not loading.
  const isLoading = key !== null && !data && !error

  return { quotes: data, error, isLoading }
}
