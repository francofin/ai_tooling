import React from "react"
import Link from "next/link"
import { Table } from "react-bootstrap"

import SectionUnavailable from "./SectionUnavailable"
import SortableHeaderCell from "@componentsLegacy/Table/SortableHeaderCell"
import TablePager from "@componentsLegacy/Table/TablePager"
import { useSortedTable } from "@hooks/useSortedTable"

// Module scope on purpose: `useSortedTable` memoises its sort on this
// reference, so an inline array would re-sort ~500 rows every render.
const COLUMNS = [
  { key: "symbol", label: "Stock", type: "string" },
  { key: "name", label: "Name", type: "string" },
  { key: "pe", label: "P/E", type: "number" },
  { key: "eps", label: "EPS", type: "number" },
  { key: "changesPercentage", label: "% Change", type: "number" },
  { key: "price", label: "Price", type: "number" },
  { key: "marketCap", label: "Market Cap", type: "number" },
]

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
 * Every constituent with a positive trailing PE, sortable and paginated.
 *
 * The backend excludes non-positive multiples, so loss-making names no longer
 * head the table -- sorting a raw PE ascending put a -5188 multiple at the top.
 * It sends all ~494 records in the one cached quotes payload; this used to
 * render only the cheapest 25 of them, which made "which names are the most
 * expensive?" unanswerable from the page.
 *
 * Sorting runs over the whole dataset, not the visible page, so a descending
 * PE sort surfaces the genuinely priciest constituents. Missing values sort to
 * the end of both directions -- see `useSortedTable`.
 */
const ValuationsSection = ({ quotes }) => {
  const {
    pageRows,
    requestSort,
    ariaSortFor,
    page,
    pageCount,
    setPage,
    rowsPerPage,
    setRowsPerPage,
    totalRows,
    rangeStart,
    rangeEnd,
  } = useSortedTable(quotes?.valuations, COLUMNS, {
    initialSortKey: "pe",
    initialDirection: "asc",
    initialRowsPerPage: 25,
  })

  if (!totalRows) {
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
        All {totalRows} constituents with positive trailing earnings, ranked by P/E from
        lowest by default. Select any column heading to re-rank the full list.
      </p>
      <Table striped responsive hover className="text-gray-700 text-sm">
        <thead>
          <tr>
            {COLUMNS.map((column) => (
              <SortableHeaderCell
                key={column.key}
                column={column}
                ariaSort={ariaSortFor(column.key)}
                onSort={requestSort}
              />
            ))}
          </tr>
        </thead>
        <tbody>
          {pageRows.map((item) => (
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
      <TablePager
        page={page}
        pageCount={pageCount}
        onPageChange={setPage}
        rowsPerPage={rowsPerPage}
        onRowsPerPageChange={setRowsPerPage}
        rangeStart={rangeStart}
        rangeEnd={rangeEnd}
        totalRows={totalRows}
        label="constituents"
      />
    </div>
  )
}

export default ValuationsSection
