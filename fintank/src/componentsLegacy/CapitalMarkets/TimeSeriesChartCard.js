import React, { useMemo } from "react";
import { Col } from "react-bootstrap";
import { Line } from "react-chartjs-2";
import FrequencySelect from "./FrequencySelect";
import { buildLineChart } from "@utils/capitalMarkets/chartBuilders";
import { indexLineOptions } from "@utils/capitalMarkets/chartOptions";

/**
 * One titled chart: heading, explanatory copy, an optional frequency selector,
 * and the line itself. Replaces 33 hand-written copies of this markup.
 */
const TimeSeriesChartCard = ({
  id,
  title,
  blurb,
  label,
  color,
  series,
  frequency,
  onFrequencyChange,
}) => {
  const chart = useMemo(
    () => buildLineChart({ series, label, color }),
    [series, label, color]
  );

  return (
    <Col lg="6">
      <div>
        <h3 className="mb-3">{title}</h3>
        <p className="text-muted fw-light">{blurb}</p>
      </div>
      {onFrequencyChange && (
        <FrequencySelect
          id={`frequency-${id}`}
          value={frequency}
          onChange={onFrequencyChange}
        />
      )}
      <Line options={indexLineOptions} data={chart} height={100} width={200} />
    </Col>
  );
};

export default TimeSeriesChartCard;
