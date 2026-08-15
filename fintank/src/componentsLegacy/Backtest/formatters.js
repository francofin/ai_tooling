/** Display helpers shared across the results components. */
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export const formatPercent = (value, digits = 1) =>
  value === null || value === undefined || Number.isNaN(value) ? '—' : `${(Number(value) * 100).toFixed(digits)}%`

export const formatMoney = (value) =>
  value === null || value === undefined || Number.isNaN(value)
    ? '—'
    : `$${Math.round(Number(value)).toLocaleString('en-US')}`

export const formatNumber = (value, digits = 2) =>
  value === null || value === undefined || Number.isNaN(value) ? '—' : Number(value).toFixed(digits)

export const formatDate = (iso) => (iso ? iso : '—')

export const monthYear = (iso) => {
  if (!iso) return '—'
  const [year, month] = iso.split('-')
  return `${MONTHS[Number(month) - 1]} ${year}`
}

/** Trading days between two ISO dates in the result's own date array. */
export const monthsBetween = (dates, fromIso, toIso) => {
  if (!fromIso || !toIso) return null
  const from = dates.indexOf(fromIso)
  const to = dates.indexOf(toIso)
  if (from < 0 || to < 0) return null
  return Math.max(1, Math.round((to - from) / 21))
}
