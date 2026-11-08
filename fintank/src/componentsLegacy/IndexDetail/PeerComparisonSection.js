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
import {
  SERIES_COLORS,
  buildDualAxisChart,
  buildLineChart,
  buildPairChart,
  hasValues,
  needsDualAxis,
} from "@utils/indexDetail/chartBuilders"
import {
  dualAxisOptions,
  indexLineOptions,
  percentLineOptions,
} from "@utils/indexDetail/chartOptions"

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
      const seriesLabels = {
        base: `${baseTitle} ${frequencyLabel}`,
        peer: `${peerLabel} ${frequencyLabel}`,
      }
      const args = {
        dates: comparison.dates,
        base: series.base,
        peer: series.peer,
        baseLabel: seriesLabels.base,
        peerLabel: seriesLabels.peer,
      }
      // Same units, but not necessarily the same order of magnitude: against
      // the VIX in the teens, an index in the thousands owns the whole axis
      // and the peer reads as a flat line on zero. Split the axis only when
      // the typical levels are far enough apart to warrant it.
      if (needsDualAxis(series.base, series.peer)) {
        return { data: buildDualAxisChart(args), axisLabels: seriesLabels }
      }
      return { data: buildPairChart(args), axisLabels: null }
    }

    if (!hasValues(series)) return null
    return {
      data: buildLineChart({
        dates: comparison.dates,
        values: series,
        label: `${baseTitle} vs ${peerLabel} — ${frequencyLabel} ${metric.label}`,
      }),
      axisLabels: null,
    }
  }, [comparison, metric, frequency, baseTitle])

  // Built per chart rather than mutating the exported `dualAxisOptions`, which
  // VixComparisonChart also renders with. Tick and title colours match the
  // series colours so each axis is readable as belonging to one line.
  const lineOptions = useMemo(() => {
    if (!chart?.axisLabels) {
      return isPercentMetric(metric) ? percentLineOptions : indexLineOptions
    }
    const { base, peer } = chart.axisLabels
    return {
      ...dualAxisOptions,
      scales: {
        ...dualAxisOptions.scales,
        y: {
          ...dualAxisOptions.scales.y,
          ticks: { color: SERIES_COLORS.base },
          title: { display: true, text: base, color: SERIES_COLORS.base },
        },
        y1: {
          ...dualAxisOptions.scales.y1,
          ticks: { color: SERIES_COLORS.peer },
          title: { display: true, text: peer, color: SERIES_COLORS.peer },
        },
      },
    }
  }, [chart, metric])

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
              <Line options={lineOptions} data={chart.data} height={100} width={200} />
            )}
          </Col>
        </Row>
      </Container>
    </section>
  )
}

export default PeerComparisonSection
