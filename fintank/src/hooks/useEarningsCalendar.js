import useSWR from 'swr'
import { fetchEarningsCalendar } from '@utils/stockApi'
import { withIsLoading } from './swrLoading'

const OPTIONS = {
  revalidateOnFocus: false,
  errorRetryCount: 3,
  errorRetryInterval: 60 * 1000,
}

// swr@1 spreads an array key across the fetcher's arguments, hence `(_, w)`.
export const useEarningsCalendar = (weekISO) => {
  const key = weekISO ? ['earnings-calendar', weekISO] : null
  return withIsLoading(
    key,
    useSWR(key, (_, w) => fetchEarningsCalendar(w), OPTIONS),
  )
}
