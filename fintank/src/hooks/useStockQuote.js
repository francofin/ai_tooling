import useSWR from 'swr';
import { fetchQuote } from '@utils/stockApi';
import { withIsLoading } from './swrLoading';

// Matches the backend's cache window while the market is open, so each poll
// picks up at most one new FMP fetch's worth of data.
const QUOTE_REFRESH_MS = 15 * 60 * 1000;

/**
 * Delayed quote for one symbol, fetched client-side only so the page never
 * blocks on the provider. Returns the SWR result (`data` is the full payload:
 * `{ quote, fetched_at, stale_cache }`) plus a derived `isLoading`.
 *
 * swr@1 spreads an array key across the fetcher's arguments, hence `(_, s)`.
 */
export const useStockQuote = (symbol) => {
  const key = symbol ? ['stock-quote', symbol] : null;
  return withIsLoading(
    key,
    useSWR(key, (_, s) => fetchQuote(s), {
      refreshInterval: QUOTE_REFRESH_MS,
      revalidateOnFocus: false,
      // swr@1 pauses refreshInterval polling while the hook holds an error, so
      // retries are what bring a transient 502 back. A 404 never resolves on
      // retry, so skip those. Backoff starts at ~1 min rather than 5 s since
      // the backend only refreshes every 15 min anyway.
      shouldRetryOnError: (err) => err?.status !== 404,
      errorRetryInterval: 60 * 1000,
      errorRetryCount: 6,
    })
  );
};

export default useStockQuote;
