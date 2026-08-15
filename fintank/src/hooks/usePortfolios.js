import { useCallback, useEffect, useState } from 'react'
import axios from 'axios'

const BASE = '/api/backtester/portfolios'

/**
 * Saved-portfolio CRUD. All of it is free — only running a backtest meters —
 * so these calls never need to worry about the quota.
 */
export const usePortfolios = () => {
  const [portfolios, setPortfolios] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const reload = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const { data } = await axios.get(BASE)
      setPortfolios(Array.isArray(data) ? data : data?.results || [])
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || 'Could not load your portfolios.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  const create = useCallback(
    async (payload) => {
      try {
        const { data } = await axios.post(BASE, payload)
        await reload()
        return data
      } catch (requestError) {
        setError(
          requestError?.response?.data?.name?.[0] ||
            requestError?.response?.data?.detail ||
            'Could not save that portfolio.',
        )
        return null
      }
    },
    [reload],
  )

  const update = useCallback(
    async (id, payload) => {
      try {
        const { data } = await axios.patch(`${BASE}/${id}`, payload)
        await reload()
        return data
      } catch (requestError) {
        setError(requestError?.response?.data?.detail || 'Could not update that portfolio.')
        return null
      }
    },
    [reload],
  )

  const remove = useCallback(
    async (id) => {
      try {
        await axios.delete(`${BASE}/${id}`)
        await reload()
        return true
      } catch {
        setError('Could not delete that portfolio.')
        return false
      }
    },
    [reload],
  )

  const duplicate = useCallback(
    async (id) => {
      try {
        const { data } = await axios.post(`${BASE}/${id}/duplicate`, {})
        await reload()
        return data
      } catch {
        setError('Could not duplicate that portfolio.')
        return null
      }
    },
    [reload],
  )

  return { portfolios, loading, error, reload, create, update, remove, duplicate }
}

export default usePortfolios
