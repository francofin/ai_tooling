import React, { useMemo, useState } from "react"
import { Row, Col, ButtonGroup, Button } from "react-bootstrap"
import { Bar } from "react-chartjs-2"

import SectionUnavailable from "./SectionUnavailable"
import { useIndexSectorContribution } from "@hooks/useIndexSectorContribution"
import { buildBarChart, SERIES_COLORS } from "@utils/indexDetail/chartBuilders"
import { horizontalBarOptions } from "@utils/indexDetail/chartOptions"

const WINDOWS = [
  { key: "ytd", label: "Year to date" },
  { key: "1M", label: "1 month" },
]

const format = (value, digits = 2) =>
  typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "--"

const signed = (value) =>
  typeof value === "number" && Number.isFinite(value)
    ? `${value > 0 ? "+" : ""}${value.toFixed(2)}`
    : "--"

/**
 * How much each sector moved the index, in percentage points of index return.
 *
 * Deliberately a different question from the equal-weighted sector buckets in
 * the factor ranks: this one weights by index weight, so it answers "how much
 * did this sector move the index" rather than "how did the typical stock in
 * this sector do". The two can name different leaders and both be correct,
 * which is why the heading and the axis label both say "contribution".
 *
 * Weights and returns come from two different pipeline outputs with their own
 * as_of dates -- four weeks apart in production -- so both are printed rather
 * than collapsed into a single "data as of".
 */
const SectorContribution = ({ slug }) => {
  const { sectors, error, loading } = useIndexSectorContribution(slug)
  const [active, setActive] = useState("ytd")

  const windowPayload = sectors?.windows?.[active]

  const chart = useMemo(() => {
    const records = Array.isArray(windowPayload?.contribution)
      ? windowPayload.contribution.filter(
          (record) => record && Number.isFinite(record.contribution_pp)
        )
      : []
    if (!records.length) return null

    return buildBarChart({
      labels: records.map((record) => String(record.sector ?? "Unclassified")),
      values: records.map((record) => record.contribution_pp),
      label: "Contribution to index return (pp)",
      // Per-bar colours: Chart.js accepts an array here, so a sector that cost
      // the index return reads as a loss rather than another green bar.
      color: records.map((record) =>
        record.contribution_pp >= 0 ? SERIES_COLORS.accent : SERIES_COLORS.peer
      ),
    })
  }, [windowPayload])

  // A failed fetch and a fetch still in flight both render nothing: the page's
  // contract is that a slow or missing section never blocks the rest.
  if (error) return null
  if (loading) return null

  if (!chart) {
    return (
      <SectionUnavailable
        title="Sector Contribution"
        message="Sector contribution is not available for this index."
      />
    )
  }

  const breadth = windowPayload?.breadth ?? {}
  const matched = sectors?.matched ?? {}
  const hasBreadth = Number.isFinite(breadth.total) && breadth.total > 0

  return (
    <Row className="pt-3">
      <Col lg="12">
        <div className="d-flex flex-wrap align-items-center justify-content-between mb-2">
          <h5 className="mb-0">Sector Contribution</h5>
          <ButtonGroup size="sm" aria-label="Contribution window">
            {WINDOWS.map(({ key, label }) => (
              <Button
                key={key}
                variant={active === key ? "primary" : "outline-primary"}
                onClick={() => setActive(key)}
                active={active === key}
              >
                {label}
              </Button>
            ))}
          </ButtonGroup>
        </div>

        <p className="text-muted small mb-3">
          Each sector&apos;s index weight multiplied by its return, in percentage points
          of the index&apos;s {active === "ytd" ? "year-to-date" : "one-month"} move. Bars
          sum to {signed(windowPayload?.index_return_pp)}pp.
        </p>

        <Bar options={horizontalBarOptions} data={chart} />

        {hasBreadth && (
          <p className="text-muted small mt-3 mb-1">
            <strong>Breadth:</strong> {breadth.positive} of {breadth.total} constituents
            positive ({format(breadth.pct, 1)}%).
          </p>
        )}

        <p className="text-muted small mb-0">
          {Number.isFinite(matched.weight_pct) && matched.weight_pct < 99.99 && (
            <>
              Covers {format(matched.weight_pct)}% of index weight ({matched.count} of{" "}
              {matched.total} holdings matched).{" "}
            </>
          )}
          Weights as of {sectors?.weights_as_of ?? "--"}; returns as of{" "}
          {sectors?.returns_as_of ?? "--"}.
        </p>
      </Col>
    </Row>
  )
}

export default SectorContribution
