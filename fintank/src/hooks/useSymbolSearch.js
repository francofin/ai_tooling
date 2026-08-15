import { useEffect, useState } from 'react'
import axios from 'axios'

const DEBOUNCE_MS = 250
const MIN_QUERY_LENGTH = 1

/**
 * Debounced typeahead over the staged universe. The debounce matters: the
 * backend builds its symbol index from S3 constituent lists, and a request per
 * keystroke would hammer it.
 */
export const useSymbolSearch = () => {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)

  useEffect(() => {
    const trimmed = query.trim()
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setResults([])
      return undefined
    }

    let cancelled = false
    const timer = setTimeout(async () => {
      try {
        setSearching(true)
        const { data } = await axios.get(`/api/backtester/search-symbols?q=${encodeURIComponent(trimmed)}`)
        if (!cancelled) setResults(data?.results || [])
      } catch (error) {
        if (!cancelled) setResults([])
      } finally {
        if (!cancelled) setSearching(false)
      }
    }, DEBOUNCE_MS)

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query])

  return { query, setQuery, results, searching }
}

export default useSymbolSearch
