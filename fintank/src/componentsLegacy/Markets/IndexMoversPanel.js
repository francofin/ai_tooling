import React, { useState } from "react"
import Link from "next/link"
import { Form, Spinner } from "react-bootstrap"
import { useIndexQuotes } from "../../hooks/useIndexQuotes"
import indexMetaData from "../../data/index-meta.json"

// Derived from the same metadata the index detail pages use, so the picker can
// only offer slugs `/index-quotes/<slug>/` actually serves.
const INDEX_OPTIONS = Object.entries(indexMetaData).map(([value, meta]) => ({
  value,
  label: meta.title,
}))

const fmtChange = (value) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return "—"
  return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`
}

/**
 * One mover. The sidebar is 250px wide, so the row is `TICKER: +0.00%` and the
 * company name is carried on the title attribute rather than shown — spelling it
 * out inline is what makes the list overflow.
 */
const MoverRow = ({ stock }) => {
  const change = Number(stock.changesPercentage)
  const tone = change > 0 ? "up" : change < 0 ? "down" : "flat"

  return (
    <li className="index-movers-row" title={stock.name || stock.symbol}>
      <Link href={`/stock-data/${stock.symbol}`} className="index-movers-symbol">
        {stock.symbol}
      </Link>
      <span className={`index-movers-change index-movers-${tone}`}>{fmtChange(change)}</span>
    </li>
  )
}

/**
 * Top and bottom constituents for a chosen index, sized for the profile sidebar.
 *
 * Reads the same cached `/index-quotes/<slug>/` payload the index detail page
 * uses — one FMP call per universe per day, shared by every viewer — so adding
 * this panel costs no additional upstream requests.
 */
const IndexMoversPanel = ({ defaultSlug = "sp500" }) => {
  const [slug, setSlug] = useState(defaultSlug)
  const { quotes, error, isLoading } = useIndexQuotes(slug)

  const top = quotes?.top_performers ?? []
  const bottom = quotes?.bottom_performers ?? []

  return (
    <div className="index-movers-panel">
      <div className="fw-bold mb-2 fs-16px">Index movers</div>

      <Form.Group controlId="index-movers-select" className="mb-2">
        <Form.Label className="visually-hidden">Index</Form.Label>
        <Form.Select
          size="sm"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          aria-label="Index"
        >
          {INDEX_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Form.Select>
      </Form.Group>

      {isLoading && (
        <div className="text-center py-3">
          <Spinner animation="border" variant="light" size="sm" role="status">
            <span className="visually-hidden">Loading...</span>
          </Spinner>
        </div>
      )}

      {error && (
        <p className="fs-12px text-inverse text-opacity-50 mb-0">Movers are unavailable right now.</p>
      )}

      {!isLoading && !error && top.length === 0 && bottom.length === 0 && (
        <p className="fs-12px text-inverse text-opacity-50 mb-0">No constituent quotes available.</p>
      )}

      {/* One scroll container for both lists, so the sidebar keeps its height
          however many movers come back and the page itself does not grow. */}
      {(top.length > 0 || bottom.length > 0) && (
        <div className="index-movers-scroll">
          {top.length > 0 && (
            <>
              <div className="index-movers-heading">Top {top.length}</div>
              <ul className="index-movers-list">
                {top.map((stock) => (
                  <MoverRow key={`top-${stock.symbol}`} stock={stock} />
                ))}
              </ul>
            </>
          )}

          {bottom.length > 0 && (
            <>
              <div className="index-movers-heading">Bottom {bottom.length}</div>
              <ul className="index-movers-list">
                {bottom.map((stock) => (
                  <MoverRow key={`bottom-${stock.symbol}`} stock={stock} />
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {quotes?.market_open === false && (
        <p className="fs-12px text-inverse text-opacity-50 mt-2 mb-0">
          Market closed — last available quotes.
        </p>
      )}
    </div>
  )
}

export default IndexMoversPanel
