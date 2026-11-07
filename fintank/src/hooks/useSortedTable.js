import { useCallback, useEffect, useMemo, useState } from "react"

/**
 * Client-side sorting + pagination for a table whose whole dataset is already
 * in memory.
 *
 * Built for the index detail valuation table, which gets all ~494 constituents
 * in one cached payload and used to render only the first 25 of a server-side
 * PE ranking. Sorting here runs over the full array, so "highest P/E" really
 * does surface the most expensive names rather than re-ordering one page.
 *
 * Deliberately free of JSX so it can be reused by any other table and read on
 * its own. Pair it with `SortableHeaderCell` and `TablePager` in
 * `src/componentsLegacy/Table/`.
 *
 * `columns` MUST be a stable reference -- declare it at module scope, not
 * inline in the component -- otherwise the sort memo is invalidated on every
 * render and the ~500-row sort runs again for nothing.
 *
 * @param {Array<Object>} data        full dataset; may be undefined while loading
 * @param {Array<{key: string, label: string, type?: "string"|"number"}>} columns
 * @param {Object}  [options]
 * @param {string}  [options.initialSortKey]      column key to sort by first
 * @param {"asc"|"desc"} [options.initialDirection="asc"]
 * @param {number}  [options.initialRowsPerPage=25]
 */

const EMPTY_ROWS = []

const ASC = "asc"
const DESC = "desc"

// Nulls are pushed to the end of BOTH orders, so this sign is applied to the
// value comparison only -- never to the missing-value branch. A raw
// `-1 * compare()` would float every null to the top of a descending sort,
// which is exactly the "most expensive constituents" question being asked.
const directionSign = (direction) => (direction === DESC ? -1 : 1)

const isMissingString = (value) => value == null || String(value).trim() === ""

// `null`, `undefined`, `""`, `NaN` and `Infinity` are all "no value" for a
// numeric column. Treating them as missing is what keeps them from
// masquerading as zero.
const isMissingNumber = (value) =>
  value == null || value === "" || !Number.isFinite(Number(value))

const compareStrings = (left, right) =>
  String(left).localeCompare(String(right), undefined, { sensitivity: "base" })

const compareNumbers = (left, right) => {
  const a = Number(left)
  const b = Number(right)
  if (a < b) return -1
  if (a > b) return 1
  return 0
}

const COMPARATORS = {
  string: { compare: compareStrings, isMissing: isMissingString },
  number: { compare: compareNumbers, isMissing: isMissingNumber },
}

const comparatorFor = (column) =>
  column?.type === "string" ? COMPARATORS.string : COMPARATORS.number

export const useSortedTable = (data, columns, options = {}) => {
  const {
    initialSortKey = null,
    initialDirection = ASC,
    initialRowsPerPage = 25,
  } = options

  const rows = Array.isArray(data) ? data : EMPTY_ROWS

  const [sort, setSort] = useState({
    key: initialSortKey,
    direction: initialDirection,
  })
  const [rowsPerPage, setRowsPerPage] = useState(initialRowsPerPage)
  const [page, setPage] = useState(1)

  const columnsByKey = useMemo(() => {
    const lookup = {}
    for (const column of columns ?? []) lookup[column.key] = column
    return lookup
  }, [columns])

  const sortedRows = useMemo(() => {
    const column = sort.key ? columnsByKey[sort.key] : null
    if (!column) return rows

    const { compare, isMissing } = comparatorFor(column)
    const sign = directionSign(sort.direction)

    // Decorate with the original index and tie-break on it: a stable order for
    // equal values, independent of the engine's sort implementation, so rows
    // do not shuffle between renders.
    return rows
      .map((row, index) => ({ row, index }))
      .sort((a, b) => {
        const left = a.row?.[sort.key]
        const right = b.row?.[sort.key]
        const leftMissing = isMissing(left)
        const rightMissing = isMissing(right)

        if (leftMissing || rightMissing) {
          if (leftMissing && rightMissing) return a.index - b.index
          return leftMissing ? 1 : -1
        }

        const order = compare(left, right)
        return order === 0 ? a.index - b.index : sign * order
      })
      .map((entry) => entry.row)
  }, [rows, sort.key, sort.direction, columnsByKey])

  const totalRows = sortedRows.length
  const pageCount = Math.max(1, Math.ceil(totalRows / rowsPerPage))

  // Clamped here as well as in the effect below. The effect only runs after
  // the render that changed `pageCount`, so without this derived clamp the
  // paint in between would show an empty slice -- e.g. page 20 of 25-row pages
  // the moment rows-per-page becomes 100.
  const currentPage = Math.min(Math.max(1, page), pageCount)

  useEffect(() => {
    setPage((previous) => Math.min(Math.max(1, previous), pageCount))
  }, [pageCount])

  const pageRows = useMemo(() => {
    const start = (currentPage - 1) * rowsPerPage
    return sortedRows.slice(start, start + rowsPerPage)
  }, [sortedRows, currentPage, rowsPerPage])

  const requestSort = useCallback((key) => {
    setSort((previous) =>
      previous.key === key
        ? { key, direction: previous.direction === ASC ? DESC : ASC }
        : { key, direction: ASC }
    )
    // A re-sort changes what row 1 is, so the viewer should be looking at it.
    setPage(1)
  }, [])

  const ariaSortFor = useCallback(
    (key) => {
      if (sort.key !== key) return "none"
      return sort.direction === ASC ? "ascending" : "descending"
    },
    [sort.key, sort.direction]
  )

  const changeRowsPerPage = useCallback((value) => {
    const next = Number(value)
    if (!Number.isFinite(next) || next < 1) return
    // No reset to page 1: the clamp above keeps the viewer near where they
    // were when the page size grows.
    setRowsPerPage(next)
  }, [])

  return {
    // current page
    pageRows,
    // whole dataset in sort order, for export or an "all rows" view
    sortedRows,
    // sorting
    sortKey: sort.key,
    sortDirection: sort.direction,
    requestSort,
    ariaSortFor,
    // pagination
    page: currentPage,
    pageCount,
    setPage,
    rowsPerPage,
    setRowsPerPage: changeRowsPerPage,
    totalRows,
    // 1-based inclusive range of the current page; both 0 when there are no rows
    rangeStart: totalRows === 0 ? 0 : (currentPage - 1) * rowsPerPage + 1,
    rangeEnd: Math.min(currentPage * rowsPerPage, totalRows),
  }
}

export default useSortedTable
