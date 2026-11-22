// Run: node --test src/utils/analystViewFormat.test.mjs
import { describe, it } from 'node:test'
import assert from 'node:assert/strict'

import { fmtRange, sourceLabel, targetLabel, upsidePct } from './analystViewFormat.mjs'

const source = { symbol: 'SHOP', exchange: 'NYSE' }

describe('targetLabel', () => {
  it('shows USD, the CAD conversion and the source listing', () => {
    assert.equal(
      targetLabel({ consensus: 178.25, cad: { consensus: 255.25 } }, source),
      "Target $178 USD (≈ $255 CAD) · from SHOP's NYSE listing",
    )
  })
  it('drops the CAD part when there is no conversion', () => {
    assert.equal(targetLabel({ consensus: 178.25, cad: null }, source), "Target $178 USD · from SHOP's NYSE listing")
  })
  it('is null without a source', () => {
    assert.equal(targetLabel({ consensus: 178.25 }, null), null)
  })
})

describe('sourceLabel', () => {
  it('names the US listing the ratings come from', () => {
    assert.equal(sourceLabel({ symbol: 'RY', exchange: 'NYSE' }), "from RY's NYSE listing")
  })
  it('is null without a source', () => {
    assert.equal(sourceLabel(null), null)
    assert.equal(sourceLabel(undefined), null)
  })
})

describe('upsidePct', () => {
  it('computes percent upside', () => {
    assert.equal(upsidePct(225, 150), 50)
  })
  it('is null for missing or non-positive inputs', () => {
    assert.equal(upsidePct(225, 0), null)
    assert.equal(upsidePct(null, 150), null)
    assert.equal(upsidePct(225, null), null)
  })
})

describe('fmtRange', () => {
  it('uses an em dash for null parts, never NaN', () => {
    const out = fmtRange({ low: null, avg: 2, high: 3 }, String)
    assert.ok(out.includes('—'))
    assert.ok(!out.includes('NaN'))
  })
})
