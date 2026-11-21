import React from 'react'
import { Badge, Form, Modal } from 'react-bootstrap'
import { useEarningsNote } from '@hooks/useEarningsNotes'
import { leanBadge, quarterLabel, visibleSections, MODAL_DISCLAIMER } from '@utils/earningsFormat.mjs'

// `quarters` is the index (newest first); `quarter` is the one being shown.
const EarningsNoteModal = ({ symbol, quarters, quarter, onSelect, onHide }) => {
  const { data: note, error, isLoading } = useEarningsNote(symbol, quarter)
  const badge = note ? leanBadge(note.lean) : null

  return (
    <Modal show onHide={onHide} size="lg" scrollable>
      <Modal.Header closeButton>
        <Modal.Title>{symbol} earnings note</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <p className="text-muted text-sm">{MODAL_DISCLAIMER}</p>

        <Form.Select
          size="sm"
          className="mb-3 w-auto"
          aria-label="Quarter"
          value={quarter}
          onChange={(e) => onSelect(e.target.value)}
        >
          {quarters.map((q) => (
            <option key={q.quarter} value={q.quarter}>
              {quarterLabel(q.quarter)}
            </option>
          ))}
        </Form.Select>

        {isLoading && <p className="text-muted">Loading note…</p>}
        {error && <p className="text-muted">This note is unavailable right now.</p>}

        {note && (
          <>
            <h5 className="mb-2">
              {note.headline} <Badge bg={badge.variant}>{badge.text}</Badge>
            </h5>
            <p className="text-muted text-sm">
              {quarterLabel(quarter)} · reported {note.report_date}
            </p>
            {visibleSections(note.sections).map(([key, heading]) => (
              <div key={key} className="mb-3">
                <h6>{heading}</h6>
                <p className="mb-0" style={{ whiteSpace: 'pre-line' }}>
                  {note.sections[key]}
                </p>
              </div>
            ))}
          </>
        )}
      </Modal.Body>
    </Modal>
  )
}

export default EarningsNoteModal
