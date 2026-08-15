import React, { useState } from 'react'
import { Button, Card, Collapse, Table } from 'react-bootstrap'

import { formatMoney, formatNumber, formatPercent } from './formatters'

const PERCENT_ROWS = [
  ['cagr', 'Annual return (CAGR)'],
  ['annualized_return', 'Annual return (average)'],
  ['annualized_volatility', 'Volatility'],
  ['max_drawdown', 'Worst drop'],
  ['var_95', 'Bad-day threshold (95%)'],
  ['cvar_95', 'Average of the worst 5% of days'],
  ['alpha', 'Alpha vs benchmark'],
]

const NUMBER_ROWS = [
  ['sharpe', 'Sharpe ratio'],
  ['sortino', 'Sortino ratio'],
  ['calmar', 'Calmar ratio'],
  ['beta', 'Beta vs benchmark'],
  ['up_capture', 'Up capture'],
  ['down_capture', 'Down capture'],
  ['annual_turnover', 'Turnover per year'],
]

const MONEY_ROWS = [
  ['ending_balance', 'Ending balance'],
  ['total_contributed', 'Total put in'],
  ['total_gain', 'Total gain'],
  ['total_costs_paid', 'Trading costs paid'],
]

/** The full §9 table, portfolio against benchmark, behind a disclosure. */
const StatsTable = ({ result }) => {
  const [open, setOpen] = useState(false)
  const metrics = result?.metrics || {}
  const benchmark = result?.benchmark_metrics || {}

  const row = (key, label, format) => (
    <tr key={key}>
      <td>{label}</td>
      <td className="text-end">{format(metrics[key])}</td>
      <td className="text-end text-muted">{format(benchmark[key])}</td>
    </tr>
  )

  if (!result) return null

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <Button variant="link" className="p-0 text-decoration-none" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? '▾' : '▸'} Full statistics
        </Button>

        <Collapse in={open}>
          <div className="pt-3">
            <Table size="sm" hover responsive className="align-middle">
              <thead>
                <tr>
                  <th>Measure</th>
                  <th className="text-end">Portfolio</th>
                  <th className="text-end">{result.benchmark_symbol || 'Benchmark'}</th>
                </tr>
              </thead>
              <tbody>
                {PERCENT_ROWS.map(([key, label]) => row(key, label, (v) => formatPercent(v)))}
                {NUMBER_ROWS.map(([key, label]) => row(key, label, (v) => formatNumber(v)))}
                {MONEY_ROWS.map(([key, label]) => row(key, label, (v) => formatMoney(v)))}
                <tr>
                  <td>Best calendar year</td>
                  <td className="text-end">
                    {metrics.best_year} ({formatPercent(metrics.best_year_return)})
                  </td>
                  <td className="text-end text-muted">
                    {benchmark.best_year} ({formatPercent(benchmark.best_year_return)})
                  </td>
                </tr>
                <tr>
                  <td>Worst calendar year</td>
                  <td className="text-end">
                    {metrics.worst_year} ({formatPercent(metrics.worst_year_return)})
                  </td>
                  <td className="text-end text-muted">
                    {benchmark.worst_year} ({formatPercent(benchmark.worst_year_return)})
                  </td>
                </tr>
              </tbody>
            </Table>

            <h6 className="mt-4 fs-13px text-muted">Where the return and the risk came from</h6>
            <Table size="sm" responsive className="align-middle">
              <thead>
                <tr>
                  <th>Holding</th>
                  <th className="text-end">Share of return</th>
                  <th className="text-end">Share of risk</th>
                </tr>
              </thead>
              <tbody>
                {(result.symbols || []).map((symbol) => (
                  <tr key={symbol}>
                    <td>{symbol}</td>
                    <td className="text-end">{formatPercent(metrics.contribution_to_return?.[symbol])}</td>
                    <td className="text-end">{formatPercent(metrics.contribution_to_risk?.[symbol])}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <p className="text-muted fs-13px mb-0">
              Every return and risk figure above is measured on the strategy itself, with deposits stripped out, so the
              deposit schedule cannot flatter it.
            </p>
            {result.request?.weighting_scheme === 'risk_parity' && (
              <p className="text-muted fs-13px mb-0 mt-2">
                <strong>Why these risk shares are not equal.</strong> Risk parity equalized risk using the{' '}
                {result.request.lookback_days} trading days before each rebalance. The shares above are measured across
                the whole period against your final weights, which is the portfolio you actually held — so the two
                legitimately differ, often by a lot. Neither number is wrong.
              </p>
            )}
          </div>
        </Collapse>
      </Card.Body>
    </Card>
  )
}

export default StatsTable
