import { React, useState, useEffect } from "react";
import { Row, Col, Card, ListGroup, Badge } from "react-bootstrap";
import ReactPaginate from "react-paginate";
import Link from "next/link"
import { useRouter } from "next/router"

// Market cap is in the listing currency: Toyota's is yen. Only dollar listings
// (or records with no currency, as before) get a "$"; London's GBp prices
// still report market cap in pounds.
const formatCap = (value, currency) => {
  const billions = (value / 10 ** 9).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",")
  if (!currency || currency === "USD") return `$${billions}B`
  return `${billions}B ${currency === "GBp" ? "GBP" : currency}`
}

const StockListPagination = ({ itemsPerPage, dataProps }) => {
  const [itemOffset, setItemOffset] = useState(0);
  const [analysisLink, setAnalysisLink] = useState("/stock-data/[ticker]");
  const [linkAs, setLinkAs] = useState(`/stock-data/`)
  const [stocksShown, setStocksShown] = useState(dataProps)
  const [currentItems, setCurrentItems] = useState([])

  const router = useRouter();


  const endOffset = itemOffset + itemsPerPage;
//   const currentItems = stocksShown.slice(itemOffset, endOffset);
  const pageCount = Math.ceil(stocksShown.length / itemsPerPage);
  const handlePageClick = (event) => {
    const newOffset = (event.selected * itemsPerPage) % stocksShown.length;
    setItemOffset(newOffset);
    window.scrollTo(0,0)
  };

  const displayValue = (value) => {
    if (value === null || value === undefined || value === "") return "-"
    return value
  }

  useEffect(() => {
    setStocksShown(dataProps)
    setCurrentItems(stocksShown.slice(itemOffset, endOffset))
  }, [dataProps, endOffset, itemOffset, stocksShown])

  // A new list (a sector pick, an ETF screen) starts on page one; otherwise a
  // narrowed result could leave the offset past its end and show nothing.
  useEffect(() => {
    setItemOffset(0)
  }, [dataProps])

  useEffect(() => {
    switch(router.query.slug){
      case "commodity":
        setAnalysisLink("/comm-data/[ticker]")
        setLinkAs(`/comm-data/`)
        break;
      case "cryptos":
        setAnalysisLink("/crypto-data/[ticker]")
        setLinkAs(`/crypto-data/`)
        break;
      case "etfs":
        setAnalysisLink("/etf-data/[ticker]")
        setLinkAs(`/etf-data/`)
        break;
      default:
        break;
    }

}, [router.query.slug])

  const cardStyle = {
    background: "rgba(10, 10, 20, 0.82)",
    backdropFilter: "blur(6px)",
    border: "none",
    borderBottom: "1px solid rgba(255,255,255,0.07)",
    color: "#fff",
  }

  const labelStyle = {
    fontSize: "0.62rem",
    letterSpacing: "0.12em",
    textTransform: "uppercase",
    color: "rgba(255,255,255,0.45)",
    marginBottom: "2px",
  }

  const valueStyle = {
    fontSize: "0.85rem",
    fontWeight: 600,
    color: "#fff",
    marginBottom: 0,
  }

  return (
    <>
      <div
        className="mb-5"
        style={{
          background: "rgba(10, 10, 20, 0.82)",
          borderRadius: "8px",
          backdropFilter: "blur(6px)",
          border: "1px solid rgba(255,255,255,0.1)",
          overflow: "hidden",
        }}
      >
          {currentItems.map((stock, index) => (
            <Link href={analysisLink} as={`${linkAs}${stock.symbol}`} passHref legacyBehavior key={index}>
              <a
                className="text-decoration-none d-block"
                style={{
                  ...cardStyle,
                  padding: "1rem 1.25rem",
                  transition: "background 0.15s",
                }}
                onMouseEnter={e => e.currentTarget.style.background = "rgba(30,30,50,0.9)"}
                onMouseLeave={e => e.currentTarget.style.background = "rgba(10,10,20,0.82)"}
              >
                <Row className="align-items-center">
                  <Col lg="4" className="mb-3 mb-lg-0">
                    <div className="fw-semibold mb-1" style={{ fontSize: "0.92rem", color: "#fff" }}>
                      {displayValue(stock.name)}
                    </div>
                    <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                      <span
                        style={{
                          fontSize: "0.68rem",
                          background: "rgba(255,255,255,0.08)",
                          color: "rgba(255,255,255,0.65)",
                          borderRadius: "4px",
                          padding: "2px 7px",
                        }}
                      >
                        {displayValue(stock.country)}
                      </span>
                      <span
                        style={{
                          fontSize: "0.68rem",
                          background: "rgba(255,255,255,0.08)",
                          color: "rgba(255,255,255,0.65)",
                          borderRadius: "4px",
                          padding: "2px 7px",
                        }}
                      >
                        {displayValue(stock.exchange_short_name)}
                      </span>
                    </div>
                  </Col>
                  <Col lg="8">
                    <Row>
                      <Col xs="6" md="3" className="py-2">
                        <div style={labelStyle}>Ticker</div>
                        <div style={valueStyle}>{displayValue(stock.symbol)}</div>
                        <div style={{ ...labelStyle, marginTop: "8px" }}>Beta</div>
                        <div style={valueStyle}>{displayValue(stock.beta)}</div>
                      </Col>
                      <Col xs="6" md="3" className="py-2">
                        <div style={labelStyle}>Sector</div>
                        <div style={{ ...valueStyle, fontSize: "0.78rem" }}>{displayValue(stock.sector)}</div>
                        <div style={{ ...labelStyle, marginTop: "8px" }}>Sub Sector</div>
                        <div style={{ ...valueStyle, fontSize: "0.78rem" }}>{displayValue(stock.industry)}</div>
                      </Col>
                      <Col xs="6" md="3" className="py-2">
                        <div style={labelStyle}>52W Range</div>
                        <div style={valueStyle}>{displayValue(stock.last_range)}</div>
                      </Col>
                      <Col xs="6" md="3" className="py-2">
                        <div style={labelStyle}>{stock.is_etf ? "AUM" : "Market Cap"}</div>
                        <div style={valueStyle}>
                          {stock.market_cap === null || stock.market_cap === undefined
                            ? "-"
                            : formatCap(stock.market_cap, stock.currency)}
                        </div>
                      </Col>
                    </Row>
                  </Col>
                </Row>
              </a>
            </Link>
          ))}
      </div>

      <ReactPaginate
        breakLabel="..."
        nextLabel="›"
        onPageChange={handlePageClick}
        forcePage={pageCount ? Math.floor(itemOffset / itemsPerPage) : undefined}
        pageRangeDisplayed={5}
        marginPagesDisplayed={1}
        pageCount={pageCount}
        previousLabel="‹"
        renderOnZeroPageCount={null}
        containerClassName="justify-content-center pagination"
        previousClassName="page-item"
        previousLinkClassName="page-link"
        nextClassName="page-item"
        nextLinkClassName="page-link"
        pageClassName="page-item"
        pageLinkClassName="page-link"
        breakClassName="page-item"
        breakLinkClassName="page-link"
        activeClassName="active"
        disabledClassName="disabled"
        style={{ filter: "invert(1) hue-rotate(180deg)" }}
      />
    </>
  );
};

export default StockListPagination;
