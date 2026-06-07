import React from "react"
import { Chart } from "react-chartjs-2"
import { useIndexCharter } from "../../hooks/useIndexChart"

const IndexChartCard = ({ index, chartType = "bar" }) => {
  const { chartData, chartOptions, loading } = useIndexCharter(index)

  if (loading || !chartOptions) return <div style={{ height: 200 }} />

  return (
    <Chart
      type={chartType}
      options={chartOptions}
      data={chartData}
      height={100}
      width={200}
    />
  )
}

export default IndexChartCard
