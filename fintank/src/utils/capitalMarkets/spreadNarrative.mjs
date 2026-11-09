/**
 * Bullet-point commentary for the capital-markets charts, written from the
 * series on screen so it never goes stale.
 *
 * Pure: a narrative definition (from equitySeries.json / economicSeries.json)
 * and one {dates, value} series in, a list of {label, text} bullets out. Every
 * threshold that decides the wording lives here or in the definition, and each
 * series is judged against its own history, so there are no hard-coded "normal"
 * levels to keep up to date.
 *
 * Kinds:
 *   relative  equity spread, comparison return minus base return (decimals)
 *   level     a yield, rate or growth figure; optional value bands
 *   curve     a yield-curve slope in basis points (long minus short)
 *
 * Run the tests: node --test src/utils/capitalMarkets/spreadNarrative.test.mjs
 */

// Equity spreads: within this many percentage points of zero is "roughly
// level", and a smaller three-month move is "little changed".
export const RELATIVE_LEVEL_PP = 1
export const RELATIVE_CHANGE_PP = 1
// Yield curve: within this many basis points of zero is "roughly flat"; a
// smaller three-month move is "little changed".
export const CURVE_FLAT_BP = 10
export const CURVE_CHANGE_BP = 10
// Top and bottom decile of a series' own history count as unusual.
export const EXTREME_PCT = 10
// "Direction" compares with the reading this many months before the latest.
export const LOOKBACK_MONTHS = 3
// Fewer readings than this and the history bullet is left out.
export const MIN_HISTORY = 12

const WINDOW_PHRASES = {
  Quarterly: '3 months',
  Yearly: '12 months',
  'Three Year': '3 years',
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

const parseDate = (value) => {
  const [y, m, d] = String(value).slice(0, 10).split('-').map(Number)
  return { y, m, d }
}

const isDaily = (dates) => {
  if (dates.length < 3) return false
  const a = new Date(String(dates[dates.length - 3]).slice(0, 10))
  const b = new Date(String(dates[dates.length - 1]).slice(0, 10))
  return (b - a) / 86400000 < 20
}

const formatDate = (value, daily) => {
  const { y, m, d } = parseDate(value)
  return daily ? `${MONTHS[m - 1]} ${d}, ${y}` : `${MONTHS[m - 1]} ${y}`
}

/** Finite readings, paired with their dates, oldest first. */
const points = (series) => {
  const dates = series?.dates ?? []
  const values = series?.value ?? []
  const out = []
  for (let i = 0; i < Math.min(dates.length, values.length); i += 1) {
    const v = values[i]
    if (typeof v === 'number' && Number.isFinite(v)) out.push({ date: String(dates[i]), value: v })
  }
  return out
}

/** The last reading on or before LOOKBACK_MONTHS before the latest one. */
const lookback = (pts) => {
  const { y, m, d } = parseDate(pts[pts.length - 1].date)
  const target = new Date(Date.UTC(y, m - 1 - LOOKBACK_MONTHS, d))
  const key = target.toISOString().slice(0, 10)
  for (let i = pts.length - 2; i >= 0; i -= 1) {
    if (pts[i].date.slice(0, 10) <= key) return pts[i]
  }
  return null
}

const quantile = (sorted, q) => {
  const pos = (sorted.length - 1) * q
  const lo = Math.floor(pos)
  const hi = Math.ceil(pos)
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo)
}

/** Where the latest reading sits in the series' own history. */
const history = (pts) => {
  const values = pts.map((p) => p.value)
  const last = values[values.length - 1]
  const below = values.filter((v) => v < last).length
  const above = values.filter((v) => v > last).length
  const sorted = [...values].sort((a, b) => a - b)
  return {
    pctBelow: Math.round((below / values.length) * 100),
    pctAbove: Math.round((above / values.length) * 100),
    p10: quantile(sorted, EXTREME_PCT / 100),
    p90: quantile(sorted, 1 - EXTREME_PCT / 100),
    since: parseDate(pts[0].date).y,
  }
}

/** "high", "low" or null: is the latest reading in the top or bottom decile? */
const extreme = (h) => {
  if (h.pctBelow >= 100 - EXTREME_PCT) return 'high'
  if (h.pctAbove >= 100 - EXTREME_PCT) return 'low'
  return null
}

