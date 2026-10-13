import React from 'react';
import { Container, Row, Col } from 'react-bootstrap';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import StockHeader from '@componentsLegacy/StockDetail/StockHeader';
import PriceChart from '@componentsLegacy/StockDetail/PriceChart';
import MomentumCharts from '@componentsLegacy/StockDetail/MomentumCharts';
import StatementsSection from '@componentsLegacy/StockDetail/StatementsSection';
import SectorNews from '@componentsLegacy/StockDetail/SectorNews';
import QuoteCard from '@componentsLegacy/StockDetail/QuoteCard';
import { fetchProfile, fetchEtfProfile, fetchPrices } from '@utils/stockApi';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

export async function getServerSideProps({ params, res }) {
  const ticker = params.ticker;

  let profile;
  try {
    profile = await fetchProfile(ticker);
  } catch (error) {
    if (!error.isNotFound) throw error;

    // ETFs have no row in the long_profiles parquet /stock-profile/ reads, so
    // every fund 404s on this route even though /etf-data/ serves it fine.
    // Resolve against the ETF store before giving up: the ways into this route
    // are many (both search boxes, index movers, rankings, valuation tables,
    // the homepage hero, plus existing bookmarks), so redirecting here fixes
    // all of them at once rather than teaching each caller which route to pick.
    try {
      await fetchEtfProfile(ticker);
      return {
        redirect: {
          destination: `/etf-data/${encodeURIComponent(ticker)}`,
          permanent: false,
        },
      };
    } catch (etfError) {
      if (!etfError.isNotFound) throw etfError;
    }

    // Signal a missing symbol with a 404 status but render our own state.
    // `notFound: true` would hand off to the App Router's not-found path,
    // which currently throws inside AppProviders and surfaces as a 500.
    res.statusCode = 404;
    return { props: { nav: { light: true, classes: 'shadow', color: 'white' }, unknownSymbol: ticker } };
  }

  // Prices are secondary: a symbol with a profile but no price parquet should
  // still render its profile rather than fail the whole page.
  let prices = null;
  try {
    prices = await fetchPrices(ticker);
  } catch (error) {
    console.error(`[${ticker}] price series unavailable:`, error.message);
  }

  const dates = prices?.dates || [];

  return {
    props: {
      nav: { light: true, classes: 'shadow', color: 'white' },
      symbol: profile.symbol || ticker.toUpperCase(),
      profile,
      dates,
      series: prices?.series || null,
      asOfDate: dates.length ? dates[dates.length - 1] : null,
    },
  };
}

const UnknownSymbol = ({ ticker }) => (
  <section>
    <Container className="py-5 text-center">
      <Row>
        <Col lg="6" className="mx-auto">
          <h1 className="mb-3">Symbol not found</h1>
          <p className="text-muted">
            We don&apos;t have coverage for &ldquo;{ticker}&rdquo; yet.
          </p>
        </Col>
      </Row>
    </Container>
  </section>
);

const StockDetail = ({ symbol, profile, dates, series, asOfDate, unknownSymbol }) =>
  unknownSymbol ? (
    <UnknownSymbol ticker={unknownSymbol} />
  ) : (
    <section>
      <Container className="py-5">
        <Row>
          <Col lg="10" className="mx-auto">
            {/*
              Top region: header + price chart on the left, quote sidebar on the
              right. The wrapper carries the section divider the chart's own
              .text-block loses once it becomes :last-of-type in its column;
              pb-0 keeps the spacing what it was before the split.
            */}
            <div className="text-block pb-0">
              <Row>
                <Col lg={8}>
                  <StockHeader profile={profile} asOfDate={asOfDate} />

                  {/*
                    Below lg the columns stack, which would push the quote under
                    the chart. Render it here instead so it sits right after the
                    header. SWR dedupes the shared key, so this is one request.
                  */}
                  <div className="d-lg-none pt-4">
                    <QuoteCard symbol={symbol} currency={profile.currency} />
                  </div>

                  {series ? (
                    <PriceChart dates={dates} series={series} />
                  ) : (
                    <div className="text-block">
                      <p className="text-muted">No price history available for {symbol}.</p>
                    </div>
                  )}
                </Col>

                <Col lg={4} className="d-none d-lg-block">
                  {/* Clears the fixed navbar; same offset as IndexDetail/MoversPanel. */}
                  <div className="sticky-top" style={{ top: '100px' }}>
                    <QuoteCard symbol={symbol} currency={profile.currency} />
                  </div>
                </Col>
              </Row>
            </div>

            {series && <MomentumCharts dates={dates} series={series} />}

            <StatementsSection symbol={symbol} />
            <SectorNews sector={profile.sector} />
          </Col>
        </Row>
      </Container>
    </section>
  );

export default StockDetail;
