import React, { useMemo, useState } from 'react'
import { Row, Col, ButtonGroup, Button, Table } from 'react-bootstrap'
import { Bar } from 'react-chartjs-2'

import SectionUnavailable from './SectionUnavailable'
import { useIndexSectorContribution } from '@hooks/useIndexSectorContribution'
import { buildBarChart, SERIES_COLORS } from '@utils/indexDetail/chartBuilders'
import { horizontalBarOptions } from '@utils/indexDetail/chartOptions'

const WINDOW_LABELS = {
  '1W': { button: '1W', phrase: 'one-week' },
  '2W': { button: '2W', phrase: 'two-week' },
  '1M': { button: '1M', phrase: 'one-month' },
  '3M': { button: '3M', phrase: 'three-month' },
  ytd: { button: 'YTD', phrase: 'year-to-date' },
  '1Y': { button: '1Y', phrase: 'one-year' },
}
// The payload before the pipeline file exists (source "live") has only these.
const LIVE_WINDOWS = ['ytd', '1M']

// Lists whose members graduate to a bigger index at reconstitution: the
// holdings snapshot no longer has them, so long windows trail the index.
const MIGRATING = new Set(['r2000', 'rmicro', 'tsx_small_cap', 'msci_sm'])
const LONG_WINDOWS = new Set(['ytd', '1Y'])

const isNumber = (value) => typeof value === 'number' && Number.isFinite(value)

const format = (value, digits = 2) => (isNumber(value) ? value.toFixed(digits) : '--')

const signed = (value, digits = 2) => (isNumber(value) ? `${value > 0 ? '+' : ''}${value.toFixed(digits)}` : '--')

// Contributions under 1pp read better in basis points.
const contribution = (value) => {
  if (!isNumber(value)) return '--'
  return Math.abs(value) < 1 ? `${signed(value * 100, 0)}bp` : `${signed(value)}pp`
}

const ContributorTable = ({ title, rows }) => (
  <Col md="6" className="mb-3">
    <h6 className="mb-2">{title}</h6>
    <Table size="sm" responsive className="mb-0 small">
      <thead>
        <tr>
          <th>Symbol</th>
          <th>Sector</th>
          <th className="text-end">Start weight</th>
          <th className="text-end">Return</th>
          <th className="text-end">Contribution</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.symbol}>
            <td>{row.symbol}</td>
            <td className="text-muted">{row.sector ?? 'Unclassified'}</td>
            <td className="text-end">{format(row.weight_start_pct)}%</td>
            <td className="text-end">{signed(row.return_pct, 1)}%</td>
            <td className="text-end">{contribution(row.contribution_pp)}</td>
          </tr>
        ))}
      </tbody>
    </Table>
  </Col>
)

/**
 * How much each sector, and each holding, moved the index, in percentage
 * points of the index's price return.
 *
 * Deliberately a different question from the equal-weighted sector buckets in
 * the factor ranks: this one weights by index weight, so it answers "how much
 * did this sector move the index" rather than "how did the typical stock in
 * this sector do". The two can name different leaders and both be correct,
 * which is why the heading and the axis label both say "contribution".
 *
 * With source "pipeline" the weights are the holdings snapshot drifted back to
 * each window's start, so the bars sum to the index return; contributors,
 * concentration and coverage come with it. Until that file exists the backend
 * serves the older live calculation (YTD and 1M only) and those extras are
 * absent, so every one of them is optional here.
 */
