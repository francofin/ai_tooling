// Pure helpers for the earnings hub. Kept free of the @utils alias so
// `node --test` can import it.
export const EMPTY = '—'

export const PANEL_DISCLAIMER = 'AI-written summary of the earnings call. One opinion, not investment advice.'

export const MODAL_DISCLAIMER =
  "This note was written by AI (Claude) from the company's earnings call transcript. It is one opinion, not investment advice, and may contain errors. Check figures against the company's filings before making any decision."

// Schema section keys in display order.
export const NOTE_SECTIONS = [
  ['results_vs_consensus', 'Results vs consensus'],
  ['guidance', 'Guidance'],
  ['management_tone', 'Management tone'],
  ['qa_themes', 'Analyst Q&A themes'],
  ['what_changed', 'What changed since last quarter'],
  ['risks', 'Risks'],
  ['bull_case', 'Bull case'],
  ['bear_case', 'Bear case'],
  ['watch_next', 'What to watch next quarter'],
]

/** NOTE_SECTIONS, minus what_changed when the note has none (the only nullable section). */
export const visibleSections = (sections) =>
  NOTE_SECTIONS.filter(([key]) => key !== 'what_changed' || sections?.what_changed)

const QUARTER_RE = /^(\d{4})-Q([1-4])$/

/** "2026-Q3" -> "Fiscal Q3 2026". */
export const quarterLabel = (quarter) => {
  const m = QUARTER_RE.exec(quarter || '')
  return m ? `Fiscal Q${m[2]} ${m[1]}` : String(quarter ?? '')
}

/** A `?note=` value, or null unless it is exactly a quarter key. */
export const parseNoteParam = (value) => (typeof value === 'string' && QUARTER_RE.test(value) ? value : null)

const LEANS = {
  bullish: { text: 'Bullish', variant: 'success' },
  neutral: { text: 'Neutral', variant: 'secondary' },
  bearish: { text: 'Bearish', variant: 'danger' },
}

export const leanBadge = (lean) => LEANS[lean] || LEANS.neutral

/** Monday plus the next four weekdays, as ISO dates (UTC maths, no DST drift). */
export const weekDays = (mondayISO) => {
  const [y, m, d] = mondayISO.split('-').map(Number)
  return [0, 1, 2, 3, 4].map((i) => new Date(Date.UTC(y, m - 1, d + i)).toISOString().slice(0, 10))
}

/** ISO date of the Monday on or before `date` (a Date, read in UTC). */
export const mondayOf = (date) => {
  const d = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()))
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7))
  return d.toISOString().slice(0, 10)
}

/** Shift an ISO date by whole days. */
export const addDays = (iso, days) => {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10)
}

export const fmtEps = (v) => (typeof v === 'number' && Number.isFinite(v) ? v.toFixed(2) : EMPTY)
