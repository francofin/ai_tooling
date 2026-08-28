import React, {useEffect, useMemo, useState} from "react"
import Link from "next/link"
import Select from "react-select"
import sector from "@data/sectors-subsectors.json"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faCheck, faTimes, faDownload, faSearch, faAngleLeft, faAngleRight  } from "@fortawesome/free-solid-svg-icons"
import {Container, Button, ListGroup, Form, InputGroup, Row, Col, Badge, Breadcrumb, Modal} from "react-bootstrap"
import universe from "@data/universe.json"
import { useRouter } from "next/router"
import {connect} from 'react-redux';
import screenerAction from '../../actions/screenerAction'
import { bindActionCreators } from "redux"
import StockListPagination from "@componentsLegacy/StockPagination"
import { useStockNames } from "@hooks/useStockNames"
import { useUniverseProfiles } from "@hooks/useUniverseProfiles"


export function getAllPostIds() {
  return universe.posts.map((post) => ({
    params: {
      slug: post.slug,
    },
  }))
}
  
export async function getPostData(slug) {
  for (var i = 0; i < universe.posts.length; i++) {
    if (universe.posts[i].slug == slug) {
      return {
        stockItem: universe.posts[i],
        slug
      }
    }
  }
  // Explicit null, not a fall-through undefined: Next rejects undefined when it
  // serialises props, so an unrecognised slug used to 500 during SSR instead of
  // rendering the page.
  return null
}

export async function getServerSideProps({ params, query }) {
  const postData = await getPostData(query.slug)
  let slug = params.slug

return {
  props: {
    nav: {
      light: true,
      classes: "shadow",
      color: "white",
    },
    loggedUser: false,
    title: "Fintank Stock Screener",
    postData,
    slug
  },
}
}

