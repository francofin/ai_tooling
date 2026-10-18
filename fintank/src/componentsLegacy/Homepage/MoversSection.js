import React, { useState } from "react"
import { Container, Row, Spinner } from "react-bootstrap"
import Select from "react-select"
import dynamic from "next/dynamic"
import Swiper from "../Swiper"
import { useIndexHeatMaps } from "../../hooks/useIndexHeatMap"
import { constituentIndexMaps } from "../../utils/IndexMappings"

const ReactApexChart = dynamic(() => import("react-apexcharts"), { ssr: false })

const MoversSection = ({ moverData, data }) => {
  const [indexHeatMapValue, setIndexHeatMapValue] = useState(constituentIndexMaps[0].value)
  const [indexHeatMapLabel, setIndexHeatMapLabel] = useState(constituentIndexMaps[0].label)
  const {
    options: heatMapOptions,
    series: heatMapSeries,
    loading: heatMapLoading,
    disclosure: heatMapDisclosure,
  } = useIndexHeatMaps(indexHeatMapValue, indexHeatMapLabel)

  return (
    <section className="py-6 bg-gray-100">
      <Container>
        <div className="text-center pb-lg-4">
          <p className="subtitle text-primary">{data.movers.subTitle}</p>
          <h2 className="mb-5">{data.movers.gainers}</h2>
        </div>
        <Swiper
          className="swiper-container-mx-negative pt-1 pb-5"
          wrapperClasses="dark-overlay"
          moverReturns
          perView={1}
          md={2}
          lg={3}
          xl={4}
          data={moverData?.gainers}
          loop
          speed={1000}
          pagination
          autoplay={{ delay: 5000 }}
        />
      </Container>
      <Container>
        <div className="text-center pb-lg-4">
          <h2 className="mb-5">{data.movers.losers}</h2>
        </div>
        <Swiper
          className="swiper-container-mx-negative pt-1 pb-5"
          wrapperClasses="dark-overlay"
          moverReturns
          perView={1}
          md={2}
          lg={3}
          xl={4}
          data={moverData?.losers}
          loop
          speed={1000}
          pagination
          autoplay={{ delay: 5000 }}
        />
      </Container>
      <Container fluid>
        <div className="text-center">
          <label className="form-label me-2">Select Index For Heat Map Performance</label>
          <Select
            id="heatmap-index"
            options={constituentIndexMaps}
            value={indexHeatMapValue}
            placeholder={indexHeatMapLabel}
            onChange={(opt) => {
              setIndexHeatMapLabel(opt.label)
              setIndexHeatMapValue(opt.value)
            }}
            className="dropdown bootstrap-select me-3 mb-3 mb-lg-0"
            classNamePrefix="selectpicker"
          />
        </div>
        <div className="text-center pb-lg-4">
          <p className="h2">{indexHeatMapLabel} Constituent Stock Performance</p>
          {heatMapDisclosure && !heatMapLoading && (
            <p className="text-muted small mb-0">
              Showing the {heatMapDisclosure.perSide.toLocaleString()} strongest and{" "}
              {heatMapDisclosure.perSide.toLocaleString()} weakest movers of{" "}
              {heatMapDisclosure.total.toLocaleString()} constituents.{" "}
              {heatMapDisclosure.omitted.toLocaleString()} names between those extremes
              are not drawn. Hover any tile for its full quote.
            </p>
          )}
        </div>
        <Row>
          {typeof window !== "undefined" && (
            heatMapLoading ? (
              <div
                style={{
                  height: 750,
                  background: '#0d1117',
                  borderRadius: 6,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Spinner animation="border" variant="light" role="status">
                  <span className="visually-hidden">Loading...</span>
                </Spinner>
              </div>
            ) : heatMapOptions ? (
              <ReactApexChart
                options={heatMapOptions}
                series={heatMapSeries}
                type="treemap"
                height={750}
              />
            ) : (
              <div
                style={{
                  height: 750,
                  background: '#0d1117',
                  borderRadius: 6,
                  opacity: 0.5,
                }}
                className="placeholder-glow"
              />
            )
          )}
        </Row>
      </Container>
    </section>
  )
}

export default MoversSection
