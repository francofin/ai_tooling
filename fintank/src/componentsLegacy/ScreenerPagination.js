import { React, useState, useEffect } from "react";
import { Row, Col, Card, ListGroup, Badge } from "react-bootstrap";
import ReactPaginate from "react-paginate";
import Link from "next/link"
import { useRouter } from "next/router"

const ScreenListPagination = ({ itemsPerPage, dataProps }) => {
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
  };

  const adjustTimeStamp = (date) => {
    const options = { year: "numeric", month: "long", day: "numeric"}
    return new Date(date).toLocaleDateString(undefined, options)
  }
//   console.log(dataProps)

  useEffect(() => {
    setStocksShown(dataProps)
    setCurrentItems(stocksShown.slice(itemOffset, endOffset))
  }, [dataProps, endOffset, itemOffset, stocksShown])

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

  return (
    <>
      <ListGroup className="shadow mb-5">
          {currentItems.map((stock, index) => (
            <Link href="/stock-data/[ticker]" as={`/stock-data/${stock.symbol}`} passHref key={index}>
            <ListGroup.Item action className="p4" as="a">
              <Row>
                <Col lg="4" className="align-self-center mb-4 mb-lg-0">
                  <div className="d-flex align-items-center mb-3">
                    <h2 className="h5 mb-0">{stock.companyName}</h2>
                  </div>
                  <Badge
                    bg={
                      stock.founded
                        && "success-light"
                    }
                    text={
                      stock.founded && "success"
                    }
                    className="p-2"
                    pill
                  >
                    Price: {(stock.price).toFixed(2).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",")}
                  </Badge>
                </Col>
                <Col lg="8">
                  <Row>
                    <Col xs="6" md="4" lg="3" className="py-3 mb-3 mb-lg-0">
                      <h6 className="label-heading">Ticker</h6>
                      <p className="text-sm fw-bold">{stock.symbol}</p>
                      <h6 className="label-heading">Exchange</h6>
                      <p className="text-sm fw-bold">{stock.exchange}</p>
                    </Col>
                    <Col xs="6" md="4" lg="3" className="py-3 mb-3 mb-lg-0">
                      <h6 className="label-heading">Sector</h6>
                      <p className="text-sm fw-bold">{stock.sector}</p>
                    </Col>
                    <Col xs="6" md="4" lg="3" className="py-3 mb-3 mb-lg-0">
                      <h6 className="label-heading">Sub-Sector</h6>
                      <p className="text-sm fw-bold">{stock.industry}</p>
                    </Col>
                    <Col xs="6" md="4" lg="3" className="py-3 mb-3 mb-lg-0">
                      <h6 className="label-heading">Beta</h6>
                      <p className="text-sm fw-bold">{stock.beta}</p>
                    </Col>
                    <Col xs="6" md="4" lg="3" className="py-3 mb-3 mb-lg-0">
                      <h6 className="label-heading">Market Cap</h6>
                      <p className="text-sm fw-bold">${(stock.marketCap/10**9).toFixed(2).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",")}B</p>
                    </Col>
                    <Col xs="6" md="4" lg="3" className="py-3 mb-3 mb-lg-0">
                      <h6 className="label-heading">County</h6>
                      <p className="text-sm fw-bold">{stock.country}</p>
                    </Col>

                  </Row>
                </Col>
              </Row>
            </ListGroup.Item>
          </Link>
          ))}
        </ListGroup>

      <ReactPaginate
        breakLabel="..."
        nextLabel="›"
        onPageChange={handlePageClick}
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
      />
    </>
  );
};

export default ScreenListPagination;
