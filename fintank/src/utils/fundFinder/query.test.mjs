// Run: node --test src/utils/fundFinder/query.test.mjs
import { describe, it } from 'node:test'
import assert from 'node:assert/strict'

import { parseQuery, toQuery, canSearch } from './query.mjs'

describe('parseQuery / toQuery', () => {
  it('round-trips a full query', () => {
    const q = { listed: 'ca', include: 'RY.TO,TD.TO', exclude: 'SHOP.TO' }
    const state = parseQuery(q)
    assert.deepEqual(state, { listed: 'ca', include: ['RY.TO', 'TD.TO'], exclude: ['SHOP.TO'] })
    assert.deepEqual(toQuery(state), q)
  })

  it('upper-cases and trims, and leaves listed null when absent', () => {
    const state = parseQuery({ include: ' ry.to ' })
    assert.equal(state.listed, null)
    assert.deepEqual(state.include, ['RY.TO'])
    assert.deepEqual(state.exclude, [])
  })

  it('accepts only ca, us or both for listed', () => {
    assert.equal(parseQuery({ listed: 'CA' }).listed, null)
    assert.equal(parseQuery({ listed: 'xx' }).listed, null)
    assert.equal(parseQuery({ listed: 'both' }).listed, 'both')
    assert.equal(parseQuery({ listed: 'us' }).listed, 'us')
  })

  it('removes duplicates and empty entries', () => {
    assert.deepEqual(parseQuery({ include: 'RY.TO,ry.to,,TD.TO,RY.TO' }).include, ['RY.TO', 'TD.TO'])
  })

  it('keeps at most 10 per list', () => {
    const many = Array.from({ length: 14 }, (_, i) => `S${i}`).join(',')
    const state = parseQuery({ include: many, exclude: many })
    assert.equal(state.include.length, 10)
    assert.equal(state.exclude.length, 10)
    assert.equal(state.include[9], 'S9')
  })

  it('takes the first value when a param is repeated', () => {
    assert.deepEqual(parseQuery({ include: ['RY.TO', 'TD.TO'] }).include, ['RY.TO'])
  })

  it('handles a missing query object', () => {
    assert.deepEqual(parseQuery(undefined), { listed: null, include: [], exclude: [] })
  })

  it('toQuery omits empty lists and never invents listed', () => {
    assert.deepEqual(toQuery({ listed: null, include: ['AAPL'], exclude: [] }), { include: 'AAPL' })
    assert.deepEqual(toQuery({ listed: null, include: [], exclude: [] }), {})
  })
})

describe('canSearch', () => {
  it('is false without listed', () => {
    assert.equal(canSearch({ listed: null, include: ['RY.TO'], exclude: [] }), false)
  })
  it('is false without an included stock', () => {
    assert.equal(canSearch({ listed: 'ca', include: [], exclude: ['SHOP.TO'] }), false)
  })
  it('is true with both', () => {
    assert.equal(canSearch({ listed: 'both', include: ['RY.TO'], exclude: [] }), true)
  })
})
