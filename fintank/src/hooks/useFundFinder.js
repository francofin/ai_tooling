import useSWR from 'swr'
import { fetchFundFinder } from '@utils/stockApi'
import { canSearch } from '@utils/fundFinder/query.mjs'
import { withIsLoading } from './swrLoading'

// Holdings change weekly: no polling, no refetch on focus. A 400 is a bad
// query and a retry cannot fix it.
const OPTIONS = {
  revalidateOnFocus: false,
  errorRetryCount: 3,
  errorRetryInterval: 30 * 1000,
  shouldRetryOnError: (err) => err?.status !== 400,
}

// Idle (null key) until a listing is chosen and at least one stock is included.
// swr@1 spreads an array key across the fetcher's arguments, hence `(_, a, b, c)`.
export const useFundFinder = (state) => {
  const key = canSearch(state)
    ? ['fund-finder', state.listed, state.include.join(','), state.exclude.join(','), state.leveraged ? '1' : '']
    : null
  return withIsLoading(
    key,
    useSWR(
      key,
      (_, listed, include, exclude, leveraged) =>
        fetchFundFinder({ listed, include, ...(exclude ? { exclude } : {}), ...(leveraged ? { leveraged } : {}) }),
      OPTIONS,
    ),
  )
}
