import { React, useState, useEffect } from "react";
import { Row, Col, Card, ListGroup, Badge } from "react-bootstrap";
import ReactPaginate from "react-paginate";
import Link from "next/link"
import { useRouter } from "next/router"

const CommodListPagination = ({ itemsPerPage, dataProps }) => {
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
    switch(router.pathname){
      case "/commodity":
        setAnalysisLink("/comm-data/[ticker]")
        setLinkAs(`/comm-data/`)
        break;
      default:
        break;
    }

}, [router.query.slug])

  return (
    <>
      <ListGroup className="shadow mb-5">
          {currentItems.map((stock, index) => (
            <Link href={analysisLink} as={`${linkAs}${stock.symbol}`} passHref key={index}>
              <ListGroup.Item action className="p4" as="a">
                <Row>
                  <Col lg="4" className="align-self-center mb-4 mb-lg-0">
                    <div className="d-flex align-items-center mb-3">
                      <h2 className="h5 mb-0">{stock.name}</h2>
                    </div>
                  </Col>
                  <Col lg="8">
                    <Row>
                      <Col xs="6" md="4" lg="3" className="py-3 mb-3 mb-lg-0">
                        <h6 className="label-heading">Ticker</h6>
                        <p className="text-sm fw-bold">{stock.symbol}</p>
                        <h6 className="label-heading">Currency</h6>
                        <p className="text-sm fw-bold">{stock.currency}</p>
                      </Col>
                      <Col xs="6" md="4" lg="3" className="py-3 mb-3 mb-lg-0">
                        <h6 className="label-heading">Price</h6>
                        <p className="text-sm fw-bold">{stock.price}</p>
                      </Col>
                      <Col xs="6" md="4" lg="3" className="py-3 mb-3 mb-lg-0">
                        <h6 className="label-heading">%Change</h6>
                        {Number(stock.changesPercentage) > 0 ?
                        <h5 className="text-sm" style={{color:"green"}}>
                        {Number(stock.changesPercentage).toFixed(1)}%
                        </h5> :
                        <h5 className="text-sm" style={{color:'red'}}>
                        {Number(stock.changesPercentage).toFixed(1)}%
                        </h5>
                        }
                      </Col>
                      <Col xs="6" md="4" lg="3" className="py-3 mb-3 mb-lg-0">
                        <h6 className="label-heading">50 Day Average</h6>
                        <p className="text-sm fw-bold">{stock.priceAvg50}</p>
                      </Col>
                      <Col xs="6" md="4" lg="3" className="py-3 mb-3 mb-lg-0">
                        <h6 className="label-heading">200 Day Average</h6>
                        <p className="text-sm fw-bold">{stock.priceAvg200}</p>
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

export default CommodListPagination;
