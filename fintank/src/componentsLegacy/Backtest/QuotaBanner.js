import React from 'react'
import { Alert } from 'react-bootstrap'

/**
 * Remaining runs, and the upgrade prompt when the API returns 402.
 * Saving and editing portfolios never counts — say so, or the meter reads as
 * hostile.
 */
const QuotaBanner = ({ quota, quotaError }) => {
  if (quotaError) {
    return (
      <Alert variant="warning" className="mb-3">
        <strong>You have used all {quotaError.limit} of your free backtests.</strong>
        <div className="fs-13px">
          Saving, editing and duplicating portfolios stays free. Re-running a backtest you have already run is also
          free.
        </div>
      </Alert>
    )
  }

  if (!quota) return null
  if (quota.remaining === null) {
    return <div className="fs-13px text-muted">Unlimited backtests on your plan.</div>
  }

  return (
    <div className={`fs-13px ${quota.remaining <= 2 ? 'text-warning' : 'text-muted'}`}>
      {quota.remaining} of {quota.limit} free backtests remaining. Saving and editing portfolios is always free.
    </div>
  )
}

export default QuotaBanner
