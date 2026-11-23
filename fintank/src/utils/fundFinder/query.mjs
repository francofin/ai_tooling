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
