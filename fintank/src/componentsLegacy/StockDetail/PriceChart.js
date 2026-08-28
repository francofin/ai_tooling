import React, { useMemo } from 'react';
import { Line } from 'react-chartjs-2';
import { useAvailableSeries } from '@hooks/useAvailableSeries';
import {
  SERIES_COLORS,
  REFERENCE_COLOR,
  MAX_SERIES,
  lineDataset,
  baseOptions,
  asPrice,
} from './chartTheme';

// Short, medium, then long horizon -- the order the notebook plots them in.
// Capped at MAX_SERIES so the categorical palette is never cycled.
const MA_PRIORITY = [
  { key: '10_day_ma', label: '10-day MA' },
  { key: '50_day_ma', label: '50-day MA' },
  { key: '200_day_ma', label: '200-day MA' },
  { key: '20_day_ma', label: '20-day MA' },
];

const PriceChart = ({ dates, series }) => {
  const availableKeys = useAvailableSeries(series, MA_PRIORITY.map((m) => m.key));
  const shown = MA_PRIORITY.filter((m) => availableKeys.includes(m.key)).slice(0, MAX_SERIES);

  const data = useMemo(
    () => ({
      labels: dates,
      datasets: [
        lineDataset('Price', series.adjClose, REFERENCE_COLOR, { reference: true }),
        ...shown.map((ma, i) => lineDataset(ma.label, series[ma.key], SERIES_COLORS[i])),
      ],
    }),
    [dates, series, shown]
  );

  const options = useMemo(() => baseOptions({ valueFormat: asPrice }), []);

  return (
    <div className="text-block">
      <h4 className="mb-1">Price &amp; Moving Averages</h4>
      {shown.length < MA_PRIORITY.length && (
        <p className="text-muted text-sm mb-3">
          Showing {shown.length} of {MA_PRIORITY.length} moving averages — the rest have no data
          for this symbol yet.
        </p>
      )}
      <div style={{ height: '340px' }}>
        <Line options={options} data={data} />
      </div>
    </div>
  );
};

export default PriceChart;
