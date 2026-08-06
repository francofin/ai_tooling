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
                    <p className="text-sm fw-bold">{typeof stock.metric === 'number' ? stock.metric.toFixed(2) : stock.metric}</p>
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
