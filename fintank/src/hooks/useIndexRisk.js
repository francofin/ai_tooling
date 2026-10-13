import useSWRImmutable from "swr/immutable"
import { fetcher, indexRiskUrl } from "@/lib/indexApi"

/**
 * Constituent risk decomposition -- contribution to index volatility and to
 * period return over the trailing 90 trading days.
 *
 * The contr_to_var parquets are a snapshot overwritten once per pipeline run,
 * so there is nothing to revalidate within a session.
 */
export const useIndexRisk = (slug, options) => {
  const key = slug ? indexRiskUrl(slug, options) : null
  const { data, error } = useSWRImmutable(key, fetcher)
  // SWR 1.3.0 has no `isLoading`; derive it. A null key is idle, not loading.
  const isLoading = key !== null && !data && !error

  return { risk: data, error, isLoading }
}
