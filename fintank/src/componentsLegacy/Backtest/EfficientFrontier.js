import React, { useMemo } from 'react'
import dynamic from 'next/dynamic'
import { Card } from 'react-bootstrap'

const ReactApexChart = dynamic(() => import('react-apexcharts'), { ssr: false })

/**
 * Random portfolios, the frontier curve, the minimum-variance and best-Sharpe
 * points, and the user's own mix.
 *
 * Computed on the whole period at once, which means it knows how everything
 * turned out. The caption says so — presented without that caveat it reads as a
 * recommendation, which it is not.
 */
const EfficientFrontier = ({ result }) => {
  const frontier = result?.frontier

  const series = useMemo(() => {
    if (!frontier) return []
    const pair = (volatility, portfolioReturn) => [
      Number((volatility * 100).toFixed(3)),
      Number((portfolioReturn * 100).toFixed(3)),
    ]

    return [
      {
        name: 'Possible mixes',
        type: 'scatter',
        data: frontier.scatter.volatility.map((volatility, i) => pair(volatility, frontier.scatter.return[i])),
      },
      {
        name: 'Best available (in hindsight)',
        type: 'line',
        data: frontier.frontier.volatility.map((volatility, i) => pair(volatility, frontier.frontier.return[i])),
      },
      {
        name: 'Steadiest mix',
        type: 'scatter',
        data: [pair(frontier.gmvp.volatility, frontier.gmvp.return)],
      },
      {
        name: 'Best return per unit of risk',
        type: 'scatter',
        data: [pair(frontier.tangency.volatility, frontier.tangency.return)],
      },
      ...(frontier.portfolio
        ? [
            {
              name: 'Your portfolio',
              type: 'scatter',
              data: [pair(frontier.portfolio.volatility, frontier.portfolio.return)],
            },
          ]
        : []),
    ]
  }, [frontier])

  if (!frontier) return null

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <h5 className="mb-2">Risk against return, for every mix you could have held</h5>
        <ReactApexChart
          type="line"
          height={360}
          series={series}
          options={{
            chart: { toolbar: { show: false }, animations: { enabled: false } },
            stroke: { width: [0, 3, 0, 0, 0], curve: 'smooth' },
            markers: { size: [3, 0, 9, 9, 11], strokeWidth: 0 },
            colors: ['#cfd4da', '#0d6efd', '#198754', '#fd7e14', '#dc3545'],
            xaxis: {
              type: 'numeric',
              title: { text: 'Volatility (% a year)' },
              labels: { formatter: (value) => `${Number(value).toFixed(0)}%` },
            },
            yaxis: {
              title: { text: 'Return (% a year)' },
              labels: { formatter: (value) => `${Number(value).toFixed(0)}%` },
            },
            legend: { position: 'top' },
            dataLabels: { enabled: false },
            tooltip: {
              shared: false,
              y: { formatter: (value) => `${Number(value).toFixed(1)}% return` },
              x: { formatter: (value) => `${Number(value).toFixed(1)}% volatility` },
            },
          }}
        />
        <p className="text-muted fs-13px mb-0">
          <strong>Illustration only.</strong> This chart was drawn knowing how the whole period turned out, so the curve
          is the best that could have been done with hindsight — not a mix anyone could have chosen in advance. Use it
          to see how much risk your portfolio took for the return it got, not as a recommendation.
        </p>
      </Card.Body>
    </Card>
  )
}

export default EfficientFrontier
