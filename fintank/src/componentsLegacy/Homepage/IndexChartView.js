import React from "react"
import { Chart } from "react-chartjs-2"

/**
 * Draws one index chart plus its latest-level banner.
 *
 * Presentational on purpose: it takes data rather than fetching it, so a caller
 * that needs to transform the series first — the picker slices it to a date
 * range — renders exactly the same chart the homepage does.
 */
const IndexChartView = ({ chartData, chartOptions, indexName, loading, chartType = "bar", height = 360 }) => {
  if (loading || !chartOptions) return <div style={{ height: height + 60 }} />

  const prices = chartData.datasets[0]?.data ?? []
  const latestPrice = prices[prices.length - 1]
  const prevPrice = prices[prices.length - 2]
  const positive = prevPrice == null || latestPrice >= prevPrice
  const color = positive ? "#16a34a" : "#dc2626"

  return (
    <div>
      <div style={{ position: "relative", height }}>
        <Chart type={chartType} options={chartOptions} data={chartData} />
      </div>
      {latestPrice != null && (
        <div
          className="fw-bold"
          style={{
            background: positive ? "rgba(22,163,74,0.08)" : "rgba(220,38,38,0.08)",
            border: `1px solid ${color}`,
            borderRadius: 6,
            padding: "6px 12px",
            marginTop: 8,
            fontSize: "1rem",
            color,
          }}
        >
          {indexName}: ${Number(latestPrice).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      )}
    </div>
  )
}

export default IndexChartView
