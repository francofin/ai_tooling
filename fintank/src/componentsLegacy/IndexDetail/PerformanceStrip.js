import React from "react"

/**
 * Trailing returns for the header.
 *
 * One map over a period list, replacing seven copy-pasted ternary blocks that
 * each repeated the whole <li> twice to pick a colour. Values come from the
 * price series the page already loads, so no FMP key reaches the browser.
 */

const PERIODS = [
  { key: "1D", label: "1 Day" },
  { key: "5D", label: "5 Day" },
  { key: "1M", label: "1 Month" },
  { key: "3M", label: "3 Month" },
  { key: "6M", label: "6 Month" },
  { key: "YTD", label: "YTD" },
  { key: "1Y", label: "1 Year" },
]

const PerformanceStrip = ({ performance }) => {
  const available = PERIODS.filter(
    (period) => typeof performance?.[period.key] === "number"
  )

  if (!available.length) return null

  return (
    <ul className="list-inline text-sm mb-4">
      {available.map((period) => {
        const value = performance[period.key]
        return (
          <li
            key={period.key}
            className="list-inline-item me-3"
            style={{ color: value >= 0 ? "green" : "red" }}
          >
            {period.label}: {value >= 0 ? "+" : ""}
            {value.toFixed(1)}%
          </li>
        )
      })}
    </ul>
  )
}

export default PerformanceStrip
