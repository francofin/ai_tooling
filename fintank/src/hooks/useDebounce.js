import { useEffect, useRef, useState } from 'react'

/**
 * Debounced value that is returned *synchronously* on the first render.
 *
 * Without the first-render passthrough the whole page idles for `delay`
 * milliseconds on load before issuing a single request, for nothing.
 *
 * Debounce the state object, not the serialized spec string: debouncing the
 * string leaves `symbols` undebounced, so adding a ticker mid-flight mounts a
 * panel that fetches with the stale spec and refetches 400ms later -- two
 * requests and a visible rebuild for that panel alone.
 */
export const useDebounce = (value, delay = 400) => {
  const [debounced, setDebounced] = useState(value)
  const first = useRef(true)

  useEffect(() => {
    if (first.current) {
      first.current = false
      return undefined
    }
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return first.current ? value : debounced
}
