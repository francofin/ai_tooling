import React, {useEffect, useMemo, useState} from "react"
import Link from "next/link"
import Select from "react-select"
import sector from "@data/sectors-subsectors.json"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faCheck, faTimes, faDownload, faSearch, faAngleLeft, faAngleRight  } from "@fortawesome/free-solid-svg-icons"
import {Container, Button, ListGroup, Form, InputGroup, Row, Col, Badge, Breadcrumb} from "react-bootstrap"
import universe from "@data/universe.json"
import { useRouter } from "next/router"
import StockListPagination from "@componentsLegacy/StockPagination"
import { useStockNames } from "@hooks/useStockNames"
import { useUniverseProfiles } from "@hooks/useUniverseProfiles"
import { tickerHref } from "@utils/stockApi"
import UniverseScreener from "@componentsLegacy/UniverseScreener"

// Slugs served by /universe-profiles/ (UNIVERSE_PROFILE_SLUGS in the backend).
const EQUITY_SCREEN_SLUGS = new Set(["sp500", "nasdaq", "tsx", "tsx_small_cap", "r2000", "rmicro", "msci_eafe", "msci_sm"])


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


  const { data: profilesData, isLoading } = useUniverseProfiles(router.query.slug)
  const universeRecords = useMemo(() => profilesData?.data ?? [], [profilesData])
  // Profile-backed universes get the client-side screener, which owns the list
  // and replaces the sector dropdown (it has its own sector filter). ETFs use
  // the fund flavour: every fund's sector is "Financial Services".
  const isEtfs = router.query.slug === 'etfs'
  const screenerKind = isEtfs ? 'etf' : EQUITY_SCREEN_SLUGS.has(router.query.slug) ? 'equity' : null


  const [universe, setUniverse] = useState([])
  const [keyWord, setKeyWord] = useState('');
  const [ticker, setTicker] = useState('');
  const [searchParam, setSearchParam] = useState('');
  // let sectorFilter = null
  const [sectorHookFilter, setSectorFilter] = useState('All');
  const [subSectorFilter, setSubSectorFilter] = useState('All');
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

    // `searchTicker` is only set by picking a suggestion, so fall back to the
    // typed text rather than pushing a route with an empty segment. Funds go
    // straight to /etf-data/ -- searching an ETF from this very page used to
    // land on /stock-data/, which has no ETF profile and renders "not found".
    const target = String(searchTicker || ticker || '').trim()
    if (!target) return
    const match = allStocks?.find(
      (s) => s['symbol'].toLowerCase() === target.toLowerCase()
    )
    router.push(tickerHref(target, match?.is_etf))
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

    if (!screenerKind) handleSelect(sectorHookFilter);

  }, [sectorHookFilter, universeRecords, screenerKind])
  







  

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
          <h1 className="hero-heading mb-0" style={{ color: "#fff" }}>{props.postData?.stockItem?.title ?? router.query.slug}</h1>
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
                    There are <strong style={{ color: "#fff" }}>{profilesData?.count ?? 0}</strong> {isEtfs ? "ETFs" : "Equities"}. <i style={{ color: "rgba(255,255,255,0.45)" }}>Some {isEtfs ? "ETFs" : "Equities"} May not be listed</i>
                  </p>
                </div>
                {!screenerKind && <div className="text-center">
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
                </div>}
              </div>

        {screenerKind && !isLoading && universeRecords.length > 0 && (
          <UniverseScreener
            key={router.query.slug}
            kind={screenerKind}
            records={universeRecords}
            onResults={setUniverse}
          />
        )}

        
        {isLoading
          ? <p className="text-center py-5" style={{ color: "rgba(255,255,255,0.6)" }}>Loading...</p>
          : <StockListPagination dataProps={universe} itemsPerPage={20} />
        }
      </Container>
    </section>
  )
}

export default Universe;