const historyText = (h, fmt, phrases = {}) => {
  const where = extreme(h)
  if (where === 'high') {
    return `Higher than ${h.pctBelow}% of readings since ${h.since}${phrases.high ? `: ${phrases.high}` : ''}.`
  }
  if (where === 'low') {
    return `Lower than ${h.pctAbove}% of readings since ${h.since}${phrases.low ? `: ${phrases.low}` : ''}.`
  }
  return `Within its usual range since ${h.since}: the middle 80% of readings runs from ${fmt(h.p10)} to ${fmt(h.p90)}.`
}

// Signed to the given precision; a value that rounds to zero carries no sign.
const signed = (v, digits = 1) => {
  const shown = Math.abs(v).toFixed(digits)
  if (Number(shown) === 0) return shown
  return `${v > 0 ? '+' : '−'}${shown}`
}
const abs = (v, digits = 1) => Math.abs(v).toFixed(digits)

// ── relative ────────────────────────────────────────────────────────────────

const describeRelative = (n, pts, frequency) => {
  const pp = (v) => `${signed(v * 100)}pp`
  const latest = pts[pts.length - 1]
  const x = latest.value * 100
  const window = WINDOW_PHRASES[frequency] ?? WINDOW_PHRASES.Quarterly
  const bullets = [
    {
      label: 'What it shows',
      text: `${n.comp} return minus ${n.base} return over a rolling ${window}${n.note ? ` (${n.note})` : ''}. Above zero, ${n.compShort} ahead; below zero, ${n.baseShort} ahead.`,
    },
  ]

  const leader = x >= RELATIVE_LEVEL_PP ? 'comp' : x <= -RELATIVE_LEVEL_PP ? 'base' : null
  const when = formatDate(latest.date, false)
  bullets.push({
    label: `Latest (${when})`,
    text: leader
      ? `${capitalise(leader === 'comp' ? n.compShort : n.baseShort)} ahead by ${abs(x)}pp.`
      : `Roughly level (${pp(latest.value)}).`,
  })

  const prev = lookback(pts)
  if (prev) {
    const delta = (latest.value - prev.value) * 100
    bullets.push({
      label: 'Direction',
      text:
        Math.abs(delta) < RELATIVE_CHANGE_PP
          ? `Little changed from ${pp(prev.value)} three months earlier.`
          : `Swung ${abs(delta)}pp toward ${delta > 0 ? n.compShort : n.baseShort} from ${pp(prev.value)} three months earlier.`,
    })
  }

  let where = null
  if (pts.length >= MIN_HISTORY) {
    const h = history(pts)
    where = extreme(h)
    bullets.push({
      label: 'Versus history',
      text: historyText(h, pp, {
        high: `unusually far in favor of ${n.compShort}`,
        low: `unusually far in favor of ${n.baseShort}`,
      }),
    })
  }

  let signal = leader === 'comp' ? n.compAhead : leader === 'base' ? n.baseAhead : (n.level ?? LEVEL_DEFAULT)
  const stretched = (leader === 'comp' && where === 'high') || (leader === 'base' && where === 'low')
  if (stretched) signal += ' At this extreme, the preference is unusually strong.'
  bullets.push({ label: 'What it can signal', text: signal })
  return bullets
}

const LEVEL_DEFAULT = 'Neither side has a meaningful edge over this window.'

// ── level ───────────────────────────────────────────────────────────────────

