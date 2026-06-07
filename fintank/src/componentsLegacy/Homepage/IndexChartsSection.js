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

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, Title, Tooltip, Legend)

const CHART_ROWS = [
  { indices: ["sp500", "nas"],        cols: 6 },
  { indices: ["dj",    "rus_1000"],   cols: 6 },
  { indices: ["tsx",   "tsx_60"],     cols: 6 },
  { indices: ["rus_2000", "ftse"],    cols: 6 },
  { indices: ["nik",   "nsei"],       cols: 6 },
  { indices: ["hsi",   "vix"],        cols: 6 },
  { indices: ["short_term", "ten_year", "thirty_year"], cols: 4 },
]

const IndexChartsSection = () => (
  <section className="py-0 bg-gray-100">
    <Container>
      {CHART_ROWS.map((row, rowIdx) => (
        <Row key={rowIdx} className="pt-3">
          {row.indices.map((index) => (
            <Col key={index} lg={row.cols}>
              <IndexChartCard index={index} />
            </Col>
          ))}
        </Row>
      ))}
    </Container>
  </section>
)

export default IndexChartsSection
