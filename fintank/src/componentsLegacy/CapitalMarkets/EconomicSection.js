import React, { useMemo } from "react";
import { Container } from "react-bootstrap";
import SectionIntro from "./SectionIntro";
import ChartGrid from "./ChartGrid";
import TimeSeriesChartCard from "./TimeSeriesChartCard";
import economicSeries from "@data/capitalMarkets/economicSeries.json";
import { hasSeriesData } from "@utils/capitalMarkets/chartBuilders";

const EconomicSection = ({ economic }) => {
  const cards = useMemo(
    () =>
      economicSeries
        .map((definition) => ({
          ...definition,
          series: economic?.[definition.dataKey],
        }))
        .filter(({ series }) => hasSeriesData(series)),
    [economic]
  );

  return (
    <Container>
      <SectionIntro title="Treasury Yields and Yield Spreads">
        {`Treasury yields of various maturities serve as indicators of market sentiment, inflation expectations, and economic outlooks. Investors, policymakers, and economists closely monitor these yields to gauge the health and direction of the economy and to make informed decisions about investments, lending rates, and monetary policy.`}
      </SectionIntro>
      <ChartGrid>
        {cards.map((card) => (
          <TimeSeriesChartCard key={card.id} {...card} />
        ))}
      </ChartGrid>
    </Container>
  );
};

export default EconomicSection;