const describeLevel = (n, pts) => {
  const scale = n.scale ?? 1
  const digits = n.decimals ?? 2
  const unit = n.unit ?? '%'
  const fmt = (raw) => {
    const v = raw * scale
    return unit === 'bp' ? `${Math.round(v)}bp` : `${n.signedValue ? signed(v, digits) : v.toFixed(digits)}%`
  }
  const latest = pts[pts.length - 1]
  const daily = isDaily(pts.map((p) => p.date))
  const bullets = [{ label: 'What it shows', text: n.about }]
  bullets.push({
    label: `Latest (${formatDate(latest.date, daily)})`,
    text: `${fmt(latest.value)}${n.valueSuffix ? ` ${n.valueSuffix}` : ''}.`,
  })

  // Change in the definition's change unit: bp of a percent figure, or pp.
  const changeUnit = n.changeUnit ?? (unit === 'bp' ? 'bp' : 'pp')
  const toChange = (raw) => {
    const v = raw * scale
    return changeUnit === 'bp' && unit === '%' ? v * 100 : v
  }
  const fmtChange = (v) => (changeUnit === 'bp' ? `${Math.round(Math.abs(v))}bp` : `${abs(v)}pp`)

  let direction = null
  const prev = lookback(pts)
  if (prev) {
    const delta = toChange(latest.value) - toChange(prev.value)
    direction = Math.abs(delta) < n.changeThreshold ? 'steady' : delta > 0 ? 'rising' : 'falling'
    const words = n.words ?? { rising: 'Up', falling: 'Down' }
    bullets.push({
      label: 'Direction',
      text:
        direction === 'steady'
          ? `Little changed from ${fmt(prev.value)} three months earlier.`
          : `${words[direction]} ${fmtChange(delta)} from ${fmt(prev.value)} three months earlier.`,
    })
  }

  if (pts.length >= MIN_HISTORY) {
    bullets.push({ label: 'Versus history', text: historyText(history(pts), fmt, n.extremes) })
  }

  const parts = []
  if (n.bands) {
    const v = latest.value * scale
    const band = n.bands.find((b) => b.max === undefined || v < b.max)
    if (band) parts.push(band.text)
  }
  if (direction && n.messages?.[direction]) parts.push(n.messages[direction])
  if (n.riseFromLow) {
    const { months, threshold, text } = n.riseFromLow
    const { y, m, d } = parseDate(latest.date)
    const start = new Date(Date.UTC(y, m - 1 - months, d)).toISOString().slice(0, 10)
    const recent = pts.filter((p) => p.date.slice(0, 10) >= start).map((p) => p.value * scale)
    const rise = latest.value * scale - Math.min(...recent)
    if (rise >= threshold) parts.push(text.replace('{rise}', rise.toFixed(1)))
  }
  if (parts.length) bullets.push({ label: 'What it can signal', text: parts.join(' ') })
  return bullets
}

// ── curve ───────────────────────────────────────────────────────────────────

const describeCurve = (n, pts) => {
  const bp = (v) => `${signed(v, 0)}bp`
  const latest = pts[pts.length - 1]
  const x = latest.value
  const daily = isDaily(pts.map((p) => p.date))
  const bullets = [
    {
      label: 'What it shows',
      text: `The ${n.long} Treasury yield minus the ${n.short} yield, in basis points. Above zero is the normal upward slope; below zero, the curve is inverted.`,
    },
  ]
  const shape = x >= CURVE_FLAT_BP ? 'positive' : x <= -CURVE_FLAT_BP ? 'inverted' : 'flat'
  bullets.push({
    label: `Latest (${formatDate(latest.date, daily)})`,
    text:
      shape === 'positive'
        ? `The ${n.long} yields ${Math.round(x)}bp more than the ${n.short}: a positive slope.`
        : shape === 'inverted'
          ? `Inverted: the ${n.short} yields ${Math.round(-x)}bp more than the ${n.long}.`
          : `Roughly flat (${bp(x)}).`,
  })

  const prev = lookback(pts)
  if (prev) {
    const delta = x - prev.value
    let text
    if (Math.abs(delta) < CURVE_CHANGE_BP) {
      text = `Little changed from ${bp(prev.value)} three months earlier.`
    } else {
      text = `${delta > 0 ? 'Steepened' : 'Flattened'} by ${Math.round(Math.abs(delta))}bp from ${bp(prev.value)} three months earlier`
      if (prev.value < 0 && x >= 0) text += ', moving out of inversion'
      if (prev.value >= 0 && x < 0) text += ', moving into inversion'
      text += '.'
    }
    bullets.push({ label: 'Direction', text })
  }

  if (pts.length >= MIN_HISTORY) {
    bullets.push({
      label: 'Versus history',
      text: historyText(history(pts), bp, {
        high: 'an unusually steep curve',
        low: 'an unusually flat or inverted curve',
      }),
    })
  }
  bullets.push({ label: 'What it can signal', text: n.messages[shape] })
  return bullets
}

const capitalise = (s) => s.charAt(0).toUpperCase() + s.slice(1)

const DESCRIBERS = { relative: describeRelative, level: describeLevel, curve: describeCurve }

/**
 * Bullets for one chart. `frequency` is the equity dropdown value
 * ("Quarterly", "Yearly", "Three Year"); other kinds ignore it. An unknown kind
 * or an empty series gives no bullets.
 */
export const describeSeries = (narrative, series, frequency) => {
  const describe = DESCRIBERS[narrative?.kind]
  const pts = points(series)
  if (!describe || !pts.length) return []
  return describe(narrative, pts, frequency)
}
