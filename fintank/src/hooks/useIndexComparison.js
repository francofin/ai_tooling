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
  const { data, error, isLoading } = useSWRImmutable(
    slug && peerKey ? indexComparisonUrl(slug, peerKey, options) : null,
    fetcher
  )

  return { comparison: data, error, isLoading }
}
