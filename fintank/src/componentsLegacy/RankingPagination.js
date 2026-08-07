import React, {useState, useEffect} from "react"
import Link from "next/link"
import {
  Container,
  Row,
  Col,
  Button,
  Nav,
  ListGroup,
  Badge,
  Card,
} from "react-bootstrap"
import { Fragment } from "react"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faAngleDoubleRight } from "@fortawesome/free-solid-svg-icons"

export async function getStaticProps() {
  return {
    props: {
      nav: {
        light: true,
        classes: "shadow",
        color: "white",
      },
      title: "Real Estate",
    },
  }
}

// The four stdev bucket labels bucketActionRun() passes as `metric` in
// src/pages/factor-performance.js.
const STDEV_METRIC_LABELS = new Set([
  'Standard Deviation One Month',
  'Standard Deviation Three Month',
  'Standard Deviation Six Month',
  'Standard Deviation YTD',
])

// Stdev columns are stored as daily decimals (0.0245), kept that way for
// parity with the v1 pipeline, so toFixed(2) alone renders them as a
// meaningless "0.02" for every row. Only at display time, scale them to a
// percentage; every other numeric metric keeps its plain toFixed(2), and
// string metrics (the sector name) render verbatim.
const formatRankingMetric = (value, metricLabel) => {
  if (typeof value !== 'number') return value
  if (STDEV_METRIC_LABELS.has(metricLabel)) return `${(value * 100).toFixed(2)}%`
  return value.toFixed(2)
}

const RankingListPagination = ({dataProps, metric, bucket}) => {
  const [analysisLink, setAnalysisLink] = useState("/stock-data/[ticker]");
  const [linkAs, setLinkAs] = useState(`/stock-data/`)
  const [currentItems, setCurrentItems] = useState([])
  const [bucketRequest, setBucketRequest] = useState(bucket)
  const [stocksShown, setStocksShown] = useState([])

  useEffect(() => {
    setStocksShown(dataProps)
    setBucketRequest(bucket)
    const stocksPerBucket = stocksShown[bucketRequest]
    setCurrentItems(stocksPerBucket)
    
  }, [dataProps, bucket, stocksShown, bucketRequest])
  
  return (
    <React.Fragment>
      <div className="list-group shadow mb-5">
          {currentItems?.map((stock, index) => (
            <Link href={analysisLink} as={`${linkAs}${stock.symbol}`} passHref key={index}>
              <div
              key={index}
              className="list-group-item list-group-item-action p-4"
            >
                <Row>
                  <Col xs="6" md="4" lg="4" className="align-self-center mb-3 mb-lg-0">
                    <h6 className="label-heading">Ticker</h6>
                    <p className="text-sm fw-bold">{stock.symbol}</p>
                  </Col>
                  <Col xs="6" md="4" lg="4" className="align-self-center mb-3 mb-lg-0">
                  <h6 className="label-heading">Period Return</h6>
                    <p className="text-sm fw-bold">{stock.return.toFixed(2)}%</p>
                  </Col>
                  <Col xs="6" md="4" lg="4" className="align-self-center mb-3 mb-lg-0">
                    <h6 className="label-heading">{metric}</h6>
                    <p className="text-sm fw-bold">{formatRankingMetric(stock.metric, metric)}</p>
                  </Col>
                  {/* <Col xs="6" md="4" lg="3" className="py-3 mb-3 mb-lg-0">
                    <h6 className="label-heading">Price</h6>
                    <p className="text-sm fw-bold">{stock.price}</p>
                  </Col> */}
                  {/* <Col xs="6" md="4" lg="3" className="py-3 mb-3 mb-lg-0">
                    <h6 className="label-heading">Market Cap</h6>
                    <p className="text-sm fw-bold">{stock.mktCap}</p>
                  </Col> */}
                </Row>
              </div>
            </Link>
          ))}
    </div>
    </React.Fragment>
  )
}

export default RankingListPagination
