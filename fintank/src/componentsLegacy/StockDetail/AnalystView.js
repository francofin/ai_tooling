import React, { useState } from 'react'
import { ButtonGroup, Button, ProgressBar, Table } from 'react-bootstrap'
import { useAnalystView, useAnalystQuarterly } from '@hooks/useAnalystView'
import useStockQuote from '@hooks/useStockQuote'
import { formatPrice, formatMarketCap, EMPTY } from '@utils/stockQuoteFormat'
import { fmtRange, targetLabel, upsidePct } from '@utils/analystViewFormat.mjs'

const METRICS = [
  ['revenue', 'Revenue', (v, c) => formatMarketCap(v, c)],
  ['eps', 'EPS', (v, c) => formatPrice(v, c)],
  ['ebitda', 'EBITDA', (v, c) => formatMarketCap(v, c)],
]

// Strong buy to strong sell, green to red.
const RATING_BARS = [
  ['strongBuy', 'Strong buy', 'success'],
  ['buy', 'Buy', 'info'],
  ['hold', 'Hold', 'warning'],
  ['sell', 'Sell', 'danger'],
  ['strongSell', 'Strong sell', 'dark'],
]

const EstimatesTable = ({ periods, currency }) => (
  <div className="table-responsive">
    <Table hover size="sm" className="align-middle">
      <thead>
        <tr>
          <th>Metric</th>
          {periods.map((p) => (
            <th key={p.date} className="text-end text-nowrap">
              {p.date}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {METRICS.map(([key, label, fmt]) => (
          <tr key={key}>
            <td className="text-nowrap">{label}</td>
            {periods.map((p) => (
              <td key={`${key}-${p.date}`} className="text-end text-nowrap">
                <div>{p[key]?.avg == null ? EMPTY : fmt(p[key].avg, currency)}</div>
                <div className="text-muted text-xs">{fmtRange(p[key], (v) => fmt(v, currency))}</div>
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </Table>
  </div>
)

const RatingsBar = ({ ratings }) => (
  <div className="mb-4">
    <div className="mb-1">
      <strong>{ratings.consensus || EMPTY}</strong>
      <span className="text-muted ms-2">{ratings.total} analysts</span>
    </div>
    <ProgressBar>
      {RATING_BARS.map(([key, label, variant]) =>
        ratings[key] > 0 ? (
          <ProgressBar
            key={key}
            variant={variant}
            now={ratings[key]}
            max={ratings.total || 1}
            label={ratings[key]}
            title={`${label}: ${ratings[key]}`}
          />
        ) : null,
      )}
    </ProgressBar>
    <div className="d-flex flex-wrap gap-3 text-muted text-xs mt-1">
      {RATING_BARS.map(([key, label]) => (
        <span key={key}>
          {label} {ratings[key] ?? 0}
        </span>
      ))}
    </div>
  </div>
)

const PriceTarget = ({ target, source, currency, price }) => {
  // A US-listing target is in USD, so compare it with the US listing's price.
  const unit = source ? 'USD' : currency
  const upside = upsidePct(target.consensus, price)
  const label = targetLabel(target, source)
  return (
    <div className="mb-4">
      <div className="d-flex flex-wrap gap-4">
        <div>
          <div className="text-muted text-xs">Consensus</div>
          <div className="fw-bold">{formatPrice(target.consensus, unit)}</div>
        </div>
        <div>
          <div className="text-muted text-xs">Median</div>
          <div>{formatPrice(target.median, unit)}</div>
        </div>
        <div>
          <div className="text-muted text-xs">Range</div>
          <div>{fmtRange(target, (v) => formatPrice(v, unit))}</div>
        </div>
        {upside != null && (
          <div>
            <div className="text-muted text-xs">Upside</div>
            <div className={upside >= 0 ? 'text-success' : 'text-danger'}>
              {upside >= 0 ? '+' : ''}
              {upside.toFixed(1)}%
            </div>
          </div>
        )}
      </div>
      {label && <div className="text-muted text-sm mt-1">{label}</div>}
    </div>
  )
}

const AnalystView = ({ symbol, currency }) => {
  const [period, setPeriod] = useState('annual')
  const { data, error, isLoading } = useAnalystView(symbol)
  const quarterly = useAnalystQuarterly(symbol, period === 'quarter')
  const { data: quoteData } = useStockQuote(data?.source?.symbol || symbol)

  // No coverage (404) and provider failures (502) both hide the panel.
  if (isLoading || error || !data) return null

  const { ratings, target, source } = data
  const annual = data.estimates?.annual || []
  const periods = period === 'quarter' ? quarterly.data?.estimates?.quarter || [] : annual
  if (!annual.length && !ratings && !target) return null

  return (
    <div className="text-block">
      <h4 className="mb-3">Analyst view</h4>

      {annual.length > 0 && (
        <div className="mb-4">
          <div className="d-flex justify-content-between align-items-center mb-2">
            <span className="text-muted text-sm">
              Analyst estimates{data.reporting_currency ? ` (${data.reporting_currency})` : ''}
            </span>
            <ButtonGroup size="sm">
              <Button variant={period === 'annual' ? 'primary' : 'outline-primary'} onClick={() => setPeriod('annual')}>
                Annual
              </Button>
              <Button
                variant={period === 'quarter' ? 'primary' : 'outline-primary'}
                onClick={() => setPeriod('quarter')}
              >
                Quarterly
              </Button>
            </ButtonGroup>
          </div>
          {period === 'quarter' && quarterly.isLoading && <p className="text-muted">Loading quarterly estimates…</p>}
          {period === 'quarter' && quarterly.error && (
            <p className="text-muted">Quarterly estimates unavailable right now.</p>
          )}
          {periods.length > 0 && <EstimatesTable periods={periods} currency={data.reporting_currency} />}
        </div>
      )}

      {ratings && <RatingsBar ratings={ratings} />}
      {target && <PriceTarget target={target} source={source} currency={currency} price={quoteData?.quote?.price} />}

      <p className="text-muted text-xs mb-0">
        Consensus from analysts covering the stock, via Financial Modeling Prep.
      </p>
    </div>
  )
}

export default AnalystView
