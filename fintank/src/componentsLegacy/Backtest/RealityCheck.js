import React from 'react'
import { Alert, Card, Table } from 'react-bootstrap'

const VARIANTS = { critical: 'danger', warning: 'warning', info: 'secondary' }
const HEADINGS = {
  critical: 'Read this before you read the numbers',
  warning: 'What this simulation cannot tell you',
  info: 'Worth knowing',
}

/**
 * The diagnostics panel and the composition timeline.
 *
 * `severities` lets the page render critical findings above the results and the
 * rest below, from one component and one data source.
 */
const RealityCheck = ({ result, severities = ['critical', 'warning', 'info'], showTimeline = true }) => {
  const findings = (result?.diagnostics || []).filter((finding) => severities.includes(finding.severity))
  const events = result?.composition_events || []

  if (!findings.length && !showTimeline) return null

  const onlyCritical = severities.length === 1 && severities[0] === 'critical'

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <h5 className="mb-3">{onlyCritical ? HEADINGS.critical : 'Reality check'}</h5>

        {!onlyCritical && (
          <p className="text-muted fs-13px">
            A backtest is a story you can tell about the past, and a well-chosen story can be made to look like almost
            anything. These notes exist so the number above is not the only thing you take away.
          </p>
        )}

        {findings.map((finding) => (
          <Alert key={finding.code} variant={VARIANTS[finding.severity]} className="mb-2">
            <strong>{finding.title}</strong>
            <div className="fs-13px mt-1">{finding.detail}</div>
          </Alert>
        ))}

        {!findings.length && !onlyCritical && <p className="fs-13px mb-0">No specific warnings for this run.</p>}

        {showTimeline && events.length > 0 && (
          <>
            <h6 className="mt-4 mb-2">What changed, and when</h6>
            <Table size="sm" responsive className="align-middle">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Holding</th>
                  <th>Change</th>
                  <th>Why</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event, index) => (
                  <tr key={`${event.date}-${event.symbol}-${index}`}>
                    <td>{event.date}</td>
                    <td>
                      <strong>{event.symbol}</strong>
                    </td>
                    <td>{event.action === 'entered' ? 'Bought' : 'Sold'}</td>
                    <td className="fs-13px text-muted">{event.reason}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </>
        )}

        {result?.truncation_cause && showTimeline && (
          <p className="fs-13px text-muted mb-0">{result.truncation_cause}</p>
        )}
      </Card.Body>
    </Card>
  )
}

export default RealityCheck
