/**
 * Sizing and colour maths for the index heat map.
 *
 * Kept apart from the component so the ordering rules can be exercised on their
 * own — the sizing is the part that is easy to get subtly wrong.
 */

// Colour bands shared with the homepage heat map (`hooks/useIndexHeatMap.js`), so
// a given move reads the same shade wherever it is drawn.
export const COLOR_RANGES = [
  { from: -9999, to: -6, color: "#5a0a10" },
  { from: -5.9999, to: -3, color: "#3d0912" },
  { from: -2.9999, to: -0.0001, color: "#3d0912" },
  { from: -0.0001, to: 0.0001, color: "#1c1c1e" },
  { from: 0.0001, to: 3, color: "#0d3a18" },
  { from: 3.0001, to: 9999, color: "#0d4a1f" },
]

export const NEUTRAL_COLOR = "#1c1c1e"
const POSITIVE_COLOR = "#0d3a18"
const NEGATIVE_COLOR = "#3d0912"

/**
 * Quotes arrive from several endpoints and a change % is occasionally a string,
 * so every value is coerced once. Anything non-numeric returns null so the caller
 * can drop the tile rather than poison the min/max the layout is scaled against.
 */
export const toNumber = (v) => {
  // `Number(null)` and `Number("")` are both 0, which would turn a quote with no
  // change % into a fabricated flat tile. Reject the empty cases before coercing.
  if (v === null || v === undefined || v === "") return null
  const n = typeof v === "number" ? v : Number(v)
  return Number.isFinite(n) ? n : null
}

/**
 * The bands leave hairline gaps between each `to` and the next `from` (-3 to
 * -2.9999, and so on). ApexCharts absorbed those itself when it owned the colour
 * scale; picking the colour here means a move landing in one would come out
 * neutral grey and read as a bug, so an unmatched value falls back on its sign.
 */
export const bandColor = (change) => {
  const band = COLOR_RANGES.find((r) => change >= r.from && change <= r.to)
  if (band) return band.color
  if (change > 0) return POSITIVE_COLOR
  if (change < 0) return NEGATIVE_COLOR
  return NEUTRAL_COLOR
}

// Share of the spread given to every tile as a floor, so the worst performer
// stays visible instead of collapsing to nothing.
const FLOOR_RATIO = 0.08

/**
 * Builds the size function for one set of changes.
 *
 * Tiles are sized by the signed change, so -5.5 is smaller than +2.02. A treemap
 * can only size by a positive number, so the changes are shifted onto a positive
 * scale by subtracting the lowest one — a straight translation, which preserves
 * the numeric ordering exactly and just moves the zero point to the day's worst
 * performer. Without a floor that worst performer would land on 0 and vanish, so
 * every tile gets one proportional to the spread.
 *
 * @param changes  numeric change percentages
 * @returns        (change) => positive tile size
 */
export const tileSizer = (changes) => {
  if (changes.length === 0) return () => 1

  const min = Math.min(...changes)
  const max = Math.max(...changes)
  const spread = max - min
  // Every index moved the same amount (or there is only one), so there is no
  // ordering to express — fall back to equal tiles.
  const floor = spread === 0 ? 1 : spread * FLOOR_RATIO

  return (change) => change - min + floor
}
