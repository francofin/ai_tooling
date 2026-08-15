import React from 'react'
import { Card } from 'react-bootstrap'

import { formatMoney, formatPercent, monthYear, monthsBetween } from './formatters'

/**
 * The plain-language answer, first. Everything numeric below it is a footnote to
 * this sentence.
 */
const ResultsHeadline = ({ result }) => {
  const metrics = result?.metrics || {}
  const benchmark = result?.benchmark_metrics || null

  const started = result?.request?.initial_amount
  const ended = metrics.ending_balance
  const contributed = metrics.total_contributed

  const beat = benchmark && metrics.cagr !== null && benchmark.cagr !== null ? metrics.cagr - benchmark.cagr : null

  const recoveryMonths = monthsBetween(
    result?.dates || [],
    metrics.max_drawdown_trough_date,
    metrics.max_drawdown_recovery_date,
  )

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <h3 className="mb-2">
          {formatMoney(started)} became {formatMoney(ended)}
          {beat !== null && (
            <span className={`ms-3 fs-5 ${beat >= 0 ? 'text-success' : 'text-danger'}`}>
              {beat >= 0 ? 'beat' : 'trailed'} {result.benchmark_symbol} by {formatPercent(Math.abs(beat))}/yr
            </span>
          )}
        </h3>

        <p className="mb-2 fs-6">
          That is {formatPercent(metrics.cagr)} a year over {metrics.years ? metrics.years.toFixed(1) : '—'} years
          {contributed > started ? `, on ${formatMoney(contributed)} of total deposits` : ''}.
        </p>

        <p className="mb-2 fs-6">
          Worst drop: <strong>{formatPercent(metrics.max_drawdown)}</strong>
          {metrics.max_drawdown_peak_date && (
            <>
              {' '}
              ({monthYear(metrics.max_drawdown_peak_date)}–{monthYear(metrics.max_drawdown_trough_date)})
            </>
          )}
          {recoveryMonths
            ? `, recovered in ${recoveryMonths} month${recoveryMonths === 1 ? '' : 's'}.`
            : metrics.max_drawdown_trough_date
              ? ', and had not recovered by the end of the period.'
              : '.'}
        </p>

        {metrics.money_weighted_return !== null &&
          metrics.money_weighted_return !== undefined &&
          contributed > started && (
            <p className="text-muted fs-13px mb-0">
              Your personal return, counting when each deposit went in, was{' '}
              {formatPercent(metrics.money_weighted_return)} a year. It differs from the {formatPercent(metrics.cagr)}{' '}
              above because that figure measures the strategy and this one measures your timing.
            </p>
          )}
      </Card.Body>
    </Card>
  )
}

export default ResultsHeadline
