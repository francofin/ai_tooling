import React, { useEffect, useState } from "react"
import {
  Container,
  Row,
  Col,
  Card,
  Badge,
  InputGroup,
  Breadcrumb,
  Form,
  Button,
  ButtonGroup,
} from "react-bootstrap"
import data from "@data/knowledge-base.json"
import Link from "next/link"
import Icon from "@componentsLegacy/Icon"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faAngleDoubleRight, faSearch } from "@fortawesome/free-solid-svg-icons"
import { faArrowTrendDown, faArrowTrendUp } from "@fortawesome/free-solid-svg-icons"
import { useIndex } from "@hooks/UseIndex"
import axios from 'axios';
import { useEtfPerformance } from "@hooks/useEtf";
import { useCryptoPerformance } from "@hooks/useCryptoPerformance";
// Shared with the index heat map's tooltip so the two renderings of a quote agree.
import { fmtPrice, fmtMarketCap, fmtTimestamp } from "@utils/quoteFormat";


const UNIVERSE_DATA_OPTIONS = [
  { value: "equity", label: "Equity" },
  { value: "crypto", label: "Crypto" },
  { value: "etf", label: "ETF" },
]

const CRYPTO_LIST = ["BTCUSD,ETHUSD,USDTUSD,BNBUSD,SOLUSD,SLAMUSD,SETHUSD,USDCUSD,XRPUSD,STETHUSD,DOGEUSD,HFTUSD,WTRXUSD,TRXUSD,TONUSD, \
                ADAUSD,WSTETHUSD,AVAXUSD,SHIBUSD,WBTCUSD,USTUSD,WETHUSD,VINUUSD,BCHUSD,LINKUSD,ETHMUSD,DOTUSD,LEOUSD,DAIUSD,LTCUSD,NEARUSD, \
                SUIUSD,APTUSD,UNIUSD,BTCBUSD,WBETHUSD,WEOSUSD,PEPEUSD,TAOUSD,ICPUSD,FETUSD,STEAMXUSD,KASUSD,XMRUSD,USDE,XLMUSD,ETCUSD,WBTUSD,STXUSD, \
                RNDRUSD,WIFUSD,OKBUSD,AAVEUSD,IMXUSD,FILUSD,ARBUSD,OPUSD,MNTUSD,CROUSD,FTMUSD,INJUSD,HBARUSD,RUNEUSD,VETUSD,ATOMUSD,LUNA1USD,BGBUSD,BONKUSD, \
                PAIUSD,POPCATUSD,GRTUSD,SEIUSD,JUPUSD,RETHUSD,PYTHUSD,FLOKIUSD,OMUSD,WLDUSD,THETAUSD,HNTUSD,TIAUSD,ZBUUSD,FLZUSD,KCSUSD,ARUSD,ONDOUSD,ALGOUSD,MKRUSD, \
                MSOLUSD,RAYUSD,BEAMUSD,LDOUSD,BSVUSD,BRETTUSD,MEWUSD,JASMYUSD,MATICUSD,BTTUSD,APEUSD,FTNUSD"];

const CRYPTO_SYMBOL_SET = new Set(CRYPTO_LIST[0].split(',').map(s => s.trim()))

export async function getStaticProps() {

//     const res = await axios.get(`${process.env.NEXT_PUBLIC_FINTANK_API_URL}/market_indexes/`);
// //   console.log(res)
//   const data = res.data;

  return {
    props: {
      nav: {
        light: true,
        classes: "shadow",
        color: "white",
      },
      title: "Market Performance",
    },
  }
}

