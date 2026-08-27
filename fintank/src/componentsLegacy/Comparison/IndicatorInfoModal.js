import React from 'react'
import { Button, Modal } from 'react-bootstrap'
import { indicatorMeta } from '@utils/technicalSpec'

/**
 * One generic modal in place of eleven hand-written ones. All prose lives in
 * indicatorMeta.json, migrated verbatim from the modals this replaces.
 */
const IndicatorInfoModal = ({ name, show, onHide }) => {
  const entry = indicatorMeta[name]
  if (!entry) return null

  return (
    <Modal show={show} onHide={onHide} scrollable>
      <Modal.Header closeButton>
        <Modal.Title className="text-uppercase" as="h6">
          {entry.label}
        </Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <p className="text-muted">{entry.description}</p>
        {entry.bullets?.length > 0 && (
          <ul className="text-muted fw-light mt-3">
            {entry.bullets.map((bullet, index) => (
              <li key={index}>{bullet}</li>
            ))}
          </ul>
        )}
      </Modal.Body>
      <Modal.Footer className="justify-content-end">
        <Button onClick={onHide}>Close</Button>
      </Modal.Footer>
    </Modal>
  )
}

export default IndicatorInfoModal
