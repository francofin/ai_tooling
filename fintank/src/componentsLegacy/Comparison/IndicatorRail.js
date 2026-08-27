import React from 'react'
import { Alert } from 'react-bootstrap'
import IndicatorControl from './IndicatorControl'
import { indicatorMeta, MAX_INDICATORS } from '@utils/technicalSpec'

/**
 * Every indicator's controls, grouped overlay vs oscillator, driven entirely
 * by indicatorMeta.json. This is the ~1,000 lines of hand-written collapse
 * panels and ~450 lines of near-identical submit handlers that the old page
 * carried, collapsed into one map.
 *
 * Settings are shared across all panels -- RSI(14) means RSI(14) in every
 * column. Per-panel settings would make the columns non-comparable, which is
 * the whole point of the page.
 *
 * `onChange` (forwarded to `IndicatorControl`) is invoked with React's
 * functional-update form, not a plain array -- wire it directly to a
 * `useState` setter, never to a wrapper that assumes it always receives an
 * array, or the rail will silently stop updating.
 */
const IndicatorRail = ({ instances, onChange }) => {
  const names = Object.keys(indicatorMeta)
  const overlays = names.filter((name) => indicatorMeta[name].kind === 'overlay')
  const oscillators = names.filter((name) => indicatorMeta[name].kind === 'oscillator')
  const full = instances.length >= MAX_INDICATORS

  const section = (title, group) => (
    <>
      <h6 className="text-uppercase text-muted small mt-4 mb-2">{title}</h6>
      {group.map((name) => (
        <IndicatorControl key={name} name={name} instances={instances} onChange={onChange} />
      ))}
    </>
  )

  return (
    <div className="indicator-rail">
      {full && (
        <Alert variant="warning" className="py-2 small">
          {MAX_INDICATORS} indicators is the maximum. Remove one to add another.
        </Alert>
      )}
      {section('Overlays', overlays)}
      {section('Oscillators', oscillators)}
    </div>
  )
}

export default IndicatorRail
