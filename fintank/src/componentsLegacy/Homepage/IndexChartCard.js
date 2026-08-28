import React from "react"
import IndexChartView from "./IndexChartView"
import { useIndexCharter } from "../../hooks/useIndexChart"

/**
 * One index chart, fetching its own data. Used by the homepage grid.
 *
 * Callers that need to transform the series before it is drawn should use
 * `useIndexCharter` with `IndexChartView` directly instead.
 */
const IndexChartCard = ({ index, chartType = "bar" }) => {
  const { chartData, chartOptions, indexName, loading } = useIndexCharter(index)

  return (
    <IndexChartView
      chartData={chartData}
      chartOptions={chartOptions}
      indexName={indexName}
      loading={loading}
      chartType={chartType}
    />
  )
}

export default IndexChartCard
