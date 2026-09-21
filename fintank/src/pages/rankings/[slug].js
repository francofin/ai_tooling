import React, {useEffect, useMemo, useState} from "react"
import Link from "next/link"
import Image from '@componentsLegacy/CustomImage'
import { faCheck, faTimes, faDownload, faSearch, faAngleLeft, faAngleRight  } from "@fortawesome/free-solid-svg-icons"
import {Container, Button, ListGroup, Form, Tab, Row, Col, Badge, Breadcrumb, Nav} from "react-bootstrap"
import universe from "@data/universe.json"
import axios from 'axios';
import { useRouter } from "next/router"
import RankingListPagination from "@componentsLegacy/RankingPagination"
import {connect} from 'react-redux'

// The slugs factor-performance.js opens with window.open(), mapped to the same
// headings it dispatches as `bucketName`. The store is the source of truth for
// the heading; this is only the fallback for a document that never received a
// dispatch (a direct visit, a refresh, a shared link), so the page can still
// say which ranking was asked for instead of rendering an anonymous blank.
const FACTOR_TITLES = {
    pe: 'Price to Earnings Rankings',
    ps: 'Price to Sales Rankings',
    pb: 'Price to Book Rankings',
    pcf: 'Price to Cash Flow Rankings',
    div: 'Dividend Yield Rankings',
    fcf: 'Free Cash Flow Rankings',
    de: 'Debt to Equity Rankings',
    roe: 'Return on Equity Rankings',
    cfd: 'Cash Flow to Debt Rankings',
    stdone: 'Standard Deviation One Month Rankings',
    stdthree: 'Standard Deviation Three Month Rankings',
    stdsix: 'Standard Deviation Six Month Rankings',
    stdytd: 'Standard Deviation Year to Date Rankings',
    beta: 'Beta Rankings',
    sector: 'Sector Rankings',
}

export async function getServerSideProps({ params }) {

    return {
      props: {
        slug: params?.slug ?? null,
        nav: {
          light: true,
          classes: "shadow",
          color: "white",
        }
      },
    }
  }


  const RankingTables = (props) => {
    // This page is only ever populated from Redux, and it is populated in a
    // *different* document: factor-performance.js dispatches the bucket, then
    // window.open()s /rankings/<slug> in a new tab, which boots a fresh store
    // at initState. So every field here can legitimately be missing — on a
    // direct visit, a refresh, a shared link, during SSR, or simply in the tick
    // before redux-persist rehydrates. Default every read off the store rather
    // than trusting its shape.
    const bucketResults = props.bucketResults || {}

    const bucketKeys = useMemo(
        () => (Array.isArray(bucketResults.bucketKeys) ? bucketResults.bucketKeys : []),
        [bucketResults.bucketKeys]
    )
    const bucketData = bucketResults.bucketData || {}
    const factorName = bucketResults.factorName || ''
    const indexName = bucketResults.indexName || ''
    // typeof guard because the slug is whatever is in the URL, and an inherited
    // key ("constructor") would otherwise hand React a function to render.
    const slugTitle =
        typeof FACTOR_TITLES[props.slug] === 'string' ? FACTOR_TITLES[props.slug] : ''
    const bucketName = bucketResults.bucketName || slugTitle || 'Factor Rankings'

    const hasBuckets = bucketKeys.length > 0

    const [bucketRequest, setBucketRequest] = useState(bucketKeys[0] ?? null)

    // useState only seeds once, but bucketKeys arrives late on a rehydrate and
    // is swapped wholesale when another factor is dispatched into the store, so
    // re-seed the selection whenever it stops pointing at a live bucket.
    useEffect(() => {
        setBucketRequest((current) => {
            if (!bucketKeys.length) return null
            return bucketKeys.includes(current) ? current : bucketKeys[0]
        })
    }, [bucketKeys])

    const handleBucketRequest = (key) => {
        setBucketRequest(key)
    }

    return (
        <React.Fragment>
            <section className="d-flex align-items-center dark-overlay py-2">
                <Image
                src={`/images/Research/research2.jpg`}
                layout="fill"
                className="bg-image"
                alt="Hero image"
                loading="eager"
                priority={true}
                />
                <Container className="py-6 py-lg-7 text-white overlay-content text-center">
                <Row>
                    <Col xl="10" className="mx-auto">
                    <h3 className="display-3 fw-bold text-shadow">{bucketName}</h3>
                    <p className="text-lg text-shadow mt-3">{indexName}</p>
                    </Col>
                </Row>
                </Container>
            </section>
            {hasBuckets ? (
            <React.Fragment>
            <Container className="position-relative mt-n7 z-index-20">
                <Tab.Container
                id="top-tabs"
                activeKey={bucketRequest}
                onSelect={handleBucketRequest}
                >
                <Nav variant="tabs" className="search-bar-nav-tabs">
                    {bucketKeys.map((tab, index) => (
                        <Nav.Item
                        key={index}
                        className={
                            index < bucketKeys.length - 1 ? "me-2" : ""
                        }
                        >
                        <Nav.Link eventKey={tab}>{tab}</Nav.Link>
                        </Nav.Item>
                    ))}
                </Nav>
                <div className="search-bar search-bar-with-tabs p-3 p-lg-4">
                    <Tab.Content>
                    </Tab.Content>
                </div>
                </Tab.Container>
            </Container>
            <section className="py-5">
                <RankingListPagination dataProps={bucketData} metric={factorName} bucket={bucketRequest}/>
            </section>
            </React.Fragment>
            ) : (
            <Container className="position-relative mt-n7 z-index-20">
                <div className="search-bar p-4 p-lg-5 text-center">
                    <h5 className="mb-3">No rankings loaded</h5>
                    <p className="text-muted mb-4">
                        These tables are built from the factor screen, so they only exist in
                        this tab once a ranking has been run. Pick an index and a period on
                        the factor performance page, then open the ranking from there.
                    </p>
                    <Link href="/factor-performance" passHref legacyBehavior>
                        <Button variant="outline-primary">Go to factor performance</Button>
                    </Link>
                </div>
            </Container>
            )}
            </React.Fragment>
      )

  }

  function mapStateToProps(state){
    return{
      bucketResults:state.bucket
    }
  }



  export default connect(mapStateToProps)(RankingTables);
