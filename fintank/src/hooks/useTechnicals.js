import useSWRImmutable from 'swr/immutable'
import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_FINTANK_API_URL ?? 'http://localhost:8000/api'

const fetcher = async (url) => {
  const response = await axios.get(url)
  return response.data
}

export const technicalsUrl = (symbol, spec) =>
  `${API_URL}/technicals/${encodeURIComponent(symbol)}/` + (spec ? `?indicators=${encodeURIComponent(spec)}` : '')

/**
 * One symbol's candles, volume and indicator series.
 *
 * `spec` is deliberately absent from the key guard. With `symbol && spec`, a
 * freshly added ticker with nothing toggled yields an empty spec, a null key,
 * and therefore no request at all -- the panel stays blank forever and the
 * candlestick, which needs no indicators, is unreachable. The backend accepts
 * a missing `indicators` parameter for exactly this reason.
 *
 * useSWRImmutable, not revalidateOnFocus: five panels revalidating on every
 * tab focus is five requests for data the server pins to a 24h TTL.
 * useIndexRisk.js is the precedent; useWatchlistPerformance revalidates only
 * because watchlists are user-mutable.
 *
 * SWR here is 1.3.0 -- `isLoading` does not exist, so loading is derived.
 */
export const useTechnicals = (symbol, spec) => {
  const { data, error } = useSWRImmutable(symbol ? technicalsUrl(symbol, spec) : null, fetcher)
  return { data, error, loading: !data && !error }
}
