// Run: node --test src/utils/capitalMarkets/spreadNarrative.test.mjs
import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import { describeSeries } from './spreadNarrative.mjs'

/** Monthly month-end series ending Oct 2026, oldest first. */
const monthly = (values, end = [2026, 10]) => {
  const [ey, em] = end
  const dates = values.map((_, i) => {
    const back = values.length - 1 - i
    const d = new Date(Date.UTC(ey, em - back, 0))
    return d.toISOString().slice(0, 10)
  })
  return { dates, value: values }
}

const text = (bullets, label) => bullets.find((b) => b.label.startsWith(label))?.text

const R2000 = {
  kind: 'relative',
  comp: 'Russell 2000',
  base: 'Russell 1000',
  compShort: 'small caps',
  baseShort: 'large caps',
  compAhead: 'Small caps leading.',
  baseAhead: 'Large caps leading.',
}

// 30 readings spread between -5% and +5%, then a chosen tail.
const history = Array.from({ length: 30 }, (_, i) => -0.05 + (i % 11) * 0.01)

describe('relative (equity spreads)', () => {
  it('names the leader and the size of the lead, in pp', () => {
    const b = describeSeries(R2000, monthly([...history, 0.008, 0.0, 0.0, -0.093]), 'Quarterly')
    assert.equal(text(b, 'Latest (Oct 2026)'), 'Large caps ahead by 9.3pp.')
    assert.match(text(b, 'What it shows'), /over a rolling 3 months\. Above zero, small caps ahead/)
  })

  it('calls a gap under 1pp roughly level and uses the neutral signal', () => {
    const b = describeSeries(R2000, monthly([...history, 0.004]), 'Yearly')
    assert.equal(text(b, 'Latest'), 'Roughly level (+0.4pp).')
    assert.match(text(b, 'What it shows'), /rolling 12 months/)
    assert.equal(text(b, 'What it can signal'), 'Neither side has a meaningful edge over this window.')
  })

  it('describes a three-month swing toward the side that gained', () => {
    const b = describeSeries(R2000, monthly([...history, 0.008, 0.0, 0.0, -0.093]), 'Quarterly')
    assert.equal(text(b, 'Direction'), 'Swung 10.1pp toward large caps from +0.8pp three months earlier.')
    const big = describeSeries(R2000, monthly([...history, 0.099, 0.0, 0.0, -0.081]), 'Quarterly')
    assert.equal(text(big, 'Direction'), 'Swung 18.0pp toward large caps from +9.9pp three months earlier.')
  })

  it('calls a move under 1pp little changed', () => {
    const b = describeSeries(R2000, monthly([...history, 0.02, 0.0, 0.0, 0.025]), 'Quarterly')
    assert.equal(text(b, 'Direction'), 'Little changed from +2.0pp three months earlier.')
  })

  it('flags a bottom-decile reading and strengthens the signal for the leader', () => {
    const b = describeSeries(R2000, monthly([...history, -0.2]), 'Quarterly')
    assert.match(
      text(b, 'Versus history'),
      /^Lower than 97% of readings since \d{4}: unusually far in favor of large caps\.$/,
    )
    assert.equal(
      text(b, 'What it can signal'),
      'Large caps leading. At this extreme, the preference is unusually strong.',
    )
  })

  it('gives the usual range when the reading is not extreme', () => {
    const b = describeSeries(R2000, monthly([...history, 0.015]), 'Quarterly')
    assert.match(
      text(b, 'Versus history'),
      /^Within its usual range since \d{4}: the middle 80% of readings runs from −\d\.\dpp to \+\d\.\dpp\.$/,
    )
    assert.equal(text(b, 'What it can signal'), 'Small caps leading.')
  })

  it("does not call a top-decile reading 'stretched' when the other side leads", () => {
    // Every reading far below zero; the latest is the least negative: top decile, base still ahead.
    const b = describeSeries(R2000, monthly([...Array(30).fill(-0.2), -0.05]), 'Quarterly')
    assert.match(text(b, 'Versus history'), /unusually far in favor of small caps/)
    assert.equal(text(b, 'What it can signal'), 'Large caps leading.')
  })

  it('never prints a negative zero', () => {
    const b = describeSeries(R2000, monthly([...history, -0.0002]), 'Quarterly')
    assert.equal(text(b, 'Latest'), 'Roughly level (0.0pp).')
  })

  it('returns nothing for an empty or missing series and skips nulls', () => {
    assert.deepEqual(describeSeries(R2000, { dates: [], value: [] }, 'Quarterly'), [])
    assert.deepEqual(describeSeries(R2000, null, 'Quarterly'), [])
    const b = describeSeries(R2000, monthly([0.02, null, 0.03]), 'Quarterly')
    assert.equal(text(b, 'Latest'), 'Small caps ahead by 3.0pp.')
    assert.equal(text(b, 'Versus history'), undefined, 'too short for a history bullet')
  })
})

const TEN = {
  kind: 'level',
  about: 'The 10-year yield.',
  unit: '%',
  changeUnit: 'bp',
  changeThreshold: 10,
  messages: { rising: 'Rising.', falling: 'Falling.', steady: 'Steady.' },
}

/** Daily series of business-ish days ending 2026-10-15. */
const daily = (values) => {
  const end = Date.UTC(2026, 9, 15)
  return {
    dates: values.map((_, i) => new Date(end - (values.length - 1 - i) * 86400000).toISOString().slice(0, 10)),
    value: values,
  }
}

