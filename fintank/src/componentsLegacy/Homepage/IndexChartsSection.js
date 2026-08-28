// src/componentsLegacy/Homepage/IndexChartsSection.js
import React from "react"
import { Container, Row, Col } from "react-bootstrap"
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from "chart.js"
import IndexChartCard from "./IndexChartCard"
import { indexChartMaps } from "../../utils/IndexMappings"

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, Title, Tooltip, Legend)

const PER_ROW = 3

// Derived from the shared index list rather than repeated here, so this grid and
// the standalone picker (`Markets/IndexChartPicker`) can never disagree about
// which indexes exist. The list is in grid order, so chunking reproduces the
// original layout exactly.
const CHART_ROWS = indexChartMaps.reduce((rows, option, i) => {
  if (i % PER_ROW === 0) rows.push([])
  rows[rows.length - 1].push(option.value)
  return rows
}, [])

const IndexChartsSection = () => (
  <section className="py-0 bg-gray-100">
    <Container fluid className="px-3">
      {CHART_ROWS.map((row, rowIdx) => (
        <Row key={rowIdx} className="pt-3">
          {row.map((index) => (
            <Col key={index} lg={4}>
              <IndexChartCard index={index} />
            </Col>
          ))}
        </Row>
      ))}
    </Container>
  </section>
)

export default IndexChartsSection