const KnowledgeBase = (props) => {
    const {data: indexData} = useIndex();
    const {data: etfData} = useEtfPerformance();
    const {data: cryptoData} = useCryptoPerformance();

    const [universeData, setUniverseData] = useState("equity");
    const [allIndexData, setAllIndexData] = useState([])
    const universeDataLabel = UNIVERSE_DATA_OPTIONS.find(o => o.value === universeData)?.label ?? "Equity";

    useEffect(() => {
        const toArray = (val) => Array.isArray(val) ? val : []
        const sortByChange = (arr) =>
            [...toArray(arr)].sort((a, b) => b.changesPercentage - a.changesPercentage)
        if (universeData === "equity") {
            setAllIndexData(sortByChange(indexData))
        } else if (universeData === "etf") {
            setAllIndexData(sortByChange(etfData))
        } else if (universeData === "crypto") {
            setAllIndexData(toArray(cryptoData).filter(item => item.marketCap > 500_000_000 && CRYPTO_SYMBOL_SET.has(item.symbol)))
        }
    }, [indexData, etfData, cryptoData, universeData])

    console.log(cryptoData)


  return (
    <React.Fragment>
      <section className="hero py-5 py-lg-7">
        <Container className="position-relative">
          <Breadcrumb
            listProps={{
              className: "ps-0 justify-content-center",
            }}
          >
            <Link href="/" passHref>
              <Breadcrumb.Item className="me-2">Home</Breadcrumb.Item>
            </Link>
              <Breadcrumb.Item active>{props.title}</Breadcrumb.Item>
          </Breadcrumb>

          <h1 className="hero-heading">{universeDataLabel}</h1>

          <div className="d-flex justify-content-center mt-3">
            <ButtonGroup>
              {UNIVERSE_DATA_OPTIONS.map((option) => (
                <Button
                  key={option.value}
                  variant={universeData === option.value ? "primary" : "outline-primary"}
                  onClick={() => setUniverseData(option.value)}
                >
                  {option.label}
                </Button>
              ))}
            </ButtonGroup>
          </div>

        </Container>
      </section>
      <section>
        <Container>
          <Row className="py-5 pt-lg-0 mt-lg-n5">
            {allIndexData?.map((block) => (
              <Col key={block.symbol} lg="4" className="mb-4 text-center">
                <Card className="border-0 shadow-sm hover-animate h-100">
                  <Card.Body className="p-4">
                    <div className="mb-2">
                      {block.changesPercentage > 0
                        ? <FontAwesomeIcon icon={faArrowTrendUp} size="2x" style={{color:"green"}}/>
                        : <FontAwesomeIcon icon={faArrowTrendDown} size="2x" style={{color:"red"}}/>
                      }
                    </div>
                    <h5 className="mb-0">{block.name}</h5>
                    <p className="text-muted text-sm mb-2">{block.symbol}</p>

                    <p className="fw-semibold fs-5 mb-1">${fmtPrice(block.price)}</p>
                    <p className="mb-2" style={{color: block.changesPercentage > 0 ? "green" : "red"}}>
                      {block.changesPercentage > 0 ? "+" : ""}{block.changesPercentage?.toFixed(2)}%
                    </p>

                    <div className="d-flex justify-content-center gap-3 text-sm text-muted mb-1">
                      {block.dayLow != null && <span>Low: ${fmtPrice(block.dayLow)}</span>}
                      {block.dayHigh != null && <span>High: ${fmtPrice(block.dayHigh)}</span>}
                    </div>
                    <div className="d-flex justify-content-center gap-3 text-sm text-muted mb-2">
                      {block.yearLow != null && <span>52W Low: ${fmtPrice(block.yearLow)}</span>}
                      {block.yearHigh != null && <span>52W High: ${fmtPrice(block.yearHigh)}</span>}
                    </div>

                    {block.marketCap != null && (
                      <p className="text-muted text-sm mb-1">Mkt Cap: {fmtMarketCap(block.marketCap)}</p>
                    )}
                    {block.priceAvg50 != null && (
                      <p className="text-muted text-sm mb-1">50D Avg: ${fmtPrice(block.priceAvg50)}</p>
                    )}
                    {block.priceAvg200 != null && (
                      <p className="text-muted text-sm mb-1">200D Avg: ${fmtPrice(block.priceAvg200)}</p>
                    )}
                    {block.eps != null && (
                      <p className="text-muted text-sm mb-1">EPS: {block.eps.toFixed(2)}</p>
                    )}
                    {block.pe != null && (
                      <p className="text-muted text-sm mb-1">P/E: {block.pe.toFixed(2)}</p>
                    )}

                    {block.timestamp != null && (
                      <p className="text-muted mt-2 mb-0" style={{fontSize:"0.7rem"}}>
                        {fmtTimestamp(block.timestamp)}
                      </p>
                    )}
                  </Card.Body>
                </Card>
              </Col>
            ))}
          </Row>
        </Container>
      </section>
    </React.Fragment>
  )
}

export default KnowledgeBase
