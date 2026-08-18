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
import EtfHeader from '@componentsLegacy/StockDetail/EtfHeader';
import PriceChart from '@componentsLegacy/StockDetail/PriceChart';
import MomentumCharts from '@componentsLegacy/StockDetail/MomentumCharts';
import SectorNews from '@componentsLegacy/StockDetail/SectorNews';
import { fetchEtfProfile, fetchPrices } from '@utils/stockApi';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

export async function getServerSideProps({ params, res }) {
  const ticker = params.ticker;

  let profile;
  try {
    profile = await fetchEtfProfile(ticker);
  } catch (error) {
    if (!error.isNotFound) throw error;
    // Mirrors stock-data/[ticker].js: 404 the status but render our own state.
    // `notFound: true` hands off to the App Router's not-found path, which
    // throws inside AppProviders and surfaces as a 500.
    res.statusCode = 404;
    return { props: { nav: { light: true, classes: 'shadow', color: 'white' }, unknownSymbol: ticker } };
  }

  // Prices are secondary: a fund with a profile but no price parquet should
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
          <h1 className="mb-3">Fund not found</h1>
          <p className="text-muted">
            We don&apos;t have coverage for &ldquo;{ticker}&rdquo; yet.
          </p>
        </Col>
      </Row>
    </Container>
  </section>
);

/**
 * Holdings and sector/geographic allocation are deliberately absent: no backend
 * endpoint serves ETF constituents today, and FMP returns them empty for a
 * chunk of funds anyway (RQP.TO is a held-to-maturity bond fund reporting
 * holdingsCount 0). Price history and fund facts are the panels that hold up
 * across the whole ETF universe, so those are what this page commits to.
 *
 * StatementsSection is omitted on purpose too -- VALID_UNIVERSES has no 'etfs'
 * entry, so financial statements 404 for every fund.
 */
const EtfDetail = ({ symbol, profile, dates, series, asOfDate, unknownSymbol }) =>
  unknownSymbol ? (
    <UnknownSymbol ticker={unknownSymbol} />
  ) : (
    <section>
      <Container className="py-5">
        <Row>
          <Col lg="10" className="mx-auto">
            <EtfHeader profile={profile} asOfDate={asOfDate} />

            {series ? (
              <>
                <PriceChart dates={dates} series={series} />
                <MomentumCharts dates={dates} series={series} />
              </>
            ) : (
              <div className="text-block">
                <p className="text-muted">No price history available for {symbol}.</p>
              </div>
            )}

            <SectorNews sector={profile.sector} />
          </Col>
        </Row>
      </Container>
    </section>
  );

export default EtfDetail;
