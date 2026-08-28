import React, {useEffect, useState, useContext} from "react"
import Link from "next/link"
import {
  Container,
  Button,
  ListGroup,
  Form,
  InputGroup,
  Row,
  Col,
  Badge,
  Breadcrumb,
  Pagination,
  Modal
} from "react-bootstrap"
import Select from "react-select"
import sector from "@data/sectors-subsectors.json"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faCheck, faTimes, faDownload, faSearch, faAngleLeft, faAngleRight  } from "@fortawesome/free-solid-svg-icons"
import { useRouter } from "next/router"
import {connect} from 'react-redux'
import ScreenListPagination from "./ScreenerPagination"


export async function getStaticProps() {
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

const Screener = (props) => {

  let screenResults = props.screenerResults
  const stockLength = screenResults.length
  const [universe, setUniverse] = useState(screenResults)
  const [sectorHookFilter, setSectorFilter] = useState('All');
  const [limitIndex, setLimitIndex] = useState(20);


  const router = useRouter();


  useEffect(() => {
    const handleSelect = (value) => {
      if (sectorHookFilter === 'All'){
        setUniverse(screenResults)
      } else{
        let sectorScreen = screenResults?.filter((p) => p.sector===value);
        setUniverse(sectorScreen)
        return sectorScreen
      }
      
    }

    handleSelect(sectorHookFilter);
  
  }, [sectorHookFilter, screenResults])

  return (
    <section className="py-5">
      <Container>
        <Breadcrumb listProps={{ className: "ps-0 justify-content-center" }}>
          <Link href="/" passHref>
            <Breadcrumb.Item>Home</Breadcrumb.Item>
          </Link>
          <Breadcrumb.Item active>Screen view</Breadcrumb.Item>
        </Breadcrumb>
        <div className="d-flex justify-content-between align-items-end mb-5">
          <h1 className="hero-heading mb-0">Screen Results</h1>
        </div>


          <div className="d-flex justify-content-between align-items-center flex-column flex-lg-row mb-5 mt-5">
          <div className="me-3">
            <p className="mb-3 mb-lg-0">
              There are <strong>{props.screenerResults.length}</strong> Equities. <i className="text-muted">Some Equities May not be listed</i>
            </p>
          </div>
          <div className="text-center">
            <label className="form-label me-5">Sector Filter</label>
            <Select
              id="sector"
              options={sector.sectors}
              value={sectorHookFilter}
              placeholder = {sectorHookFilter}
              onChange = {(e) => setSectorFilter(e.value)}
              className="dropdown bootstrap-select me-3 mb-3 mb-lg-0"
              classNamePrefix="selectpicker"
            />
          </div>
        </div>

        <ScreenListPagination dataProps={universe} itemsPerPage={limitIndex}/>      
      </Container>
    </section>
  )
}

function mapStateToProps(state){
  return{
    screenerResults:state.screener
  }
}

export default connect(mapStateToProps)(Screener);
