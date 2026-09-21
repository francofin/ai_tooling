import React from "react"
import { Row, Col } from "react-bootstrap"

/**
 * How the index has behaved, as opposed to where it has got to.
 *
 * Volatility, return-to-risk and up/down day counts over three windows, read
 * from the same price parquet the chart above already uses -- 32 of its 51
 * columns describe the series' own behaviour and had no reader until now.
 *
 * A snapshot, not a series: the values are the latest row, so they carry the
 * chart's own `as_of` rather than implying today. That matters here because the
 * upstream pipeline is hand-run and can sit weeks behind.
 */

const METRICS = [
  {
    key: "volatility",
    label: "Volatility",
    // Stored annualised decimal: 0.20 is 20%.
    format: (value) => `${(value * 100).toFixed(1)}%`,
  },
  {
    key: "return_to_risk",
    label: "Return / risk",
    format: (value) => value.toFixed(2),
  },
]

const IndexInternals = ({ internals, asOf }) => {
  const windows = Array.isArray(internals) ? internals : []
  if (!windows.length) return null

  return (
    <div className="pt-3">
      <div className="d-flex flex-wrap align-items-baseline justify-content-between mb-2">
        <h5 className="mb-0">Index Internals</h5>
        {asOf && <span className="text-muted small">As of {asOf}</span>}
      </div>

      <Row className="g-3">
        {windows.map((window) => {
          const ratio = window.up_down_ratio
          const hasDays =
            Number.isFinite(window.up_days) && Number.isFinite(window.down_days)

          return (
            <Col md="4" key={window.key}>
              <div className="border rounded p-3 h-100">
                <div className="text-uppercase text-muted small mb-2">
                  {window.label}
                </div>

                {METRICS.map(({ key, label, format }) => (
                  <div
                    className="d-flex justify-content-between align-items-baseline"
                    key={key}
                  >
                    <span className="text-muted small">{label}</span>
                    <span className="fw-bold">
                      {Number.isFinite(window[key]) ? format(window[key]) : "--"}
                    </span>
                  </div>
                ))}

                <div className="d-flex justify-content-between align-items-baseline">
                  <span className="text-muted small">Up / down days</span>
                  <span className="fw-bold">
                    {hasDays ? `${window.up_days} / ${window.down_days}` : "--"}
                    {Number.isFinite(ratio) && (
                      <span
                        className="fw-normal small ms-2"
                        style={{ color: ratio >= 1 ? "green" : "red" }}
                      >
                        {ratio.toFixed(2)}x
                      </span>
                    )}
                  </span>
                </div>
              </div>
            </Col>
          )
        })}
      </Row>
    </div>
  )
}

export default IndexInternals
