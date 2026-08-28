import React, {useEffect, useState} from "react"
import Link from "next/link"
import Image from '@componentsLegacy/CustomImage'
import { faCheck, faTimes, faDownload, faSearch, faAngleLeft, faAngleRight  } from "@fortawesome/free-solid-svg-icons"
import {Container, Button, ListGroup, Form, Tab, Row, Col, Badge, Breadcrumb, Nav} from "react-bootstrap"
import universe from "@data/universe.json"
import axios from 'axios';
import { useRouter } from "next/router"
import RankingListPagination from "@componentsLegacy/RankingPagination"
import {connect} from 'react-redux'

export async function getServerSideProps({ params, query }) {

    console.log(params)
    console.log(query)
    return {
      props: {
        nav: {
          light: true,
          classes: "shadow",
          color: "white",
        }
      },
    }
  }

  
  const RankingTables = (props) => {
    const [bucketRequest, setBucketRequest] = useState(props.bucketResults.bucketKeys[0])
    let bucketResults = props.bucketResults
    console.log(bucketResults)


    const handleBucketRequest = (e) => {
        console.log(e.target.text)
        setBucketRequest(e.target.text)
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
                    <h3 className="display-3 fw-bold text-shadow">{bucketResults.bucketName}</h3>
                    <p className="text-lg text-shadow mt-3">{bucketResults.indexName}</p>
                    </Col>
                </Row>
                </Container>
            </section>
            <Container className="position-relative mt-n7 z-index-20">
                <Tab.Container
                id="top-tabs"
                defaultActiveKey={bucketResults.bucketKeys[0]}
                >
                <Nav variant="tabs" className="search-bar-nav-tabs">
                    {bucketResults.bucketKeys &&
                    bucketResults.bucketKeys.map((tab, index) => (
                        <Nav.Item
                        key={index}
                        className={
                            index < bucketResults.bucketKeys - 1 ? "me-2" : ""
                        }
                        >
                        <Nav.Link eventKey={tab} value={tab} onClick={handleBucketRequest}>{tab}</Nav.Link>
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
                <RankingListPagination dataProps={bucketResults.bucketData} metric={bucketResults.factorName} bucket={bucketRequest}/>
            </section>
            </React.Fragment>
      )

  }

  function mapStateToProps(state){
    return{
      bucketResults:state.bucket
    }
  }



  export default connect(mapStateToProps)(RankingTables);