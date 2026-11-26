// URL <-> page state for /fund-finder. Pure, so it is testable with `node --test`.
export const MAX_PER_LIST = 10
const LISTED = ['ca', 'us', 'both']

const first = (value) => (Array.isArray(value) ? value[0] : value)

const parseList = (value) => {
  const raw = first(value)
  if (typeof raw !== 'string') return []
  const out = []
  for (const part of raw.split(',')) {
    const symbol = part.trim().toUpperCase()
    if (symbol && !out.includes(symbol)) out.push(symbol)
    if (out.length >= MAX_PER_LIST) break
  }
  return out
}

export const parseQuery = (urlQuery) => {
  const q = urlQuery || {}
  const listed = first(q.listed)
  return {
    listed: LISTED.includes(listed) ? listed : null,
    include: parseList(q.include),
    exclude: parseList(q.exclude),
    leveraged: first(q.leveraged) === '1',
  }
}

export const toQuery = (state) => {
  const out = {}
  if (state.listed) out.listed = state.listed
  if (state.include?.length) out.include = state.include.join(',')
  if (state.exclude?.length) out.exclude = state.exclude.join(',')
  if (state.leveraged) out.leveraged = '1'
  return out
}

export const canSearch = (state) => Boolean(state.listed) && state.include.length > 0

// MER in percent (FMP etf/info expenseRatio: 0.18 means 0.18%). FMP sends 0
// when it has no value, so 0 shows as missing, like null.
export const formatMer = (mer) => {
  const n = Number(mer)
  return mer == null || Number.isNaN(n) || n === 0 ? '—' : `${n.toFixed(2)}%`
}

// Footnote for the funds the pipeline leaves out (FMP lists only their top
// 10 holdings, rescaled to 100%); null when there are none or no count.
export const top10Footnote = (count) => {
  const n = Number(count)
  if (count == null || !Number.isInteger(n) || n <= 0) return null
  return n === 1
    ? '1 fund is left out because FMP lists only its top 10 holdings.'
    : `${n} funds are left out because FMP lists only their top 10 holdings.`
}

// Leveraged funds (e.g. "Enhanced" 1.25x ETFs) are shown only when asked.
export const LEVERAGED_FOOTNOTE =
  'Leveraged funds borrow to hold more than 100% of their assets; weights shown are their full exposure.'

// Badge text from holdings coverage in percent: 124.4 -> "1.24x"; null when
// missing or not over 100%.
export const leverageLabel = (coveragePct) => {
  const n = Number(coveragePct)
  if (coveragePct == null || Number.isNaN(n) || n <= 100) return null
  return `${(n / 100).toFixed(2)}x`
}
