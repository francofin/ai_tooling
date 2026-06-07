import React from "react"
import { Container, Row, Col, Button } from "react-bootstrap"
import Swiper from "../Swiper"
import { useStockNames } from "../../hooks/useStockNames"
import { useRouter } from "next/router"

const EXCHANGE_LIST = ["NASDAQ", "TSX", "NYSE", "CBOE"]

const HeroSection = ({ data }) => {
  const router = useRouter()
  const { data: stockNames } = useStockNames()
  const allStocks = stockNames?.stocks?.filter(
    (s) => EXCHANGE_LIST.includes(s.exchange_short_name)
  )

  const randomTickerSearch = () => {
    const idx = Math.floor(Math.random() * allStocks.length)
    router.push(`/stock-data/${allStocks[idx].symbol}`)
  }

  return (
    <section className="hero-home">
      <Swiper
        className="hero-slider"
        wrapperClasses="dark-overlay"
        data={data.swiperImages}
        simple
        effect="fade"
        speed={2000}
        autoplay={{ delay: 10000 }}
      />
      <Container className="py-6 py-md-7 text-white z-index-20">
        <Row>
          <Col xl="10">
            {data.hero && (
              <div className="text-center text-lg-start">
                <p className="subtitle letter-spacing-4 mb-2 text-secondary text-shadow">
                  {data.hero.subTitle}
                </p>
                <h1 className="display-3 fw-bold text-shadow">{data.hero.title}</h1>
                <p className="subtitle letter-spacing-4 mb-2 text-secondary text-shadow">
                  {data.hero.subtitle2}
                </p>
              </div>
            )}
            <Button onClick={randomTickerSearch} disabled={!allStocks}>
              Random Ticker Search
            </Button>
          </Col>
        </Row>
      </Container>
    </section>
  )
}

export default HeroSection
