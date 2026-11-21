// Run: node --test src/utils/earningsFormat.test.mjs
import { describe, it } from 'node:test'
import assert from 'node:assert/strict'

import {
  quarterLabel,
  parseNoteParam,
  leanBadge,
  weekDays,
  PANEL_DISCLAIMER,
  MODAL_DISCLAIMER,
  NOTE_SECTIONS,
  visibleSections,
  noteLinkLabel,
  isoDay,
  defaultDay,
} from './earningsFormat.mjs'

describe('quarterLabel', () => {
  it('formats a quarter key', () => {
    assert.equal(quarterLabel('2026-Q3'), 'Fiscal Q3 2026')
  })
})

describe('parseNoteParam', () => {
  it('accepts a valid quarter key', () => {
    assert.equal(parseNoteParam('2026-Q3'), '2026-Q3')
  })
  it('rejects anything else', () => {
    for (const bad of ['2026-Q5', 'Q3', '../x', undefined, ['2026-Q3'], '2026-Q3\n']) {
      assert.equal(parseNoteParam(bad), null)
    }
  })
})

describe('leanBadge', () => {
  it('maps the three leans', () => {
    assert.deepEqual(leanBadge('bullish'), { text: 'Bullish', variant: 'success' })
    assert.deepEqual(leanBadge('neutral'), { text: 'Neutral', variant: 'secondary' })
    assert.deepEqual(leanBadge('bearish'), { text: 'Bearish', variant: 'danger' })
  })
  it('falls back to neutral', () => {
    assert.equal(leanBadge('buy').text, 'Neutral')
  })
})

describe('weekDays', () => {
  it('lists Monday to Friday', () => {
    assert.deepEqual(weekDays('2026-11-16'), ['2026-11-16', '2026-11-17', '2026-11-18', '2026-11-19', '2026-11-20'])
  })
  it('crosses a month boundary', () => {
    assert.deepEqual(weekDays('2026-11-30'), ['2026-11-30', '2026-12-01', '2026-12-02', '2026-12-03', '2026-12-04'])
  })
})

describe('disclaimers', () => {
  it('are verbatim', () => {
    assert.equal(PANEL_DISCLAIMER, 'AI-written summary of the earnings call. One opinion, not investment advice.')
    assert.equal(
      MODAL_DISCLAIMER,
      "This note was written by AI (Claude) from the company's earnings call transcript. It is one opinion, not investment advice, and may contain errors. Check figures against the company's filings before making any decision.",
    )
  })
})

describe('NOTE_SECTIONS', () => {
  it('lists the sections in order', () => {
    const keys = NOTE_SECTIONS.map(([k]) => k)
    assert.deepEqual(keys, [
      'results_vs_consensus', 'guidance', 'management_tone', 'qa_themes', 'what_changed',
      'risks', 'bull_case', 'bear_case', 'watch_next',
    ])
  })
})

describe('visibleSections', () => {
  it('skips what_changed when null', () => {
    const keys = visibleSections({ what_changed: null }).map(([k]) => k)
    assert.ok(!keys.includes('what_changed'))
    assert.equal(keys.length, 8)
  })
})

describe('noteLinkLabel', () => {
  it('names the quarter', () => {
    assert.equal(noteLinkLabel('2026-Q2'), 'Read Q2 note')
    assert.equal(noteLinkLabel('2025-Q4'), 'Read Q4 note')
  })
  it('falls back without a quarter key', () => {
    assert.equal(noteLinkLabel(null), 'Read note')
    assert.equal(noteLinkLabel('2026-Q7'), 'Read note')
  })
})

describe('defaultDay', () => {
  const days = weekDays('2026-11-16')
  it('opens today when it is in the displayed week', () => {
    assert.equal(defaultDay(days, '2026-11-19'), '2026-11-19')
  })
  it('opens the Monday for another week or a weekend', () => {
    assert.equal(defaultDay(days, '2026-11-26'), '2026-11-16')
    assert.equal(defaultDay(days, '2026-11-21'), '2026-11-16')
  })
  it('reads today in UTC, like mondayOf', () => {
    assert.equal(isoDay(new Date(Date.UTC(2026, 10, 19, 23, 30))), '2026-11-19')
  })
})
