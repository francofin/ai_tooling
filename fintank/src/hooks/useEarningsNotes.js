import useSWR from 'swr'
import { fetchEarningsNotes, fetchEarningsNote } from '@utils/stockApi'
import { withIsLoading } from './swrLoading'

// Notes change at most a few times a year: no polling, no refetch on focus.
// A 404 means no note and never resolves on retry.
const OPTIONS = {
  revalidateOnFocus: false,
  errorRetryCount: 6,
  errorRetryInterval: 60 * 1000,
  shouldRetryOnError: (err) => err?.status !== 404,
}

// swr@1 spreads an array key across the fetcher's arguments, hence `(_, s)`.
export const useEarningsNotes = (symbol) => {
  const key = symbol ? ['earnings-notes', symbol] : null
  return withIsLoading(
    key,
    useSWR(key, (_, s) => fetchEarningsNotes(s), OPTIONS),
  )
}

// A null key keeps the fetch lazy until a quarter is chosen.
export const useEarningsNote = (symbol, quarter) => {
  const key = symbol && quarter ? ['earnings-note', symbol, quarter] : null
  return withIsLoading(
    key,
    useSWR(key, (_, s, q) => fetchEarningsNote(s, q), OPTIONS),
  )
}
