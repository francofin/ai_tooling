import React from "react"
import Link from "next/link"
import { Table } from "react-bootstrap"

import SectionUnavailable from "./SectionUnavailable"

const VISIBLE_ROWS = 25

const fmtMarketCap = (value) => {
  if (value == null) return "—"
  if (value >= 1e12) return `$${(value / 1e12).toFixed(2)}T`
  if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`
  if (value >= 1e6) return `$${(value / 1e6).toFixed(2)}M`
  return `$${(value / 1e3).toFixed(2)}K`
}

const fmtNumber = (value, digits = 2) =>
  value == null ? "—" : Number(value).toFixed(digits)

/**
 * Constituents ranked cheapest first on trailing PE.
 *
 * The backend excludes non-positive multiples, so loss-making names no longer
 * head the table -- sorting a raw PE ascending put a -5188 multiple at the top.
 * Only the cheapest {VISIBLE_ROWS} are rendered; the full ranking runs to
 * several hundred rows and was previously dumped into the DOM in one go.
 */
const ValuationsSection = ({ quotes }) => {
  const valuations = quotes?.valuations ?? []

  if (!valuations.length) {
    return (
      <SectionUnavailable
        title="Stock Valuations"
        message="Valuation data is not available for this index."
      />
    )
  }

  return (
    <div className="text-block">
      <h4 className="mb-2">Stock Valuations</h4>
      <p className="text-muted text-sm">
        The {Math.min(VISIBLE_ROWS, valuations.length)} lowest trailing P/E ratios of{" "}
        {valuations.length} constituents with positive earnings.
      </p>
      <Table striped responsive hover className="text-gray-700 text-sm">
        <thead>
          <tr>
            <th className="py-3 align-middle">Stock</th>
            <th className="py-3 align-middle">Name</th>
            <th className="py-3 align-middle">P/E</th>
            <th className="py-3 align-middle">EPS</th>
            <th className="py-3 align-middle">% Change</th>
            <th className="py-3 align-middle">Price</th>
            <th className="py-3 align-middle">Market Cap</th>
          </tr>
        </thead>
        <tbody>
          {valuations.slice(0, VISIBLE_ROWS).map((item) => (
            <tr key={item.symbol} className="py-3 align-middle">
              <td>
                <Link href={`/stock-data/${item.symbol}`}>{item.symbol}</Link>
              </td>
              <td>{item.name}</td>
              <td>{fmtNumber(item.pe)}</td>
              <td>{fmtNumber(item.eps)}</td>
              <td style={{ color: item.changesPercentage >= 0 ? "green" : "red" }}>
                {fmtNumber(item.changesPercentage)}%
              </td>
              <td>${fmtNumber(item.price)}</td>
              <td>{fmtMarketCap(item.marketCap)}</td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  )
}

export default ValuationsSection
