import React, { useEffect, useRef, useState } from 'react'
import { Alert, Button, Spinner } from 'react-bootstrap'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faXmark } from '@fortawesome/free-solid-svg-icons'
import { useTechnicals } from '@hooks/useTechnicals'
import PanelErrorBoundary from './PanelErrorBoundary'
import PriceChart, { CHART_HEIGHT } from './PriceChart'
import OscillatorChart, { OSCILLATOR_HEIGHT } from './OscillatorChart'

const nameOf = (token) => token.split(':')[0]

// Total vertical footprint of the reserved `.symbol-panel__warnings` slot
// (0.5rem top margin + 24px box) in src/styles/pages/_chart-comparison.scss.
// The slot renders whether or not `payload.warnings` has entries, so the
// mounted `.symbol-panel__charts` content always has this exact height
// budgeted for it and never disagrees with the off-screen placeholder below,
// regardless of warning count.
const WARNINGS_HEIGHT = 32

/**
 * One ticker's column: sticky header, price chart, one sub-panel per
 * oscillator. Owns its own SWR subscription.
 *
 * Holds last-good data in a ref and renders it dimmed while a new spec is in
 * flight. SWR 1.3.0 has no keepPreviousData, so without this every debounced
 * spec change makes `data` undefined in all five panels at once and ~30 chart
 * instances unmount and remount.
 *
 * Off-screen panels render a fixed-height placeholder instead of mounting
 * charts, which keeps the live grouped-chart count near the visible set.
 * getGroupedCharts() filters on "has any group" rather than "has *my* group",
 * so its returned array is as long as every grouped chart on the page and
 * Tooltip.js walks it on every mousemove.
 */
const SymbolPanel = ({ symbol, spec, onRemove, root }) => {
  const { data, error, loading } = useTechnicals(symbol, spec)
  const lastGood = useRef(null)
  const [visible, setVisible] = useState(false)
  const container = useRef(null)

  if (data) lastGood.current = data

  useEffect(() => {
    const node = container.current
    if (!node || typeof IntersectionObserver === 'undefined') {
      setVisible(true)
      return undefined
    }
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), {
      root: root?.current ?? null,
      rootMargin: '200px',
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [root])

  const payload = data ?? lastGood.current
  const stale = Boolean(!data && lastGood.current)

  const oscillators = payload
    ? Object.entries(payload.indicators).filter(([, entry]) => entry.kind === 'oscillator')
    : []

  const chartsHeight = CHART_HEIGHT + oscillators.length * (OSCILLATOR_HEIGHT + 24) + WARNINGS_HEIGHT

  return (
    <PanelErrorBoundary symbol={symbol}>
      <section ref={container} className="symbol-panel" aria-label={`${symbol} charts`} tabIndex={-1}>
        <header className="symbol-panel__header">
          <span className="fw-semibold">{symbol}</span>
          <Button
            variant="link"
            size="sm"
            className="p-0"
            aria-label={`Remove ${symbol}`}
            onClick={() => onRemove(symbol)}
          >
            <FontAwesomeIcon icon={faXmark} />
          </Button>
        </header>

        {error && (
          <Alert variant="warning" className="m-3">
            {error.response?.status === 404 ? `No price history for ${symbol}` : `Could not load ${symbol}`}
          </Alert>
        )}

        {!error && loading && !lastGood.current && (
          <div
            className="d-flex align-items-center justify-content-center"
            style={{ height: chartsHeight || CHART_HEIGHT }}
          >
            <Spinner animation="border" role="status" size="sm" />
            <span className="visually-hidden">{`Loading ${symbol}`}</span>
          </div>
        )}

        {/* `.symbol-panel__body` carries the panel's vertical padding, wrapping
            both branches below, so the padding is never the mounted branch's to
            add and the off-screen branch's to forget -- CSS applies it equally
            either way and chartsHeight only has to account for content. */}
        {!error && payload && (
          <div className="symbol-panel__body">
            {!visible ? (
              <div style={{ height: chartsHeight }} aria-hidden="true" />
            ) : (
              <div className={stale ? 'symbol-panel__charts is-stale' : 'symbol-panel__charts'}>
                <PriceChart
                  symbol={symbol}
                  dates={payload.dates}
                  candle={payload.candle}
                  volume={payload.volume}
                  averageVolume={payload.average_volume}
                  overlays={Object.entries(payload.indicators)
                    .filter(([, entry]) => entry.kind === 'overlay')
                    .map(([token, entry]) => ({
                      token,
                      name: nameOf(token),
                      series: entry.series,
                    }))}
                />

                {oscillators.map(([token, entry]) => (
                  <OscillatorChart
                    key={token}
                    symbol={symbol}
                    token={token}
                    name={nameOf(token)}
                    entry={entry}
                    dates={payload.dates}
                  />
                ))}

                {/* Fixed-height slot rendered whether or not there are warnings --
                    see WARNINGS_HEIGHT above. */}
                <div className="symbol-panel__warnings small text-muted" aria-hidden={!(payload.warnings?.length > 0)}>
                  {payload.warnings?.length > 0 && (
                    <ul>
                      {payload.warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </section>
    </PanelErrorBoundary>
  )
}

export default SymbolPanel
