import { useCallback, useEffect, useState } from 'react'
import axios from 'axios'

/**
 * Remaining free backtests. Cheap enough to refetch after every run so the
 * banner never shows a stale count.
 */
export const useBacktestQuota = () => {
  const [quota, setQuota] = useState(null)
  const [loading, setLoading] = useState(true)

  const reload = useCallback(async () => {
    try {
      setLoading(true)
      const { data } = await axios.get('/api/backtester/quota')
      setQuota(data)
    } catch (error) {
      setQuota(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  return { quota, loading, reload }
}

export default useBacktestQuota
