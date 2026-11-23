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
  }
}

export const toQuery = (state) => {
  const out = {}
  if (state.listed) out.listed = state.listed
  if (state.include?.length) out.include = state.include.join(',')
  if (state.exclude?.length) out.exclude = state.exclude.join(',')
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
