import React, { useMemo } from "react"
import { Row, Col } from "react-bootstrap"
import { Bar } from "react-chartjs-2"

import SectionUnavailable from "./SectionUnavailable"
import { useIndexRisk } from "@hooks/useIndexRisk"
import { buildBarChart, SERIES_COLORS } from "@utils/indexDetail/chartBuilders"
import { horizontalBarOptions } from "@utils/indexDetail/chartOptions"

const toPercent = (records, field) => records.map((record) => (record[field] ?? 0) * 100)

/**
 * Which constituents drive the index's volatility and its period return.
 *
 * Backed by the contr_to_var parquets, which had no reader in the backend until
 * this page needed them. Indexes without a constituent list get a 404 from the
 * endpoint and this section quietly disappears.
 */
const RiskDecomposition = ({ slug }) => {
  const { risk, error, isLoading } = useIndexRisk(slug)

  const charts = useMemo(() => {
    if (!risk) return null
    const volatility = risk.contribution_to_volatility ?? []
    const returns = risk.period_return ?? []
    if (!volatility.length && !returns.length) return null

    return {
      volatility: buildBarChart({
        labels: volatility.map((record) => record.symbol),
        values: toPercent(volatility, "pct_contr_to_vol"),
        label: "% of index volatility",
        color: SERIES_COLORS.peer,
      }),
      returns: buildBarChart({
        labels: returns.map((record) => record.symbol),
        values: toPercent(returns, "period_return"),
        label: "Period return",
        color: SERIES_COLORS.accent,
      }),
    }
  }, [risk])

  if (error) return null
  if (isLoading) return null
  if (!charts) {
    return (
      <SectionUnavailable
        title="Risk Decomposition"
        message="Constituent risk data is not available for this index."
      />
    )
  }

  const window = risk.window_days ? `${risk.window_days} day` : "Trailing"
  const count = risk.contribution_to_volatility?.length ?? 0

  return (
    <Row className="pt-3">
      <Col lg="6">
        <h4 className="mb-1">Contribution to Volatility: Top {count}</h4>
        <p className="text-muted text-sm">
          Share of the index&apos;s {window} volatility attributable to each holding, as of{" "}
          {risk.as_of?.slice(0, 10)}.
        </p>
        <Bar options={horizontalBarOptions} data={charts.volatility} height={400} width={300} />
      </Col>
      <Col lg="6">
        <h4 className="mb-1">
          {window} Return: Top {risk.period_return?.length ?? 0}
        </h4>
        <p className="text-muted text-sm">
          Best performing holdings over the same window.
        </p>
        <Bar options={horizontalBarOptions} data={charts.returns} height={400} width={300} />
      </Col>
    </Row>
  )
}

export default RiskDecomposition
