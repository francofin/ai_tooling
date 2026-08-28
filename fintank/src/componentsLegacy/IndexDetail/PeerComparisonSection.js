import React, { useMemo, useState } from "react"
import { Container, Row, Col, Nav } from "react-bootstrap"
import { Line } from "react-chartjs-2"

import OptionSelect from "./OptionSelect"
import SectionUnavailable from "./SectionUnavailable"
import { useIndexComparison } from "@hooks/useIndexComparison"
import {
  METRICS,
  DEFAULT_METRIC_ID,
  getMetric,
  availableFrequencies,
  isPercentMetric,
} from "@utils/indexDetail/metrics"
import { buildLineChart, buildPairChart, hasValues } from "@utils/indexDetail/chartBuilders"
import { indexLineOptions, percentLineOptions } from "@utils/indexDetail/chartOptions"

/**
 * This index against a peer, across every comparison metric.
 *
 * Replaces five near-identical page sections (~600 lines, 20 state variables,
 * 10 handler functions) and the five backend pack endpoints behind them. The
 * peer is chosen once for all metrics; the metric is a tab; the frequency comes
 * from that metric's own list. One fetch per peer covers every tab, because the
 * backend returns all metric families in a single payload.
 */
const PeerComparisonSection = ({ slug, peers, baseTitle }) => {
  const [peerKey, setPeerKey] = useState(peers?.[0]?.key ?? null)
  const [metricId, setMetricId] = useState(DEFAULT_METRIC_ID)
  const [frequencies, setFrequencies] = useState({})

  const { comparison, error, isLoading } = useIndexComparison(slug, peerKey)

  const metric = getMetric(metricId)
  const options = useMemo(
    () => availableFrequencies(metric, comparison?.metrics),
    [metric, comparison]
  )
  // Frequency is remembered per metric, so switching tabs and back does not
  // reset the choice. Falls back to the first option the payload actually has.
  const frequency = frequencies[metric.id] ?? options[0]?.value

  const chart = useMemo(() => {
    const family = comparison?.metrics?.[metric.family]
    const series = frequency ? family?.[frequency] : null
    if (!series) return null

    const peerLabel = comparison?.peer?.title ?? "Comparison"
    const frequencyLabel =
      metric.frequencies.find((option) => option.value === frequency)?.label ?? ""

    if (metric.shape === "pair") {
      if (!hasValues(series.base) && !hasValues(series.peer)) return null
      return buildPairChart({
        dates: comparison.dates,
        base: series.base,
        peer: series.peer,
        baseLabel: `${baseTitle} ${frequencyLabel}`,
        peerLabel: `${peerLabel} ${frequencyLabel}`,
      })
    }

    if (!hasValues(series)) return null
    return buildLineChart({
      dates: comparison.dates,
      values: series,
      label: `${baseTitle} vs ${peerLabel} — ${frequencyLabel} ${metric.label}`,
    })
  }, [comparison, metric, frequency, baseTitle])

  if (!peers?.length) return null

  return (
    <section className="py-4">
      <Container>
        <Row className="pt-3">
          <Col lg="12">
            <div className="text-block">
              <h6 className="mb-3">Peer Comparison</h6>
              <p className="text-muted fw-light">{metric.blurb}</p>
            </div>

            <div className="text-center mb-3">
              <OptionSelect
                id={`peer-${slug}`}
                label="Comparison Index"
                options={peers.map((peer) => ({ value: peer.key, label: peer.label }))}
                value={peerKey}
                onChange={setPeerKey}
              />
              {options.length > 0 && (
                <OptionSelect
                  id={`frequency-${slug}-${metric.id}`}
                  label="Frequency"
                  options={options}
                  value={frequency}
                  onChange={(value) =>
                    setFrequencies((current) => ({ ...current, [metric.id]: value }))
                  }
                />
              )}
            </div>

            <Nav
              variant="tabs"
              className="mb-3"
              activeKey={metric.id}
              onSelect={(key) => key && setMetricId(key)}
            >
              {METRICS.map((entry) => (
                <Nav.Item key={entry.id}>
                  <Nav.Link eventKey={entry.id}>{entry.label}</Nav.Link>
                </Nav.Item>
              ))}
            </Nav>

            {error && (
              <SectionUnavailable message="This comparison could not be loaded. Try another index." />
            )}
            {!error && isLoading && (
              <p className="text-muted fw-light">Loading comparison…</p>
            )}
            {!error && !isLoading && !chart && (
              <SectionUnavailable
                message={`No ${metric.label.toLowerCase()} data overlaps these two indexes.`}
              />
            )}
            {chart && (
              <Line
                options={isPercentMetric(metric) ? percentLineOptions : indexLineOptions}
                data={chart}
                height={100}
                width={200}
              />
            )}
          </Col>
        </Row>
      </Container>
    </section>
  )
}

export default PeerComparisonSection
