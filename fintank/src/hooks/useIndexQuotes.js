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
  const { data, error, isLoading } = useSWR(
    slug ? indexQuotesUrl(slug) : null,
    fetcher,
    { revalidateOnFocus: false, refreshInterval: 300000 }
  )

  return { quotes: data, error, isLoading }
}
