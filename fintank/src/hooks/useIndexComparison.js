import useSWRImmutable from "swr/immutable"
import { fetcher, indexComparisonUrl } from "@/lib/indexApi"

/**
 * One index against one comparison index.
 *
 * Immutable: the underlying parquets are rebuilt daily and the backend caches
 * the computed pair for 24h, so revalidating on focus would re-fetch bytes that
 * cannot have changed. Switching peers changes the key, which is the fetch.
 */
export const useIndexComparison = (slug, peerKey, options) => {
  const key = slug && peerKey ? indexComparisonUrl(slug, peerKey, options) : null
  const { data, error } = useSWRImmutable(key, fetcher)
  // SWR 1.3.0 has no `isLoading`; derive it. A null key is idle, not loading.
  const isLoading = key !== null && !data && !error

  return { comparison: data, error, isLoading }
}
