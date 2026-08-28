import React, { useMemo } from "react"
import { Container, Row, Col } from "react-bootstrap"
import { Line } from "react-chartjs-2"

import SectionUnavailable from "./SectionUnavailable"
import { useIndexComparison } from "@hooks/useIndexComparison"
import { buildDualAxisChart, hasValues } from "@utils/indexDetail/chartBuilders"
import { dualAxisOptions } from "@utils/indexDetail/chartOptions"

const VIX_KEY = "vix"

/**
 * Index level against the CBOE Volatility Index.
 *
 * Reuses the comparison endpoint rather than adding one: the payload carries
 * raw levels for both sides, which is all this chart needs. Two axes, since an
 * index in the thousands and a VIX in the teens share no scale -- the old
 * version plotted both on one axis, flattening the VIX into the baseline.
 */
const VixComparisonChart = ({ slug, baseTitle }) => {
  const { comparison, error } = useIndexComparison(slug, VIX_KEY)

  const chart = useMemo(() => {
    const price = comparison?.metrics?.price?.adjClose
    if (!hasValues(price?.base) || !hasValues(price?.peer)) return null
    return buildDualAxisChart({
      dates: comparison.dates,
      base: price.base,
      peer: price.peer,
      baseLabel: baseTitle,
      peerLabel: comparison.peer?.title ?? "CBOE Volatility Index",
    })
  }, [comparison, baseTitle])

  if (error) return null

  return (
    <section className="py-4 bg-gray-100">
      <Container>
        <div className="text-block">
          <h6 className="mb-3">{baseTitle} Relative to the CBOE Volatility Index (VIX)</h6>
          <p className="text-muted fw-light">
            The VIX measures expected market volatility from the implied volatility of
            S&amp;P 500 index options. Reading an index against it helps gauge short-term
            sentiment and how certain market participants are. The relationship is not
            exact, but markets tend to move inversely to the VIX: a rising VIX usually
            accompanies falling equity prices. Readings above 25 indicate a volatile
            market, and higher still points to real uncertainty about direction. It is one
            indicator among many, not a forecast.
          </p>
        </div>
        <Row className="pt-3">
          <Col lg="12">
            {chart ? (
              <Line options={dualAxisOptions} data={chart} height={100} width={200} />
            ) : (
              <SectionUnavailable message="Volatility comparison is loading or unavailable." />
            )}
          </Col>
        </Row>
      </Container>
    </section>
  )
}

export default VixComparisonChart
