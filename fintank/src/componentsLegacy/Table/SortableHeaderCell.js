import React from "react"

/**
 * A `<th>` that sorts its column when clicked.
 *
 * The clickable part is a real `<button>` so it is reachable by keyboard and
 * announced as a control; `aria-sort` goes on the `<th>` itself, which is where
 * screen readers look for it. The caret is `aria-hidden` -- `aria-sort` already
 * says the same thing to assistive tech, and a second announcement is noise.
 *
 * Pair with `useSortedTable` in `src/hooks/useSortedTable.js`.
 */

const CARETS = { ascending: "▲", descending: "▼" }
const IDLE_CARET = "↕"

const SortableHeaderCell = ({ column, ariaSort, onSort, className = "" }) => {
  const active = ariaSort === "ascending" || ariaSort === "descending"

  return (
    <th
      scope="col"
      aria-sort={ariaSort}
      className={`py-3 align-middle ${className}`.trim()}
    >
      <button
        type="button"
        onClick={() => onSort(column.key)}
        className="btn btn-link p-0 border-0 align-baseline text-reset text-decoration-none fw-semibold d-inline-flex align-items-center gap-1"
      >
        <span>{column.label}</span>
        <span aria-hidden="true" className={active ? "" : "text-muted opacity-50"}>
          {active ? CARETS[ariaSort] : IDLE_CARET}
        </span>
      </button>
    </th>
  )
}

export default SortableHeaderCell
