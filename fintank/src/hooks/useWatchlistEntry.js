import { useCallback, useEffect, useState } from 'react'
import axios from 'axios'

/**
 * One symbol's membership in the signed-in user's watchlist.
 *
 * Goes through /api/watchlist/*, so the JWT stays in its httpOnly cookie and
 * never reaches client code. (It replaced an older useWatchList.js that quoted
 * the list straight from FMP in the browser with the API key in the query
 * string; that hook was unused and has been removed.)
 *
 * `signedOut` is kept separate from `error`: not being logged in is an expected
 * state the button renders as a prompt, not a failure worth showing in red.
 */
export const useWatchlistEntry = (symbol) => {
  const [onWatchlist, setOnWatchlist] = useState(false)
  const [signedOut, setSignedOut] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!symbol) return undefined

    let cancelled = false
    const check = async () => {
      try {
        setLoading(true)
        const { data } = await axios.get(
          `/api/watchlist/stockonwatchlist/${encodeURIComponent(symbol)}/verify`,
        )
        if (!cancelled) {
          setOnWatchlist(Boolean(data))
          setSignedOut(false)
        }
      } catch (requestError) {
        if (cancelled) return
        if (requestError?.response?.status === 401) setSignedOut(true)
        else setError(requestError?.response?.data?.detail || 'Could not read your watchlist.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    check()
    return () => {
      cancelled = true
    }
  }, [symbol])

  const toggle = useCallback(async () => {
    const route = onWatchlist ? 'deletefromwatchlist' : 'addtowatchlist'
    // Flip optimistically so the button responds immediately, and put it back
    // if the request fails.
    const previous = onWatchlist
    setOnWatchlist(!previous)
    setSaving(true)
    setError(null)
    try {
      await axios.post(`/api/watchlist/${route}/${encodeURIComponent(symbol)}`)
    } catch (requestError) {
      setOnWatchlist(previous)
      if (requestError?.response?.status === 401) setSignedOut(true)
      else setError(requestError?.response?.data?.detail || 'Could not update your watchlist.')
    } finally {
      setSaving(false)
    }
  }, [onWatchlist, symbol])

  return { onWatchlist, signedOut, loading, saving, error, toggle }
}
