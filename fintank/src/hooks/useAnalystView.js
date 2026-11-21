import useSWR from 'swr'
import { fetchAnalystView, fetchAnalystQuarterly } from '@utils/stockApi'
import { withIsLoading } from './swrLoading'

// Estimates move slowly: no polling and no refetch on focus. A 404 means no
// coverage and never resolves on retry.
const OPTIONS = {
  revalidateOnFocus: false,
  shouldRetryOnError: (err) => err?.status !== 404,
}

// swr@1 spreads an array key across the fetcher's arguments, hence `(_, s)`.
export const useAnalystView = (symbol) => {
  const key = symbol ? ['analyst-view', symbol] : null
  return withIsLoading(
    key,
    useSWR(key, (_, s) => fetchAnalystView(s), OPTIONS),
  )
}

// A null key keeps the quarterly fetch lazy until `enabled`.
export const useAnalystQuarterly = (symbol, enabled) => {
  const key = symbol && enabled ? ['analyst-quarterly', symbol] : null
  return withIsLoading(
    key,
    useSWR(key, (_, s) => fetchAnalystQuarterly(s), OPTIONS),
  )
}
