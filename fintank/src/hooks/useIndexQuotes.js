import useSWR from "swr"
import { fetcher, indexQuotesUrl } from "@/lib/indexApi"

/**
 * Constituent quotes: top and bottom movers plus the PE-ranked valuation table,
 * from one cached payload.
 *
 * Not immutable, unlike the parquet-backed hooks -- these are market quotes.
 * The backend caches for 24h, so a refetch is cheap when it lands on a warm
 * cache and picks up the new batch when it does not.
 */
export const useIndexQuotes = (slug) => {
  const key = slug ? indexQuotesUrl(slug) : null
  const { data, error } = useSWR(key, fetcher, {
    revalidateOnFocus: false,
    refreshInterval: 300000,
  })
  // SWR 1.3.0 has no `isLoading`; derive it. A null key is idle, not loading.
  const isLoading = key !== null && !data && !error

  return { quotes: data, error, isLoading }
}
