import React, { useMemo, useState } from 'react'
import dynamic from 'next/dynamic'
import { Card, Form } from 'react-bootstrap'

const ReactApexChart = dynamic(() => import('react-apexcharts'), { ssr: false })

/**
 * Portfolio vs benchmark, with inception markers.
 *
 * Plots the time-weighted index rather than NAV so the line is comparable to the
 * benchmark even when the user made deposits — a NAV line against a benchmark
 * index is not a like-for-like comparison.
 */
const GrowthChart = ({ result }) => {
  const [logScale, setLogScale] = useState(false)

  const series = useMemo(() => {
    if (!result) return []
    const rows = [
      {
        name: 'Portfolio',
        data: result.dates.map((date, i) => ({ x: date, y: result.index[i] })),
      },
    ]
    if (result.benchmark_index?.length) {
      rows.push({
        name: result.benchmark_symbol || 'Benchmark',
        data: result.dates.map((date, i) => ({ x: date, y: result.benchmark_index[i] })),
      })
    }
    return rows
  }, [result])

  const annotations = useMemo(() => {
    const entries = (result?.composition_events || []).filter(
      (event) => event.action === 'entered' && event.date !== result.effective_start,
    )
    return {
      xaxis: entries.slice(0, 12).map((event) => ({
        x: new Date(event.date).getTime(),
        borderColor: '#9aa0a6',
        strokeDashArray: 4,
        label: {
          text: `${event.symbol} in`,
          style: { fontSize: '10px', background: '#f1f3f4' },
        },
      })),
    }
  }, [result])

  if (!result) return null

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <div className="d-flex justify-content-between align-items-center mb-2">
          <h5 className="mb-0">Growth of $1</h5>
          <Form.Check
            type="switch"
            id="growth-log-scale"
            label="Log scale"
            checked={logScale}
            onChange={(event) => setLogScale(event.target.checked)}
          />
        </div>
        <ReactApexChart
          type="line"
          height={340}
          series={series}
          options={{
            chart: { type: 'line', toolbar: { show: false }, animations: { enabled: false } },
            stroke: { width: 2, curve: 'straight' },
            xaxis: { type: 'datetime' },
            yaxis: {
              logarithmic: logScale,
              labels: { formatter: (value) => (value ? value.toFixed(2) : value) },
            },
            annotations,
            legend: { position: 'top' },
            tooltip: { x: { format: 'dd MMM yyyy' } },
            colors: ['#0d6efd', '#6c757d'],
            dataLabels: { enabled: false },
          }}
        />
        <p className="text-muted fs-13px mb-0">Dashed markers show when a holding first entered the portfolio.</p>
      </Card.Body>
    </Card>
  )
}

export default GrowthChart
