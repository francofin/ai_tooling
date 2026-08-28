import React from "react"
import PerformanceStrip from "./PerformanceStrip"

const formatDate = (value) => {
  if (!value) return null
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  })
}

/**
 * Title, trailing returns, and the index's background copy.
 *
 * `asOf` is the last date in the price series rather than today's date, which
 * the old page printed. If the pipeline stops running, that shows here instead
 * of the page implying the numbers are current.
 */
const IndexHeader = ({ title, history, performance, asOf, priceSource }) => (
  <div className="text-block">
    <PerformanceStrip performance={performance} />

    <h1>{title}</h1>
    <div className="text-muted text-uppercase mb-4">
      {`A historical perspective of the ${title}`}
    </div>

    <ul className="list-inline text-sm mb-4">
      {asOf && (
        <li className="list-inline-item me-3">Data as of: {formatDate(asOf)}</li>
      )}
      {priceSource === "etf" && (
        <li className="list-inline-item me-3">
          Index level tracked via its constituent ETF
        </li>
      )}
    </ul>

    {history && (
      <>
        <h6 className="mb-3">Index History</h6>
        <p className="text-muted fw-light">{history}</p>
      </>
    )}
  </div>
)

export default IndexHeader