const Universe = (props) => {

  const router = useRouter();

  const [modal, setModal] = useState(false)

    const onClickModal = () => {
        setModal(!modal)
    }

  const { data: profilesData, isLoading } = useUniverseProfiles(router.query.slug)
  const universeRecords = useMemo(() => profilesData?.data ?? [], [profilesData])


  const [universe, setUniverse] = useState([])
  const [keyWord, setKeyWord] = useState('');
  const [ticker, setTicker] = useState('');
  const [minMarketCap, setMinMarketCap] = useState(0);
  const [maxMarketCap, setMaxMarketCap] = useState(100000000000000);
  const [minPrice, setMinPrice] = useState(0.00);
  const [maxPrice, setMaxPrice] = useState(99999999);
  const [showPriceFilter, setShowPriceFilter] = useState(true);
  const [maxBeta, setMaxBeta] = useState(100);
  const [minBeta, setMinBeta] = useState(0);
  const [showBetaFilter, setShowBetaFilter] = useState(true);
  const [minDividend, setMinDividend] = useState(0);
  const [country, setCountry] = useState('');
  const [sectorScreener, setSectorScreener] = useState('');
  const [subSectorScreener, setSubSectorScreener] = useState('');
  const [searchParam, setSearchParam] = useState('');
  // let sectorFilter = null
  const [sectorHookFilter, setSectorFilter] = useState('All');
  const [subSectorFilter, setSubSectorFilter] = useState('All');
  const [createLink, setCreateLink] = useState(false);
  const [loading, setLoading] = useState(false);
  const [isEquityRelated, setIsEquityRelated] = useState(true);
  const [searchFocus, setSearchFocus] = useState(false)
  const [activeSuggestion, setActiveSuggestion] = useState(0)
  const [filteredSuggestions, setFilteredSuggestions] = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [searchTicker, setSearchTicker] = useState('')
  const onFocus = () => setSearchFocus(!searchFocus)


  const {data:stockNames} = useStockNames();
  const allStocks = stockNames?.stocks

  const returnQuery = (e) => {
    e.preventDefault();

    router.push(`/stock-data/${searchTicker}`)
  }


  const onSearchChange = (e) => {
    // const { suggestions  = allStocks;
    const userInput = e.target.value;

    // Filter our suggestions that don't contain the user's input
    const suggestionFilter = allStocks?.filter(
      suggestion =>
        (suggestion['symbol'].toLowerCase().indexOf(userInput.toLowerCase()) > -1) || (suggestion['name'].toLowerCase().indexOf(userInput.toLowerCase()) > -1)
    );


    // setActiveSuggestion(0)
    setFilteredSuggestions(suggestionFilter)
    setShowSuggestions(true)
    setTicker(userInput)
  };

  const onKeySuggestDown = (e) => {
    if (e.keyCode === 13) {
      setActiveSuggestion(0)
      setShowSuggestions(false)
      setTicker(filteredSuggestions[activeSuggestion])
    }
    // User pressed the up arrow
    else if (e.keyCode === 38) {
      if (activeSuggestion === 0) {
        return;
      }

      setActiveSuggestion(activeSuggestion - 1);
    }
    // User pressed the down arrow
    else if (e.keyCode === 40) {
      if (activeSuggestion - 1 === filteredSuggestions.length) {
        return;
      }

      setActiveSuggestion(activeSuggestion + 1);
    }
  };

  const onSuggestionClick = (item) => {

    setActiveSuggestion(0)
    setShowSuggestions(false)
    setFilteredSuggestions([])
    setSearchTicker(item)
    setTicker(item)

  };

  const renderSuggestedList = () => {
    return(
    <ListGroup variant="flush" className="shadow mb-5" style={{position:'relative'}}>
      {filteredSuggestions?.map((suggestion, i) => {
        return(
          <ListGroup.Item key={i} as="li" onClick={() => onSuggestionClick(suggestion['symbol'])}>
                {suggestion['symbol']} - {suggestion['name']} - {suggestion['exchange']}
            </ListGroup.Item>
        )
      })}
    </ListGroup>
    )
  }

  const resetTicker = () => {
    // e.preventDefault()
    setTicker('')
    setFilteredSuggestions([])
    setActiveSuggestion(0)
    setShowSuggestions(false)
  }


  const handleScreenSubmit = (e) => {
    e.preventDefault();
    setLoading(true);

    const formData = {
      "market_cap_max": maxMarketCap ? maxMarketCap : null,
      "market_cap_min": minMarketCap ? minMarketCap : null,
      "beta_max": maxBeta ? maxBeta : null,
      "beta_min": minBeta ? minBeta : null,
      "beta_max": maxBeta ? maxBeta : null,
      "beta_min": minBeta ? minBeta : null,
      "sector": sectorScreener ? sectorScreener : null,
      "sub_industry": subSectorScreener ? subSectorScreener : null,
      "dividend_min": minDividend ? minDividend : null,
      "country": country ? country : null,
      "price_max": maxPrice ? maxPrice : null,
      "price_min": minPrice ? minPrice : null,
    }      
    props.screenerActionRun(formData);
    setLoading(false)
    !loading && window.open("/screener","_blank")
  }



  useEffect(() => {
    const handleSelect = (value) => {
      if (sectorHookFilter === 'All'){
        setUniverse(universeRecords)
      } else{
        let sectorScreen = universeRecords?.filter((p) => p.sector===value);
        setUniverse(sectorScreen)
        return sectorScreen
      }
    }

    handleSelect(sectorHookFilter);

  }, [sectorHookFilter, universeRecords])
  

  useEffect(() => {
    if((maxBeta === "") || (minBeta === "")) {
      setShowBetaFilter(false)
      setMaxBeta(undefined)
      setMinBeta(undefined)
    }
  }, [showBetaFilter, minBeta, maxBeta])

  useEffect(() => {
    if(minDividend === "") {
      setMinDividend(undefined)
    }
  }, [minDividend])



  useEffect(() => {
    if (['commodities', 'cryptos', 'etfs', ].indexOf(router.query.slug) >=0){
      setIsEquityRelated(false)
    }
  }, [router])


  

  return (
    <section
      className="py-5"
      style={{
        backgroundImage: "url('/images/homeImages/brooklyn.jpg')",
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundAttachment: "fixed",
        minHeight: "100vh",
        position: "relative",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "rgba(5, 5, 15, 0.78)",
          pointerEvents: "none",
        }}
      />
      <Container style={{ position: "relative", zIndex: 1 }}>
        <Breadcrumb listProps={{ className: "ps-0 justify-content-center" }} style={{ filter: "brightness(1.4)" }}>
          <Link href="/" passHref>
            <Breadcrumb.Item>Home</Breadcrumb.Item>
          </Link>
          <Breadcrumb.Item active>Host view</Breadcrumb.Item>
        </Breadcrumb>
        <div className="d-flex justify-content-between align-items-end mb-5">
          <h1 className="hero-heading mb-0" style={{ color: "#fff" }}>{props.postData.stockItem.title}</h1>
        </div>
        <Row>
            <Col xl="5" className="mx-auto">
              <Form onSubmit={returnQuery}>
                <InputGroup>
                  <Form.Control
                    type="text"
                    placeholder="Search Stock"
                    value={ticker}
                    name={"keyword"}
                    autoComplete="off"
                    onFocus={onFocus}
                    onChange ={(e) => onSearchChange(e)}
                    onBlur={() => setTimeout(() => onFocus(), 333)}
                  />
                  <Button variant="reset" size="sm" type="reset" onClick={resetTicker}>
                    <FontAwesomeIcon icon={faTimes} />
                  </Button>
                  {(showSuggestions && filteredSuggestions?.length < 40) ?
                    <div onKeyDown = {(e) => onKeySuggestDown(e)}s>
                      {renderSuggestedList()}
                    </div>:
                    ""
                    }
                </InputGroup>
              </Form>
            </Col>
          </Row>

        
          <div className="d-flex justify-content-between align-items-center flex-column flex-lg-row mb-5 mt-5">
                <div className="me-3">
                  <p className="mb-3 mb-lg-0" style={{ color: "rgba(255,255,255,0.75)" }}>
                    There are <strong style={{ color: "#fff" }}>{profilesData?.count ?? 0}</strong> Equities. <i style={{ color: "rgba(255,255,255,0.45)" }}>Some Equities May not be listed</i>
                  </p>
                </div>
                <div className="text-center">
                  <label className="form-label me-2" style={{ color: "rgba(255,255,255,0.75)" }}>Sectors</label>
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

        {isEquityRelated && <section className="pb-3">
        <Button onClick={onClickModal}>Launch Stock Screener</Button>
            <Modal show={modal} onHide={onClickModal}>
                <Modal.Header closeButton>
                    <Modal.Title className="text-uppercase" as="h6">
                    Stock Screener
                    </Modal.Title>
                </Modal.Header>
                <Modal.Body>
                    <p className="text-muted">
                    <strong>Fintank Stock Screener</strong> All Fields are not required.
                    We have crafted the ability to screen our universe based on
                    Market Cap of Stocks,Stock Dividend Yield, Beta, Price, Sector, Sub Industry
                    and Country. Screen excludes ETFs.{" "}
                    <a href="#">More Info on our Screener</a>
                    </p>
                      <div className="w-100 py-2 px-md-2 px-xxl-2 position-relative">
                     
                        <Form className="form-validate" onSubmit={handleScreenSubmit}>
                        <Row className="min-vh-20">
                          <Col md="8" lg="6" xl="6" className="d-flex align-items-center">
                            <div className="mb-4">
                              <Form.Label htmlFor="loginUsername">Maximum Market Cap</Form.Label>
                              <Form.Select aria-label="Default select example" onChange={(e)=>setMaxMarketCap(e.target.value)}>
                              <option>Select Max Market Cap</option>
                              {sector.marketCapRanges.map((sub, i) => {
                                return(
                                  <option key={i} value={sub.value}>{sub.label}</option>
                                )
                              })}
                            </Form.Select>
                            </div>
                          </Col>
                          <Col md="8" lg="6" xl="6" className="d-flex align-items-center">
                          <div className="mb-4">
                            <Form.Label htmlFor="loginUsername">Minimum Market Cap</Form.Label>
                            <Form.Select aria-label="Default select example" onChange={(e)=>setMinMarketCap(e.target.value)}>
                              <option>Select Min Market Cap</option>
                              {sector.marketCapRanges.map((sub, i) => {
                                return(
                                  <option key={i} value={sub.value}>{sub.label}</option>
                                )
                              })}
                            </Form.Select>
                          </div>
                          </Col>
                          <Col md="8" lg="6" xl="6" className="d-flex align-items-center">
                            <div className="mb-4">
                              <Form.Label htmlFor="loginUsername">Maximum Price</Form.Label>
                              <Form.Select aria-label="Default select example" onChange={(e)=>setMaxPrice(e.target.value)}>
                              <option>Select Maximum Price</option>
                              {sector.priceRanges.map((sub, i) => {
                                return(
                                  <option key={i} value={sub.value}>{sub.label}</option>
                                )
                              })}
                            </Form.Select>
                            </div>
                          </Col>
                          <Col md="8" lg="6" xl="6" className="d-flex align-items-center">
                          <div className="mb-4">
                            <Form.Label htmlFor="loginUsername">Minimum Price</Form.Label>
                            <Form.Select aria-label="Default select example" onChange={(e)=>setMinPrice(e.target.value)}>
                              <option>Select Minimum Price</option>
                              {sector.priceRanges.map((sub, i) => {
                                return(
                                  <option key={i} value={sub.value}>{sub.label}</option>
                                )
                              })}
                            </Form.Select>
                          </div>
                          </Col>
                          {showBetaFilter ?
                          <>
                          <Col md="8" lg="6" xl="6" className="d-flex align-items-center">
                            <div className="mb-4">
                              <Form.Label htmlFor="loginUsername">Maximum Beta</Form.Label>
                              <Form.Select aria-label="Default select example" onChange={(e)=>setMaxBeta(e.target.value)}>
                              <option>Select Max Beta</option>
                              {sector.betaRanges.map((sub, i) => {
                                return(
                                  <option key={i} value={sub.value}>{sub.label}</option>
                                )
                              })}
                            </Form.Select>
                            </div>
                          </Col>  
                          <Col md="8" lg="6" xl="6" className="d-flex align-items-center">
                          <div className="mb-4">
                            <Form.Label htmlFor="loginUsername">Minimum Beta</Form.Label>
                            <Form.Select aria-label="Default select example" onChange={(e)=>setMinBeta(e.target.value)}>
                              <option>Select Min Beta</option>
                              {sector.betaRanges.map((sub, i) => {
                                return(
                                  <option key={i} value={sub.value}>{sub.label}</option>
                                )
                              })}
                            </Form.Select>
                          </div>
                          </Col>
                          </> :
                           <Col md="8" lg="6" xl="6" className="d-flex align-items-center">
                            <div className="mb-4">
                              <Form.Label htmlFor="loginUsername">Beta</Form.Label>
                              <Form.Select aria-label="Default select example" onChange={(e)=>setShowBetaFilter(e.target.value)}>
                              <option>No Screen Chosen</option>
                              <option value={true}>Select Beta Screen</option>
                            </Form.Select>
                            </div>
                           </Col> }
                          <Col md="8" lg="6" xl="6" className="d-flex align-items-center">
                          <div className="mb-4">
                            <Form.Label htmlFor="loginUsername">Dividend Yield</Form.Label>
                            <Form.Select aria-label="Default select example" onChange={(e)=>setMinDividend(e.target.value)}>
                              <option>Select Dividend Treatment</option>
                              {sector.dividendFilter.map((sub, i) => {
                                return(
                                  <option key={i} value={sub.value}>{sub.label}</option>
                                )
                              })}
                            </Form.Select>
                          </div>
                          </Col>
                          </Row>

                          <div className="mb-4">
                            <Form.Label htmlFor="loginUsername">Sector</Form.Label>
                            {/* <Form.Control
                              type="text"
                              value={sectorScreener}
                              autoComplete="off"
                              onChange={(e) => setSectorScreener(e.target.value)}
                            /> */}
                            <Form.Select aria-label="Default select example" onChange={(e)=>setSectorScreener(e.target.value)}>
                              <option value="">Select Sector</option>
                              <option value="Technology">Information Technology</option>
                              <option value="Consumer Cyclical">Consumer Cyclical</option>
                              <option value="Consumer Defensive">Consumer Defensive</option>
                              <option value="Industrials">Industrials </option>
                              <option value="Financial Services">Financial Services</option>
                              <option value="Basic Materials">Materials</option>
                              <option value="Energy">Energy</option>
                              <option value="Healthcare">Healthcare</option>
                              <option value="Utilities">Utilities</option>
                              <option value="Real Estate">Real Estate</option>
                              <option value="Communication Services">Communication Services</option>
                              <option value="Financial">Financial</option>
                            </Form.Select>
                          </div>
                          <div className="mb-4">
                            <Form.Label htmlFor="loginUsername">SubSector</Form.Label>
                            <Form.Select aria-label="Default select example" onChange={(e)=>setSubSectorScreener(e.target.value)}>
                              <option>Select Sector</option>
                              {sector.subSectors.map((sub, i) => {
                                return(
                                  <option key={i} value={sub.label}>{sub.label}</option>
                                )
                              })}
                            </Form.Select>
                          </div>
                          <Row className="min-vh-20">
                            <Col md="8" lg="6" xl="6" className="d-flex align-items-center">
                            <div className="mb-4">
                              <Form.Label htmlFor="loginUsername">Country</Form.Label>
                              <Form.Select aria-label="Default select example" onChange={(e)=>setCountry(e.target.value)}>
                              <option value="">Select Country</option>
                              {sector.country.map((sub, i) => {
                                return(
                                  <option key={i} value={sub.value}>{sub.label}</option>
                                )
                              })}
                            </Form.Select>
                            </div>
                            </Col>
                          </Row>

                          
                          <div className="d-grid">
                            <Button type="submit">Run Screen</Button>
                          </div>
                        </Form>
                        
                        <hr data-content="Get More Information" className="my-3 hr-text letter-spacing-2" />
                        <hr className="my-4" />
                        <p className="text-sm text-muted">
                          {`See our Disclosures For more information on the Stock Screener.`}{" "}
                          <a href="#">Terms and Conditions</a> and{" "}
                          <a href="#">Privacy Policy</a>.
                        </p>
                      </div>
                    
                </Modal.Body>
                <Modal.Footer className="justify-content-end">
                  {createLink &&
                    <Link variant="success" href="/screener" passHref>
                      View Results
                    </Link>
                  }
                  
                    <Button variant="outline-muted" onClick={onClickModal}>
                    Close Screener
                    </Button>
                </Modal.Footer>
            </Modal>
        </section> 
        }
        
        {isLoading
          ? <p className="text-center py-5" style={{ color: "rgba(255,255,255,0.6)" }}>Loading...</p>
          : <StockListPagination dataProps={universe} itemsPerPage={20} />
        }
      </Container>
    </section>
  )
}

function mapStateToProps(state){
  return {
    screenerAction:state.screener
  }
}

function mapDispatchToProps(dispatch){

  return bindActionCreators({
    screenerActionRun:screenerAction
  }, dispatch)

}

export default connect(mapStateToProps, mapDispatchToProps)(Universe);
