// src/pages/index.js
import React from "react"
import axios from "axios"
import data from "../data/index.json"
import HeroSection from "../componentsLegacy/Homepage/HeroSection"
import IndexReturnsSection from "../componentsLegacy/Homepage/IndexReturnsSection"
import IndexChartsSection from "../componentsLegacy/Homepage/IndexChartsSection"
import SectorPerformanceSection from "../componentsLegacy/Homepage/SectorPerformanceSection"
import MoversSection from "../componentsLegacy/Homepage/MoversSection"
import NewsSection from "../componentsLegacy/Homepage/NewsSection"
import JumbotronSection from "../componentsLegacy/Homepage/JumbotronSection"

const fetcher = async (url) => {
  const res = await axios.get(url)
  return res.data
}

export async function getServerSideProps() {
  const moverData = await fetcher(
    `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/gainers-losers/`
  )

  let responseNews = []
  try {
    const fmpRes = await axios.get(
      `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/get_articles/fmp`
    )
    responseNews = fmpRes.data ?? []
  } catch (_) {
    // news fetch failed — page renders with empty articles
  }

  return {
    props: {
      nav: { light: true, classes: "shadow", color: "white" },
      title: "Fintank",
      data,
      moverData,
      responseNews,
    },
  }
}

const Index = ({ moverData, responseNews }) => {
  const fmpArticles = Array.isArray(responseNews)
    ? responseNews
    : (responseNews?.data ?? [])
  const filteredArticles = fmpArticles.filter(
    (a) => a.site !== "newslanes" && a.image !== null
  )

  return (
    <React.Fragment>
      <HeroSection data={data} />
      <IndexReturnsSection data={data} />
      <IndexChartsSection />
      <SectorPerformanceSection />
      {moverData && <MoversSection moverData={moverData} data={data} />}
      <NewsSection articles={filteredArticles} data={data} />
      <JumbotronSection data={data} />
    </React.Fragment>
  )
}

export default Index
