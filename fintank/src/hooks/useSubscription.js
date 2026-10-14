import { useCallback, useEffect, useRef, useState } from 'react'
import axios from 'axios'

const POLL_EVERY_MS = 2000
const POLL_FOR_MS = 20000

/**
 * The signed-in user's plan. With `poll`, keeps refetching for up to 20 s until
 * the tier turns `pro` -- used right after Stripe Checkout, while the webhook
 * that upgrades the account is still on its way. `pollExpired` tells the page
 * to stop showing the spinner.
 *
 * The poll runs on a fixed `setInterval`, not a chain of `setTimeout`s started
 * from the fetched data: if the subscription endpoint keeps erroring (so
 * `subscription` never changes), the wall-clock check below still fires on
 * every tick and flips `pollExpired` once ~20 s have elapsed, so the page
 * can't be left spinning forever on a broken backend.
 */
export const useSubscription = ({ poll = false } = {}) => {
  const [subscription, setSubscription] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [pollExpired, setPollExpired] = useState(false)
  const startedAt = useRef(Date.now())
  const isPro = subscription?.tier === 'pro'

  const reload = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/billing/subscription')
      setSubscription(data)
      setError(null)
      return data
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not load your subscription.')
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  useEffect(() => {
    if (!poll || isPro || pollExpired) return undefined
    const interval = setInterval(async () => {
      await reload()
      if (Date.now() - startedAt.current >= POLL_FOR_MS) {
        setPollExpired(true)
      }
    }, POLL_EVERY_MS)
    return () => clearInterval(interval)
  }, [poll, isPro, pollExpired, reload])

  return { subscription, loading, error, pollExpired, reload }
}

export default useSubscription
