/**
 * Formatters for the quote fields shared by the markets cards and the index
 * heat map tooltip.
 *
 * These live here rather than in a page so the two renderings of the same quote
 * can't drift apart — the heat map's hover is meant to show exactly what the
 * card shows.
 */

export const fmtPrice = (v) => {
  if (v == null) return "—"
  if (v >= 1000) return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (v >= 1) return v.toFixed(2)
  if (v >= 0.01) return v.toFixed(4)
  return v.toFixed(6)
}

export const fmtMarketCap = (v) => {
  if (v == null) return "—"
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`
  return `$${(v / 1e3).toFixed(2)}K`
}

export const fmtTimestamp = (ts) =>
  new Date(ts * 1000).toLocaleString("en-US", {
    month: "short", day: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  })

export const fmtPercent = (v) =>
  v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`

/**
 * The card's field list, in card order, as `[label, value]` pairs.
 *
 * Entries whose underlying value is absent are dropped, mirroring the card's
 * per-field null guards — crypto quotes carry marketCap and the index quotes
 * generally don't, so both shapes flow through this unchanged.
 */
export const quoteDetailRows = (quote) => {
  const rows = [
    ["Low", quote.dayLow, fmtPrice, "$"],
    ["High", quote.dayHigh, fmtPrice, "$"],
    ["52W Low", quote.yearLow, fmtPrice, "$"],
    ["52W High", quote.yearHigh, fmtPrice, "$"],
    ["Mkt Cap", quote.marketCap, fmtMarketCap, ""],
    ["50D Avg", quote.priceAvg50, fmtPrice, "$"],
    ["200D Avg", quote.priceAvg200, fmtPrice, "$"],
    ["EPS", quote.eps, (v) => v.toFixed(2), ""],
    ["P/E", quote.pe, (v) => v.toFixed(2), ""],
  ]

  return rows
    .filter(([, value]) => value != null)
    .map(([label, value, format, prefix]) => [label, `${prefix}${format(value)}`])
}
