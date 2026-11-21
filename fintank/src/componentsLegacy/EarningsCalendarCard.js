import React, { useState } from 'react'
import Link from 'next/link'
import { Card, Nav, Table, Button } from 'react-bootstrap'
import { useEarningsCalendar } from '@hooks/useEarningsCalendar'
import { EMPTY, addDays, fmtEps, mondayOf, weekDays } from '@utils/earningsFormat.mjs'

const REGIONS = [
  ['ca', 'Canada'],
  ['us', 'US'],
]

const dayLabel = (iso) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-CA', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' })

const EarningsCalendarCard = () => {
  const [week, setWeek] = useState(() => mondayOf(new Date()))
  const [region, setRegion] = useState('ca')
  const [day, setDay] = useState(null) // null = the week's first day
  const { data, error, isLoading } = useEarningsCalendar(week)

  // Provider or API failure hides the card.
  if (error) return null

  const days = weekDays(week)
  const activeDay = day && days.includes(day) ? day : days[0]
  const rows = (data?.rows || []).filter((r) => r.region === region && r.date === activeDay)

  const shift = (delta) => {
    setWeek(addDays(week, delta * 7))
    setDay(null)
  }

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body className="p-4">
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
          <h4 className="mb-0">Earnings calendar</h4>
          <div className="d-flex align-items-center gap-2">
            <Button size="sm" variant="outline-primary" aria-label="Previous week" onClick={() => shift(-1)}>
              ←
            </Button>
            <span className="text-sm text-nowrap">Week of {week}</span>
            <Button size="sm" variant="outline-primary" aria-label="Next week" onClick={() => shift(1)}>
              →
            </Button>
          </div>
        </div>

        <Nav variant="pills" className="mb-2">
          {REGIONS.map(([key, label]) => (
            <Nav.Item key={key}>
              <Nav.Link as="button" type="button" active={region === key} onClick={() => setRegion(key)}>
                {label}
              </Nav.Link>
            </Nav.Item>
          ))}
        </Nav>
        <Nav variant="tabs" className="mb-3">
          {days.map((d) => (
            <Nav.Item key={d}>
              <Nav.Link as="button" type="button" active={activeDay === d} onClick={() => setDay(d)}>
                {dayLabel(d)}
              </Nav.Link>
            </Nav.Item>
          ))}
        </Nav>

        {isLoading ? (
          <p className="text-muted mb-0">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="text-muted mb-0">No covered companies report this day.</p>
        ) : (
          <div className="table-responsive">
            <Table hover size="sm" className="align-middle mb-0">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Name</th>
                  <th>Date</th>
                  <th className="text-end">EPS est.</th>
                  <th className="text-end">EPS actual</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.symbol}>
                    <td>
                      <Link href={`/stock-data/${encodeURIComponent(r.symbol)}`}>{r.symbol}</Link>
                    </td>
                    <td>{r.name || EMPTY}</td>
                    <td className="text-nowrap">{r.date}</td>
                    <td className="text-end">{fmtEps(r.eps_estimate)}</td>
                    <td className="text-end">{fmtEps(r.eps_actual)}</td>
                    <td className="text-end text-nowrap">
                      {r.note_quarter && (
                        <Link href={`/stock-data/${encodeURIComponent(r.symbol)}?note=${encodeURIComponent(r.note_quarter)}`}>
                          Read note →
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        )}
      </Card.Body>
    </Card>
  )
}

export default EarningsCalendarCard
