import React, { useMemo } from "react"
import { Container, Row, Col } from "react-bootstrap"
import { Line } from "react-chartjs-2"

import SectionUnavailable from "./SectionUnavailable"
import { buildPriceChart, hasValues, SERIES_COLORS } from "@utils/indexDetail/chartBuilders"
import { indexLineOptions } from "@utils/indexDetail/chartOptions"

// Overlays are drawn only when the payload carries them, so a short-history
// proxy ETF with no 200-day average simply shows fewer lines.
const OVERLAYS = [
  { key: "ma_50", label: "50 Day MA", color: SERIES_COLORS.accent },
  { key: "ma_200", label: "200 Day MA", color: SERIES_COLORS.neutral },
]

const IndexPriceChart = ({ title, dates, series }) => {
  const chart = useMemo(() => {
    if (!hasValues(series?.adjClose)) return null
    return buildPriceChart({
      dates,
      price: series.adjClose,
      priceLabel: title,
      overlays: OVERLAYS.filter((overlay) => hasValues(series[overlay.key])).map(
        (overlay) => ({
          label: overlay.label,
          values: series[overlay.key],
          color: overlay.color,
        })
      ),
    })
  }, [dates, series, title])

  return (
    <section className="py-0 bg-gray-100">
      <Container>
        <Row className="pt-3">
          <Col lg="12">
            {chart ? (
              <Line options={indexLineOptions} data={chart} height={100} width={200} />
            ) : (
              <SectionUnavailable message="Price history is unavailable for this index." />
            )}
          </Col>
        </Row>
      </Container>
    </section>
  )
}

export default IndexPriceChart
