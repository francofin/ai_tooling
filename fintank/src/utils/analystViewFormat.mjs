// Pure helpers for the analyst view panel. Kept free of the @utils alias so
// `node --test` can import it.
export const EMPTY = '—'

const isNum = (v) => typeof v === 'number' && Number.isFinite(v)
const whole = (v) => `$${Math.round(v)}`

/**
 * Label for a target taken from a US listing of a non-US stock, e.g.
 * "Target $178 USD (≈ $255 CAD) · from SHOP's NYSE listing". Null when the
 * target is the stock's own (no source).
 */
export const targetLabel = (target, source) => {
  if (!source || !target || !isNum(target.consensus)) return null
  const cad = target.cad && isNum(target.cad.consensus) ? ` (≈ ${whole(target.cad.consensus)} CAD)` : ''
  return `Target ${whole(target.consensus)} USD${cad} · from ${source.symbol}'s ${source.exchange} listing`
}

/** Percent upside of a target over the price, or null when it can't be computed. */
export const upsidePct = (targetConsensus, price) => {
  if (!isNum(targetConsensus) || !isNum(price) || price <= 0) return null
  return (targetConsensus / price - 1) * 100
}

/** "low – high" with an em dash for any missing part. */
export const fmtRange = (range, formatter) => {
  const part = (v) => (isNum(v) ? formatter(v) : EMPTY)
  return `${part(range?.low)} – ${part(range?.high)}`
}
