import useSWRImmutable from "swr/immutable"

import { fetcher, indexSectorContributionUrl } from "@/lib/indexApi"

/**
 * Sector contribution to index return, and breadth, per window.
 *
 * Immutable like useIndexRisk: the payload is a cross-sectional snapshot the
 * pipeline overwrites, so there is nothing to revalidate within a session.
 *
 * SWR here is 1.3.0, which has no `isLoading` -- useTechnicals.js:28 documents
 * this. Loading is derived rather than destructured, so the consumer can tell
 * "still fetching" from "fetched and empty" and avoid flashing an unavailable
 * message over a request that is merely in flight.
 */
export const useIndexSectorContribution = (slug) => {
  const { data, error } = useSWRImmutable(
    slug ? indexSectorContributionUrl(slug) : null,
    fetcher
  )

  return { sectors: data, error, loading: !data && !error }
}
