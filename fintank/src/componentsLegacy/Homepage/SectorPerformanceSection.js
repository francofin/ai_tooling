import React, { useState } from "react"
import { Container, Row, Col } from "react-bootstrap"
import Select from "react-select"
import Image from "../CustomImage"
import { useSectorData } from "../../hooks/UseSectorData"
import { sectorMappings } from "../../utils/IndexMappings"

const SectorPerformanceSection = () => {
  const [sectorValue, setSectorValue] = useState(sectorMappings[0].value)
  const [sectorLabel, setSectorLabel] = useState(sectorMappings[0].label)
  const { data: sectorData } = useSectorData(sectorValue)

  if (!sectorData) return null

  return (
    <section className="pt-6 pb-6">
      <Container fluid>
        <div className="text-center">
          <label className="form-label me-2">Select Index For Sector Performance</label>
          <Select
            id="sector-index"
            options={sectorMappings}
            value={sectorValue}
            placeholder={sectorLabel}
            onChange={(opt) => { setSectorLabel(opt.label); setSectorValue(opt.value) }}
            className="dropdown bootstrap-select me-3 mb-3 mb-lg-0"
            classNamePrefix="selectpicker"
          />
        </div>
        <div className="text-center pb-lg-4">
          <p className="h2">Sector Performance: {sectorData?.message}</p>
        </div>
        <Row className="px-4 g-0">
          {sectorData.sectors.map((sector, index) => (
            <Col
              key={index}
              xs="4"
              lg="3"
              xl="3"
              className={`px-0 ${
                index === sectorData.sectors.length ? "d-none d-lg-block d-xl-none" : ""
              }`}
            >
              <div
                style={{ minHeight: "260px" }}
                className="d-flex align-items-center dark-overlay hover-scale-bg-image"
              >
                <Image
                  src={`/images/stockPerformance/${
                    parseFloat(sector.averageChange) > 0 ? "stock-up.jpg" : "stock-down-3.jpg"
                  }`}
                  alt={sector.sector}
                  layout="fill"
                  className="bg-image"
                />
                <div className="p-3 text-white text-center z-index-20">
                  <h4 className="h4">{sector.sector}: {parseFloat(sector.averageChange).toFixed(2)}%</h4>
                </div>
              </div>
            </Col>
          ))}
        </Row>
      </Container>
    </section>
  )
}

export default SectorPerformanceSection
