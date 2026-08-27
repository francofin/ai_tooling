import React, { useState } from 'react'
import { Button, Form } from 'react-bootstrap'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faCircleInfo, faPlus, faXmark } from '@fortawesome/free-solid-svg-icons'
import IndicatorInfoModal from './IndicatorInfoModal'
import { indicatorMeta, makeInstance, validateInstance } from '@utils/technicalSpec'

/**
 * One indicator's controls: every active instance of it, plus an add button.
 *
 * Inputs are generated from `params`, so nothing here is hand-wired per
 * indicator. That is what retires the old page's TEMA bug, where the second
 * period box called setTemaPeriodOne and silently overwrote the first.
 *
 * Validation is inline: the old page raised a `swal` modal per failure, which
 * across five panels would stack up to five popups from one bad period.
 *
 * All mutations go through the functional-update form of `onChange` (i.e.
 * `onChange((prev) => ...)`) rather than closing over the `instances` prop.
 * `makeInstanceId` never collides against an accurate `existing` list, but
 * two `add()` calls firing before a React state commit would both read the
 * same stale `instances` prop and mint the same id. Deriving the next list
 * from the setter's own previous state (which this component doesn't own --
 * it only ever forwards `onChange` from an ancestor's `useState`) closes that
 * window instead of merely narrowing it.
 */
const IndicatorControl = ({ name, instances, onChange }) => {
  const [showInfo, setShowInfo] = useState(false)
  const entry = indicatorMeta[name]
  const mine = instances.filter((instance) => instance.name === name)

  const add = () => onChange((prev) => [...prev, makeInstance(name, prev)])

  const remove = (id) => onChange((prev) => prev.filter((instance) => instance.id !== id))

  const setParam = (id, key, raw) => {
    const value = raw === '' ? '' : Number(raw)
    onChange((prev) =>
      prev.map((instance) =>
        instance.id === id ? { ...instance, params: { ...instance.params, [key]: value } } : instance,
      ),
    )
  }

  return (
    <div className="indicator-control border-bottom py-3">
      <div className="d-flex align-items-center justify-content-between">
        <span className="fw-semibold small">{entry.label}</span>
        <div className="d-flex gap-1">
          <Button
            variant="link"
            size="sm"
            className="p-0"
            aria-label={`About ${entry.label}`}
            onClick={() => setShowInfo(true)}
          >
            <FontAwesomeIcon icon={faCircleInfo} />
          </Button>
          <Button variant="link" size="sm" className="p-0" aria-label={`Add ${entry.label}`} onClick={add}>
            <FontAwesomeIcon icon={faPlus} />
          </Button>
        </div>
      </div>

      {mine.map((instance) => {
        const errors = validateInstance(instance) ?? {}
        return (
          <div key={instance.id} className="d-flex align-items-start gap-2 mt-2">
            {entry.params.length === 0 && <span className="text-muted small flex-grow-1">Active</span>}
            {entry.params.map((param) => (
              <Form.Group key={param.key} className="flex-grow-1">
                <Form.Label className="small text-muted mb-0" htmlFor={`${instance.id}-${param.key}`}>
                  {param.label}
                </Form.Label>
                <Form.Control
                  id={`${instance.id}-${param.key}`}
                  type="number"
                  size="sm"
                  min={param.min}
                  max={param.max}
                  value={instance.params[param.key]}
                  isInvalid={Boolean(errors[param.key])}
                  onChange={(event) => setParam(instance.id, param.key, event.target.value)}
                />
                <Form.Control.Feedback type="invalid">{errors[param.key]}</Form.Control.Feedback>
              </Form.Group>
            ))}
            <Button
              variant="link"
              size="sm"
              className="p-0 mt-4"
              aria-label={`Remove ${entry.label} ${instance.id}`}
              onClick={() => remove(instance.id)}
            >
              <FontAwesomeIcon icon={faXmark} />
            </Button>
          </div>
        )
      })}

      <IndicatorInfoModal name={name} show={showInfo} onHide={() => setShowInfo(false)} />
    </div>
  )
}

export default IndicatorControl
