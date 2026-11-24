// Run: node --test src/utils/capitalMarkets/downsample.test.mjs
import { describe, it } from 'node:test'
import assert from 'node:assert/strict'

import { weeklyForDisplay, DISPLAY_POINT_LIMIT } from './downsample.mjs'

/** Business-day series from `start`, `n` points, values 0..n-1. */
const daily = (start, n) => {
  const dates = []
  const d = new Date(`${start}T00:00:00Z`)
  while (dates.length < n) {
    const day = d.getUTCDay()
    if (day !== 0 && day !== 6) dates.push(d.toISOString().slice(0, 10))
    d.setUTCDate(d.getUTCDate() + 1)
  }
  return { dates, value: dates.map((_, i) => i) }
}

describe('weeklyForDisplay', () => {
  it('returns short series unchanged (same object)', () => {
    const s = daily('2023-08-01', 826)
    assert.equal(weeklyForDisplay(s), s)
  })

  it('returns null and empty input unchanged', () => {
    assert.equal(weeklyForDisplay(null), null)
    const empty = { dates: [], value: [] }
    assert.equal(weeklyForDisplay(empty), empty)
  })

  it('keeps the last trading day of each week (Friday close)', () => {
    // 2026-01-05 is a Monday; 3 full weeks.
    const s = daily('2026-01-05', 15)
    const out = weeklyForDisplay(s, 5)
    assert.deepEqual(out.dates, ['2026-01-05', '2026-01-09', '2026-01-16', '2026-01-23'])
    assert.deepEqual(out.value, [0, 4, 9, 14])
  })

  it('keeps the first and last points so the line spans the full range', () => {
    // Starts on a Wednesday, ends on a Tuesday mid-week.
    const s = daily('2026-01-07', 10)
    const out = weeklyForDisplay(s, 5)
    assert.equal(out.dates[0], s.dates[0])
    assert.equal(out.dates.at(-1), s.dates.at(-1))
    assert.equal(out.value.at(-1), s.value.at(-1))
  })

  it('thins a 60-year daily series to about one point a week', () => {
    const s = daily('1962-01-02', 16206)
    const out = weeklyForDisplay(s)
    assert.ok(s.dates.length > DISPLAY_POINT_LIMIT)
    assert.ok(out.dates.length > 3200 && out.dates.length < 3300, `${out.dates.length}`)
    assert.equal(out.dates.length, out.value.length)
    // Every kept value is the exact daily value on that date (no averaging).
    out.dates.forEach((date, i) => {
      assert.equal(out.value[i], s.value[s.dates.indexOf(date)])
    })
  })

  it('does not change the input series', () => {
    const s = daily('1962-01-02', 3000)
    const before = JSON.stringify(s)
    weeklyForDisplay(s)
    assert.equal(JSON.stringify(s), before)
  })
})
