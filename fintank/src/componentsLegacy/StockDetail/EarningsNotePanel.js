import React, { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import { Badge } from 'react-bootstrap'
import { useEarningsNotes } from '@hooks/useEarningsNotes'
import EarningsNoteModal from '@componentsLegacy/StockDetail/EarningsNoteModal'
import { leanBadge, parseNoteParam, quarterLabel, PANEL_DISCLAIMER } from '@utils/earningsFormat.mjs'

const EarningsNotePanel = ({ symbol }) => {
  const router = useRouter()
  const { data, error, isLoading } = useEarningsNotes(symbol)
  const [open, setOpen] = useState(null) // the quarter shown in the modal, or null

  const quarters = data?.quarters || []
  const wanted = parseNoteParam(router.query.note)

  // A valid ?note= that is in the index opens the modal on load; anything else is ignored.
  useEffect(() => {
    if (wanted && quarters.some((q) => q.quarter === wanted)) setOpen(wanted)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wanted, data])

  // ?note= follows the modal; shallow so the server-side props are not refetched.
  const setNote = (quarter) => {
    const query = { ...router.query }
    if (quarter) query.note = quarter
    else delete query.note
    router.replace({ pathname: router.pathname, query }, undefined, { shallow: true })
  }
  const show = (quarter) => {
    setOpen(quarter)
    setNote(quarter)
  }
  const hide = () => {
    setOpen(null)
    setNote(null)
  }

  // No note (404), provider failure and loading all hide the panel.
  if (isLoading || error || !data || !quarters.length || !data.latest) return null

  // Quarter, date and lean come from the index entry; the text from the full note.
  const entry = quarters[0]
  const badge = leanBadge(entry.lean)
  const { headline, key_points: points } = data.latest

  return (
    <div className="text-block">
      <h4 className="mb-3">Earnings note</h4>
      <div
        className="border rounded p-3"
        role="button"
        tabIndex={0}
        style={{ cursor: 'pointer' }}
        onClick={() => show(entry.quarter)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault() // Space would otherwise scroll the page
            show(entry.quarter)
          }
        }}
      >
        <div className="d-flex flex-wrap align-items-center gap-2 mb-2">
          <strong>{quarterLabel(entry.quarter)}</strong>
          <span className="text-muted text-sm">reported {entry.report_date}</span>
          <Badge bg={badge.variant}>{badge.text}</Badge>
        </div>
        <p className="fw-bold mb-2">{headline}</p>
        <ul className="mb-2">
          {points.map((p, i) => (
            <li key={i}>{p}</li>
          ))}
        </ul>
        <span className="text-primary text-sm">Read the full note →</span>
      </div>
      <p className="text-muted text-xs mt-2 mb-0">{PANEL_DISCLAIMER}</p>

      {open && (
        <EarningsNoteModal symbol={symbol} quarters={quarters} quarter={open} onSelect={show} onHide={hide} />
      )}
    </div>
  )
}

export default EarningsNotePanel
