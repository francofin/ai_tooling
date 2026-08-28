import React from "react"
import Link from "next/link"

const MoverList = ({ title, movers }) => (
  <>
    <p className="text-muted text-center mb-1">
      <span className="text-primary h5">{title}</span>
    </p>
    {movers.map((stock) => (
      <div key={stock.symbol}>
        <hr className="my-1" />
        <h5 className="text-sm text-center">
          <Link href={`/stock-data/${stock.symbol}`}>{stock.symbol}</Link>: {stock.name}{" "}
          <span style={{ color: stock.changesPercentage >= 0 ? "green" : "red" }}>
            {stock.changesPercentage >= 0 ? "+" : ""}
            {Number(stock.changesPercentage).toFixed(2)}%
          </span>
        </h5>
      </div>
    ))}
  </>
)

/**
 * Sticky panel of the day's best and worst constituents.
 *
 * Both lists come from one cached quotes payload, so the panel and the
 * valuation table below it share a single FMP round trip per universe per day.
 * Symbols link through to their detail page, which the old panel did not do.
 */
const MoversPanel = ({ quotes }) => {
  const top = quotes?.top_performers ?? []
  const bottom = quotes?.bottom_performers ?? []

  if (!top.length && !bottom.length) return null

  return (
    <div style={{ top: "100px" }} className="p-4 shadow ms-lg-4 rounded sticky-top">
      {top.length > 0 && <MoverList title={`Top ${top.length} Performers`} movers={top} />}
      {bottom.length > 0 && (
        <>
          <br />
          <MoverList title={`Bottom ${bottom.length} Performers`} movers={bottom} />
        </>
      )}
      {quotes?.market_open === false && (
        <p className="text-muted text-center text-sm mt-3 mb-0">
          Market closed — last available quotes.
        </p>
      )}
    </div>
  )
}

export default MoversPanel
