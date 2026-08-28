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
  const { data, error, isLoading } = useSWRImmutable(
    slug ? indexRiskUrl(slug, options) : null,
    fetcher
  )

  return { risk: data, error, isLoading }
}