const SectorContribution = ({ slug }) => {
  const { sectors, error, loading } = useIndexSectorContribution(slug)
  const [chosen, setChosen] = useState('ytd')

  const available = (Array.isArray(sectors?.windows_available) ? sectors.windows_available : LIVE_WINDOWS).filter(
    (key) => WINDOW_LABELS[key],
  )
  const active = available.includes(chosen) ? chosen : available.includes('ytd') ? 'ytd' : available[0]
  const windowPayload = sectors?.windows?.[active]

  const chart = useMemo(() => {
    const records = Array.isArray(windowPayload?.contribution)
      ? windowPayload.contribution.filter((record) => record && Number.isFinite(record.contribution_pp))
      : []
    if (!records.length) return null

    return buildBarChart({
      labels: records.map((record) => String(record.sector ?? 'Unclassified')),
      values: records.map((record) => record.contribution_pp),
      label: 'Contribution to index return (pp)',
      // Per-bar colours: Chart.js accepts an array here, so a sector that cost
      // the index return reads as a loss rather than another green bar.
      color: records.map((record) => (record.contribution_pp >= 0 ? SERIES_COLORS.accent : SERIES_COLORS.peer)),
    })
  }, [windowPayload])

  // A failed fetch and a fetch still in flight both render nothing: the page's
  // contract is that a slow or missing section never blocks the rest.
  if (error) return null
  if (loading) return null

  if (!chart) {
    return (
      <SectionUnavailable title="Sector Contribution" message="Sector contribution is not available for this index." />
    )
  }

  const breadth = windowPayload?.breadth ?? {}
  const matched = sectors?.matched ?? {}
  const hasBreadth = Number.isFinite(breadth.total) && breadth.total > 0
  const fromPipeline = sectors?.source === 'pipeline'
  const concentration = windowPayload?.concentration ?? {}
  const coverage = windowPayload?.coverage ?? {}
  const top = Array.isArray(windowPayload?.top_contributors) ? windowPayload.top_contributors : []
  const bottom = Array.isArray(windowPayload?.bottom_contributors) ? windowPayload.bottom_contributors : []
  const unattributed = isNumber(coverage.unattributed_pct) ? coverage.unattributed_pct : null
  const approximate = MIGRATING.has(sectors?.universe) && LONG_WINDOWS.has(active)

  return (
    <Row className="pt-3">
      <Col lg="12">
        <div className="d-flex flex-wrap align-items-center justify-content-between mb-2">
          <h5 className="mb-0">Return Attribution</h5>
          <ButtonGroup size="sm" aria-label="Attribution window">
            {available.map((key) => (
              <Button
                key={key}
                variant={active === key ? 'primary' : 'outline-primary'}
                onClick={() => setChosen(key)}
                active={active === key}
              >
                {WINDOW_LABELS[key].button}
              </Button>
            ))}
          </ButtonGroup>
        </div>

        <p className="text-muted small mb-3">
          {fromPipeline
            ? "Each sector's weight at the start of the window multiplied by its return"
            : "Each sector's index weight multiplied by its return"}
          , in percentage points of the index&apos;s {WINDOW_LABELS[active].phrase} move. Bars sum to{' '}
          {signed(windowPayload?.index_return_pp)}pp.
        </p>

        <Bar options={horizontalBarOptions} data={chart} />

        {(hasBreadth || fromPipeline) && (
          <p className="text-muted small mt-3 mb-2">
            {hasBreadth && (
              <>
                <strong>Breadth:</strong> {breadth.positive} of {breadth.total} up ({format(breadth.pct, 1)}%).{' '}
              </>
            )}
            {isNumber(concentration.top10_contribution_pp) && (
              <>
                <strong>Top 10:</strong> {signed(concentration.top10_contribution_pp)}pp of the move.{' '}
              </>
            )}
            {isNumber(concentration.effective_n) && (
              <>
                <strong>Effective names:</strong> {format(concentration.effective_n, 0)}.{' '}
              </>
            )}
            {isNumber(windowPayload?.cap_minus_ew_pp) && (
              <>
                <strong>Cap-weighted vs equal-weighted:</strong> {signed(windowPayload.cap_minus_ew_pp)}pp.
              </>
            )}
          </p>
        )}

        {top.length > 0 && (
          <Row className="mt-2">
            <ContributorTable title="Top contributors" rows={top} />
            <ContributorTable title="Bottom contributors" rows={bottom} />
          </Row>
        )}

        <p className="text-muted small mb-0">
          {fromPipeline ? (
            <>
              Price return
              {sectors?.currency_basis === 'local' && ', in local currency'}. Holdings as of{' '}
              {sectors?.holdings_as_of ?? '--'}; prices to {windowPayload?.end_date ?? '--'}.
              {unattributed !== null && unattributed > 0 && (
                <> Unattributed {format(unattributed, 1)}% of weight (no price data).</>
              )}
              {approximate && (
                <>
                  {' '}
                  Approximate over this window: holdings that moved up to a larger index during it are no longer in the
                  list.
                </>
              )}
            </>
          ) : (
            <>
              {Number.isFinite(matched.weight_pct) && matched.weight_pct < 99.99 && (
                <>
                  Covers {format(matched.weight_pct)}% of index weight ({matched.count} of {matched.total} holdings
                  matched).{' '}
                </>
              )}
              Weights as of {sectors?.weights_as_of ?? '--'}; returns as of {sectors?.returns_as_of ?? '--'}.
            </>
          )}
        </p>
      </Col>
    </Row>
  )
}

export default SectorContribution
