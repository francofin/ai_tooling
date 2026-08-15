import { useCallback, useEffect, useRef, useState } from 'react'
import axios from 'axios'

const POLL_START_MS = 1000
const POLL_MAX_MS = 3000
const POLL_STEP_MS = 500

/**
 * Submit a backtest, poll until it finishes, then fetch the result.
 *
 * Polling starts at 1s and backs off to 3s: most runs finish in a few seconds,
 * and a fixed 1s interval on a 30s risk-parity run is 30 pointless requests.
 */
export const useBacktestRun = () => {
  const [taskId, setTaskId] = useState(null)
  const [status, setStatus] = useState('idle')
  const [progress, setProgress] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [quotaError, setQuotaError] = useState(null)
  const timer = useRef(null)
  const interval = useRef(POLL_START_MS)

  const clear = useCallback(() => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
  }, [])

  useEffect(() => clear, [clear])

  const fetchResult = useCallback(async (id) => {
    try {
      const { data } = await axios.get(`/api/backtester/results/${id}`)
      setResult(data)
      setStatus('complete')
    } catch (requestError) {
      setStatus('failed')
      setError(requestError?.response?.data?.detail || 'The backtest finished but its results are gone.')
    }
  }, [])

  const poll = useCallback(
    async (id) => {
      try {
        const { data } = await axios.get(`/api/backtester/status/${id}`)
        setProgress(data?.progress || '')

        if (data?.status === 'complete') {
          await fetchResult(id)
          return
        }
        if (data?.status === 'failed') {
          setStatus('failed')
          setError(data?.error || 'The backtest failed.')
          return
        }
        interval.current = Math.min(interval.current + POLL_STEP_MS, POLL_MAX_MS)
        timer.current = setTimeout(() => poll(id), interval.current)
      } catch {
        setStatus('failed')
        setError('Lost contact with the backtester.')
      }
    },
    [fetchResult],
  )

  const reset = useCallback(() => {
    clear()
    setTaskId(null)
    setStatus('idle')
    setProgress('')
    setResult(null)
    setError(null)
    setQuotaError(null)
    interval.current = POLL_START_MS
  }, [clear])

  const submit = useCallback(
    async (payload) => {
      clear()
      setStatus('submitting')
      setError(null)
      setQuotaError(null)
      setResult(null)
      interval.current = POLL_START_MS

      try {
        const { data } = await axios.post('/api/backtester/run', payload)
        setTaskId(data.task_id)

        if (data.cached) {
          setStatus('running')
          await fetchResult(data.task_id)
          return data.task_id
        }
        setStatus('running')
        timer.current = setTimeout(() => poll(data.task_id), POLL_START_MS)
        return data.task_id
      } catch (requestError) {
        const response = requestError?.response
        setStatus('failed')
        if (response?.status === 402) {
          setQuotaError(response.data)
        } else {
          setError(response?.data?.detail || 'Could not start the backtest.')
        }
        return null
      }
    },
    [clear, fetchResult, poll],
  )

  return { taskId, status, progress, result, error, quotaError, submit, reset }
}

export default useBacktestRun
