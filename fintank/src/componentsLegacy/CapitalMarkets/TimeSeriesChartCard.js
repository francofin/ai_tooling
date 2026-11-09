import React, { useMemo } from 'react'
import { Col } from 'react-bootstrap'
import { Line } from 'react-chartjs-2'
import FrequencySelect from './FrequencySelect'
import { buildLineChart } from '@utils/capitalMarkets/chartBuilders'
import { indexLineOptions } from '@utils/capitalMarkets/chartOptions'
import { describeSeries } from '@utils/capitalMarkets/spreadNarrative.mjs'

/**
 * One titled chart: heading, bullet-point commentary written from the series
 * on screen (see spreadNarrative.mjs), an optional frequency selector, and the
 * line itself. Replaces 33 hand-written copies of this markup.
 */
const TimeSeriesChartCard = ({ id, title, narrative, label, color, series, frequency, onFrequencyChange }) => {
  const bullets = useMemo(() => describeSeries(narrative, series, frequency), [narrative, series, frequency])
  const chart = useMemo(() => buildLineChart({ series, label, color }), [series, label, color])

  return (
    <Col lg="6">
      <div>
        <h3 className="mb-3">{title}</h3>
        {bullets.length > 0 && (
          <ul className="text-muted fw-light ps-3">
            {bullets.map((bullet) => (
              <li key={bullet.label} className="mb-1">
                <span className="fw-normal">{bullet.label}:</span> {bullet.text}
              </li>
            ))}
          </ul>
        )}
      </div>
      {onFrequencyChange && <FrequencySelect id={`frequency-${id}`} value={frequency} onChange={onFrequencyChange} />}
      <Line options={indexLineOptions} data={chart} height={100} width={200} />
    </Col>
  )
}

export default TimeSeriesChartCard
