import React, { useState } from "react";
import axios from "axios";
import { Container, Row, Col, Button, Nav, Tab } from "react-bootstrap";
import { useRouter } from "next/router";

import Swiper from "@componentsLegacy/Swiper";
import EquitySection from "@componentsLegacy/CapitalMarkets/EquitySection";
import EconomicSection from "@componentsLegacy/CapitalMarkets/EconomicSection";
import LastUpdated from "@componentsLegacy/CapitalMarkets/LastUpdated";
import DataUnavailable from "@componentsLegacy/CapitalMarkets/DataUnavailable";

import { useHomeIndex } from "@hooks/useHomeIndex";
import { useStockNames } from "@hooks/useStockNames";

import data from "@data/index.json";
import tabData from "@data/searchTabs.json";

import "@utils/capitalMarkets/chartOptions"; // registers the Chart.js components

const [EQUITY_TAB, ECONOMIC_TAB] = tabData.marketSearchTabs.tabs.map(
  (tab) => tab.title
);

/**
 * Statically generated and revalidated hourly rather than server-rendered per
 * request: /economic-data/ is a ~460 KB gzipped blob rebuilt once a day by the
 * update_economic_data_daily Celery beat job, so rendering it on every visit
 * was pure repeat work. ISR also means that once one build has succeeded, a
 * later backend outage keeps serving the last good page -- the previous
 * getServerSideProps had no try/catch and turned any failure into a 500.
 */
export async function getStaticProps() {
  const props = {
    nav: { light: true, classes: "shadow", color: "white" },
    title: "Fintank",
  };

  try {
    const { data: payload } = await axios.get(
      `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/economic-data/`
    );

    return {
      props: {
        ...props,
        economic: payload.economic ?? null,
        equityMarkets: payload.equity_markets ?? null,
        lastUpdated: payload.last_updated ?? null,
      },
      revalidate: 3600,
    };
  } catch (error) {
    // Only reachable before a first successful build. Retry sooner than the
    // steady-state interval so the page recovers quickly.
    console.error("capital-markets: /economic-data/ fetch failed", error.message);

    return {
      props: {
        ...props,
        economic: null,
        equityMarkets: null,
        lastUpdated: null,
      },
      revalidate: 60,
    };
  }
}

const CapitalMarketIndicators = ({ economic, equityMarkets, lastUpdated }) => {
  const router = useRouter();
  const indexData = useHomeIndex();
  const { data: stockNames } = useStockNames();
  const [activeTab, setActiveTab] = useState(EQUITY_TAB);
  // Tabs opened so far. A tab's charts are built on its first visit and then
  // kept (hidden with d-none), so switching back is instant.
  const [visitedTabs, setVisitedTabs] = useState(() => new Set([EQUITY_TAB]));

  const selectTab = (tab) => {
    if (!tab) return;
    setActiveTab(tab);
    setVisitedTabs((current) =>
      current.has(tab) ? current : new Set(current).add(tab)
    );
  };

  // /index-performance/ answers {data: [...quotes]}; the slider needs the list.
  const indexQuotes = Array.isArray(indexData.data?.data)
    ? indexData.data.data
    : [];

  const searchableStocks = stockNames?.stocks?.filter(
    (stock) => stock.universe === "sp500" || stock.universe === "tsx"
  );

  const randomTickerSearch = () => {
    if (!searchableStocks?.length) return;
    const { symbol } =
      searchableStocks[Math.floor(Math.random() * searchableStocks.length)];
    router.push(`/stock-data/${symbol}`);
  };

  const hasData = Boolean(economic || equityMarkets);

  return (
    <React.Fragment>
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
                  <h1 className="display-3 fw-bold text-shadow">
                    Capital Market Indicators
                  </h1>
                </div>
              )}
              <Button
                onClick={randomTickerSearch}
                disabled={!searchableStocks?.length}
              >
                Random Ticker Search
              </Button>
            </Col>
          </Row>
        </Container>
      </section>

      {data.topBlocks && indexQuotes.length > 0 && (
        <section className="py-6 bg-gray-100">
          <Container>
            <div className="text-center pb-lg-4">
              <p className="subtitle text-primary">{data.topBlocks.subTitle}</p>
              <h2 className="mb-5">{data.topBlocks.title}</h2>
            </div>
            <Swiper
              className="swiper-container-mx-negative pt-3 pb-5"
              wrapperClasses="dark-overlay"
              indexReturns
              perView={1}
              md={2}
              lg={3}
              xl={4}
              data={indexQuotes}
              loop
              speed={1000}
              pagination
              autoplay={{ delay: 5000 }}
            />
          </Container>
        </section>
      )}

      <section className="py-0 bg-gray-100">
        <Container>
          <Tab.Container id="top-tabs" activeKey={activeTab}>
            <Nav
              variant="tabs"
              className="search-bar-nav-tabs"
              onSelect={selectTab}
            >
              {tabData.marketSearchTabs.tabs.map((tab, index) => (
                <Nav.Item
                  key={tab.title}
                  className={
                    index < tabData.marketSearchTabs.tabs.length - 1
                      ? "me-2"
                      : ""
                  }
                >
                  <Nav.Link eventKey={tab.title}>{tab.title}</Nav.Link>
                </Nav.Item>
              ))}
            </Nav>
            <section className="py-0 bg-white-100">
              {/* A tab's charts are created on its first visit only, then
                  hidden rather than destroyed when the user switches away. */}
              {!hasData && <DataUnavailable />}
              {hasData && visitedTabs.has(EQUITY_TAB) && (
                <div
                  className={
                    activeTab === EQUITY_TAB
                      ? "capital-markets-tab-pane"
                      : "d-none"
                  }
                >
                  <EquitySection equityMarkets={equityMarkets} />
                </div>
              )}
              {hasData && visitedTabs.has(ECONOMIC_TAB) && (
                <div
                  className={
                    activeTab === ECONOMIC_TAB
                      ? "capital-markets-tab-pane"
                      : "d-none"
                  }
                >
                  <EconomicSection economic={economic} />
                </div>
              )}
              {hasData && (
                <Container>
                  <LastUpdated timestamp={lastUpdated} />
                </Container>
              )}
            </section>
          </Tab.Container>
        </Container>
      </section>
    </React.Fragment>
  );
};

export default CapitalMarketIndicators;
