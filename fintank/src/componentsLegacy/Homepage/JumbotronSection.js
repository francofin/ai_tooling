import React from "react"
import { Container, Button } from "react-bootstrap"
import Image from "../CustomImage"
import { useStockNames } from "../../hooks/useStockNames"
import { useRouter } from "next/router"

const EXCHANGE_LIST = ["NASDAQ", "TSX", "NYSE", "CBOE"]

const JumbotronSection = ({ data }) => {
  const router = useRouter()
  const { data: stockNames } = useStockNames()
  const allStocks = stockNames?.stocks?.filter(
    (s) => EXCHANGE_LIST.includes(s.exchange_short_name)
  )

  const randomTickerSearch = () => {
    if (!allStocks || allStocks.length === 0) return
    const idx = Math.floor(Math.random() * allStocks.length)
    router.push(`/stock-data/${allStocks[idx].symbol}`)
  }

  if (!data.jumbotron) return null

  return (
    <section className="py-7 position-relative dark-overlay">
      <Image
        src={`/images/${data.jumbotron.img}`}
        alt=""
        className="bg-image"
        layout="fill"
      />
      <Container>
        <div className="overlay-content text-white py-lg-5">
          <h4 className="display-4 fw-bold text-serif text-shadow mb-5">
            {data.jumbotron.title}
          </h4>
          <Button onClick={randomTickerSearch} variant="light" disabled={!allStocks || allStocks.length === 0}>
            Discover A Company
          </Button>
        </div>
      </Container>
    </section>
  )
}

export default JumbotronSection
