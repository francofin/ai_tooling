import React, { useMemo } from 'react'
import dynamic from 'next/dynamic'
import { Card } from 'react-bootstrap'

const ReactApexChart = dynamic(() => import('react-apexcharts'), { ssr: false })

/** Underwater plot: how far below its previous high the portfolio sat. */
const DrawdownChart = ({ result }) => {
  const series = useMemo(() => {
    if (!result) return []
    const rows = [
      {
        name: 'Portfolio',
        data: result.dates.map((date, i) => ({ x: date, y: result.drawdown[i] * 100 })),
      },
    ]
    if (result.benchmark_drawdown?.length) {
      rows.push({
        name: result.benchmark_symbol || 'Benchmark',
        data: result.dates.map((date, i) => ({
          x: date,
          y: result.benchmark_drawdown[i] * 100,
        })),
      })
    }
    return rows
  }, [result])

  if (!result) return null

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <h5 className="mb-2">How far underwater</h5>
        <ReactApexChart
          type="area"
          height={260}
          series={series}
          options={{
            chart: { type: 'area', toolbar: { show: false }, animations: { enabled: false } },
            stroke: { width: 1.5, curve: 'straight' },
            fill: { type: 'gradient', gradient: { opacityFrom: 0.4, opacityTo: 0.05 } },
            xaxis: { type: 'datetime' },
            yaxis: { labels: { formatter: (value) => `${value.toFixed(0)}%` } },
            legend: { position: 'top' },
            colors: ['#dc3545', '#adb5bd'],
            dataLabels: { enabled: false },
            tooltip: { y: { formatter: (value) => `${value.toFixed(1)}%` } },
          }}
        />
      </Card.Body>
    </Card>
  )
}

export default DrawdownChart
