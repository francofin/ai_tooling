import React from "react"
import axios from "axios"
import data from "../data/index.json"
import RichSwiper from "../componentsLegacy/RichSwiper"
import IndexReturnsSidePanel from "../componentsLegacy/Homepage/IndexReturnsSidePanel"
import IndexChartsSection from "../componentsLegacy/Homepage/IndexChartsSection"
import SectorPerformanceSection from "../componentsLegacy/Homepage/SectorPerformanceSection"
import MoversSection from "../componentsLegacy/Homepage/MoversSection"
import NewsSection from "../componentsLegacy/Homepage/NewsSection"
import JumbotronSection from "../componentsLegacy/Homepage/JumbotronSection"
// Shared with the profile rail's feed so both show the same set of articles.
import { filterDisplayableArticles } from "../utils/newsArticles"

const fetcher = async (url) => {
  const res = await axios.get(url)
  return res.data
}

export async function getServerSideProps() {
  let moverData = null
  try {
    moverData = await fetcher(
      `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/gainers-losers/`
    )
  } catch (_) {}

  let responseNews = []
  try {
    responseNews =
      (await fetcher(
        `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/get_articles/fmp`
      )) ?? []
  } catch (_) {}

  return {
    props: {
      nav: { dark: true, fixed: "false", color: "transparent" },
      noPaddingTop: true,
      headerClasses: "header-absolute",
      title: "Fintank",
      moverData,
      responseNews,
    },
  }
}

const Index = ({ moverData, responseNews }) => {
  const filteredArticles = filterDisplayableArticles(responseNews)

  return (
    <React.Fragment>
      <div style={{ position: "relative" }}>
        <RichSwiper
          className="multi-slider"
          data={data.swiper}
          perView={1}
          spaceBetween={0}
          centeredSlides
          loop
          speed={2500}
          autoplay={5000}
          effect="fade"
          parallax
          paginationClass="swiper-pagination-white"
          priority
        />
        <IndexReturnsSidePanel />
      </div>
      <IndexChartsSection />
      <SectorPerformanceSection />
      {moverData?.gainers && <MoversSection moverData={moverData} data={data} />}
      <NewsSection articles={filteredArticles} data={data} />
      <JumbotronSection data={data} />
    </React.Fragment>
  )
}

export default Index
