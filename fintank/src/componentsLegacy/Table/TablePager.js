import React from "react"
import { Form, Pagination } from "react-bootstrap"

/**
 * Page controls, rows-per-page selector and a "Showing X-Y of N" indicator.
 *
 * react-bootstrap's own `Pagination`, not `react-paginate` (which the older
 * screener list uses) and not the unused `datatables.net-*` packages: the
 * dataset is already in memory, so the only thing needed is a window of page
 * numbers around the current one.
 *
 * Pair with `useSortedTable` in `src/hooks/useSortedTable.js` -- its return
 * value supplies every prop here.
 */

const WINDOW_SIZE = 5

/** Up to WINDOW_SIZE consecutive page numbers, centred on `page` where it can be. */
const pageWindow = (page, pageCount) => {
  const span = Math.min(WINDOW_SIZE, pageCount)
  const start = Math.min(Math.max(1, page - Math.floor(span / 2)), pageCount - span + 1)
  return Array.from({ length: span }, (_, offset) => start + offset)
}

const TablePager = ({
  page,
  pageCount,
  onPageChange,
  rowsPerPage,
  onRowsPerPageChange,
  rowsPerPageOptions = [25, 50, 100],
  rangeStart,
  rangeEnd,
  totalRows,
  label = "rows",
  className = "",
}) => {
  if (!totalRows) return null

  const pages = pageWindow(page, pageCount)
  const firstShown = pages[0]
  const lastShown = pages[pages.length - 1]

  return (
    <div
      className={`d-flex flex-wrap align-items-center justify-content-between gap-3 ${className}`.trim()}
    >
      <div className="d-flex align-items-center gap-2">
        <span className="text-muted text-sm">
          Showing {rangeStart}&ndash;{rangeEnd} of {totalRows} {label}
        </span>
        <Form.Label htmlFor="table-pager-rows" className="text-muted text-sm mb-0 ms-2">
          Rows
        </Form.Label>
        <Form.Select
          id="table-pager-rows"
          size="sm"
          style={{ width: "auto" }}
          value={rowsPerPage}
          onChange={(event) => onRowsPerPageChange(event.target.value)}
        >
          {rowsPerPageOptions.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </Form.Select>
      </div>

      {pageCount > 1 && (
        <Pagination size="sm" className="mb-0">
          <Pagination.First
            aria-label="First page"
            disabled={page === 1}
            onClick={() => onPageChange(1)}
          />
          <Pagination.Prev
            aria-label="Previous page"
            disabled={page === 1}
            onClick={() => onPageChange(page - 1)}
          />

          {firstShown > 1 && <Pagination.Ellipsis disabled />}

          {pages.map((number) => (
            <Pagination.Item
              key={number}
              active={number === page}
              onClick={() => onPageChange(number)}
            >
              {number}
            </Pagination.Item>
          ))}

          {lastShown < pageCount && <Pagination.Ellipsis disabled />}

          <Pagination.Next
            aria-label="Next page"
            disabled={page === pageCount}
            onClick={() => onPageChange(page + 1)}
          />
          <Pagination.Last
            aria-label="Last page"
            disabled={page === pageCount}
            onClick={() => onPageChange(pageCount)}
          />
        </Pagination>
      )}
    </div>
  )
}

export default TablePager