describe('level (yields, rates, growth)', () => {
  it('dates a daily series to the day and reports the change in bp', () => {
    const values = [...Array(120).fill(4.8), 5.1]
    const b = describeSeries(TEN, daily(values))
    assert.equal(text(b, 'Latest (Oct 15, 2026)'), '5.10%.')
    assert.equal(text(b, 'Direction'), 'Up 30bp from 4.80% three months earlier.')
    assert.equal(text(b, 'What it can signal'), 'Rising.')
  })

  it('calls a move under the threshold little changed', () => {
    const b = describeSeries(TEN, daily([...Array(120).fill(5.05), 5.1]))
    assert.equal(text(b, 'Direction'), 'Little changed from 5.05% three months earlier.')
    assert.equal(text(b, 'What it can signal'), 'Steady.')
  })

  it('picks the value band and adds the direction message', () => {
    const CPI = {
      kind: 'level',
      about: 'CPI.',
      scale: 100,
      decimals: 1,
      changeThreshold: 0.2,
      valueSuffix: 'year over year',
      bands: [{ max: 1.5, text: 'Below.' }, { max: 2.5, text: 'Near.' }, { text: 'Above.' }],
      messages: { rising: 'And rising.', falling: 'And easing.' },
    }
    const b = describeSeries(CPI, monthly([...Array(20).fill(0.03), 0.0373, 0.0354, 0.0371, 0.0402]))
    assert.equal(text(b, 'Latest (Oct 2026)'), '4.0% year over year.')
    assert.equal(text(b, 'Direction'), 'Up 0.3pp from 3.7% three months earlier.')
    assert.equal(text(b, 'What it can signal'), 'Above. And rising.')
    const near = describeSeries(CPI, monthly([...Array(20).fill(0.02), 0.021]))
    assert.equal(text(near, 'What it can signal'), 'Near.')
  })

  it('adds the rise-from-low warning only past the threshold', () => {
    const UNEMP = {
      kind: 'level',
      about: 'Unemployment.',
      decimals: 1,
      changeThreshold: 0.2,
      messages: { rising: 'Rising.', falling: 'Falling.', steady: 'Steady.' },
      riseFromLow: { months: 12, threshold: 0.5, text: 'Up {rise}pp from its 12-month low.' },
    }
    const up = describeSeries(UNEMP, monthly([...Array(12).fill(4.0), 3.9, 4.0, 4.1, 4.2, 4.5]))
    assert.equal(text(up, 'What it can signal'), 'Rising. Up 0.6pp from its 12-month low.')
    const flat = describeSeries(UNEMP, monthly([...Array(16).fill(4.1), 4.2]))
    assert.equal(text(flat, 'What it can signal'), 'Steady.')
  })
})

const CURVE = {
  kind: 'curve',
  long: '10-year',
  short: '2-year',
  messages: { positive: 'Normal.', flat: 'Flat.', inverted: 'Inverted.' },
}

describe('curve (yield spreads)', () => {
  it('describes a positive slope and a steepening', () => {
    const b = describeSeries(CURVE, daily([...Array(100).fill(10), 33]))
    assert.equal(text(b, 'Latest'), 'The 10-year yields 33bp more than the 2-year: a positive slope.')
    assert.equal(text(b, 'Direction'), 'Steepened by 23bp from +10bp three months earlier.')
    assert.equal(text(b, 'What it can signal'), 'Normal.')
  })

  it('describes an inversion and a move into it', () => {
    const b = describeSeries(CURVE, daily([...Array(100).fill(20), -40]))
    assert.equal(text(b, 'Latest'), 'Inverted: the 2-year yields 40bp more than the 10-year.')
    assert.equal(text(b, 'Direction'), 'Flattened by 60bp from +20bp three months earlier, moving into inversion.')
    assert.equal(text(b, 'What it can signal'), 'Inverted.')
  })

  it('calls within 10bp flat and notes leaving an inversion', () => {
    const b = describeSeries(CURVE, daily([...Array(100).fill(-30), 5]))
    assert.equal(text(b, 'Latest'), 'Roughly flat (+5bp).')
    assert.match(text(b, 'Direction'), /moving out of inversion\.$/)
    assert.equal(text(b, 'What it can signal'), 'Flat.')
  })
})

describe("the page's definitions", () => {
  const load = (name) => JSON.parse(readFileSync(new URL(`../../data/capitalMarkets/${name}`, import.meta.url)))
  const kinds = {
    relative: ['comp', 'base', 'compShort', 'baseShort', 'compAhead', 'baseAhead'],
    level: ['about', 'changeThreshold'],
    curve: ['long', 'short', 'messages'],
  }

  for (const name of ['equitySeries.json', 'economicSeries.json']) {
    it(`${name}: every chart has a complete narrative and produces bullets`, () => {
      for (const def of load(name)) {
        const n = def.narrative
        assert.ok(n && kinds[n.kind], `${def.id} has a known narrative kind`)
        for (const field of kinds[n.kind]) assert.ok(n[field] !== undefined, `${def.id} narrative.${field}`)
        const values =
          n.kind === 'relative'
            ? history
            : n.kind === 'curve'
              ? [...Array(30).fill(50), -20]
              : [...Array(30).fill(n.scale ? 0.02 : 4), n.scale ? 0.03 : 5]
        const bullets = describeSeries(n, monthly(values), 'Quarterly')
        assert.ok(bullets.length >= 4, `${def.id} gives at least 4 bullets`)
        for (const b of bullets) assert.ok(b.text && !b.text.includes('undefined'), `${def.id}: ${b.label}`)
      }
    })
  }
})
