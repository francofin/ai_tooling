import React, { useCallback, useMemo, useState } from "react";
import { Container } from "react-bootstrap";
import SectionIntro from "./SectionIntro";
import ChartGrid from "./ChartGrid";
import TimeSeriesChartCard from "./TimeSeriesChartCard";
import equitySeries from "@data/capitalMarkets/equitySeries.json";
import {
  hasSeriesData,
  selectFrequencySeries,
} from "@utils/capitalMarkets/chartBuilders";
import { DEFAULT_FREQUENCY } from "@utils/capitalMarkets/chartOptions";

const EquitySection = ({ equityMarkets }) => {
  // One map keyed by chart id, rather than the 20 separate useState pairs the
  // old component declared.
  const [frequencies, setFrequencies] = useState({});

  const setFrequency = useCallback(
    (id, frequency) =>
      setFrequencies((current) => ({ ...current, [id]: frequency })),
    []
  );

  const cards = useMemo(
    () =>
      equitySeries
        .map((definition) => {
          const frequency = frequencies[definition.id] ?? DEFAULT_FREQUENCY;
          return {
            ...definition,
            frequency,
            series: selectFrequencySeries(
              equityMarkets?.[definition.packKey],
              frequency
            ),
          };
        })
        .filter(({ series }) => hasSeriesData(series)),
    [equityMarkets, frequencies]
  );

  return (
    <Container>
      <SectionIntro title="Index Cap and Style Spread Charts">
        {`Spread between Large, Small and Mid Cap as well as Style Spreads including Value and Growth.`}
      </SectionIntro>
      <ChartGrid>
        {cards.map((card) => (
          <TimeSeriesChartCard
            key={card.id}
            {...card}
            onFrequencyChange={(frequency) => setFrequency(card.id, frequency)}
          />
        ))}
      </ChartGrid>
    </Container>
  );
};

export default EquitySection;
