import React, { useMemo } from 'react'
import dynamic from 'next/dynamic'
import { Card } from 'react-bootstrap'

const ReactApexChart = dynamic(() => import('react-apexcharts'), { ssr: false })

const SAMPLE_TARGET = 400

/**
 * Stacked weights plus the effective asset count.
 *
 * The most informative view on the page: it is where staggered inception becomes
 * visible rather than merely disclosed, which is why it is not tucked behind a
 * disclosure. Series are downsampled — 5,000 points × 20 symbols would stall the
 * browser and would not show anything the sampled version does not.
 */
const AllocationOverTime = ({ result }) => {
  const { series, countSeries } = useMemo(() => {
    if (!result) return { series: [], countSeries: [] }

    const step = Math.max(1, Math.ceil(result.dates.length / SAMPLE_TARGET))
    const sampled = result.dates.filter((_, i) => i % step === 0)

    const weightSeries = Object.keys(result.weights_over_time).map((symbol) => ({
      name: symbol,
      data: result.weights_over_time[symbol]
        .filter((_, i) => i % step === 0)
        .map((weight, i) => ({ x: sampled[i], y: Number((weight * 100).toFixed(2)) })),
    }))

    const counts = [
      {
        name: 'Holdings owned',
        data: result.effective_asset_count
          .filter((_, i) => i % step === 0)
          .map((count, i) => ({ x: sampled[i], y: count })),
      },
    ]

    return { series: weightSeries, countSeries: counts }
  }, [result])

  if (!result) return null

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <h5 className="mb-2">What you actually owned, over time</h5>
        <ReactApexChart
          type="area"
          height={300}
          series={series}
          options={{
            chart: {
              type: 'area',
              stacked: true,
              toolbar: { show: false },
              animations: { enabled: false },
            },
            stroke: { width: 0 },
            fill: { opacity: 0.85 },
            xaxis: { type: 'datetime' },
            yaxis: { max: 100, labels: { formatter: (value) => `${value.toFixed(0)}%` } },
            legend: { position: 'bottom' },
            dataLabels: { enabled: false },
            tooltip: { y: { formatter: (value) => `${value.toFixed(1)}%` } },
          }}
        />

        <h6 className="mt-3 mb-1 fs-13px text-muted">Number of your holdings that existed and were owned</h6>
        <ReactApexChart
          type="line"
          height={140}
          series={countSeries}
          options={{
            chart: { type: 'line', toolbar: { show: false }, animations: { enabled: false } },
            stroke: { width: 2, curve: 'stepline' },
            xaxis: { type: 'datetime' },
            yaxis: {
              min: 0,
              tickAmount: Math.min(result.symbols.length, 5),
              labels: { formatter: (value) => value.toFixed(0) },
            },
            colors: ['#198754'],
            dataLabels: { enabled: false },
            legend: { show: false },
          }}
        />
      </Card.Body>
    </Card>
  )
}

export default AllocationOverTime
