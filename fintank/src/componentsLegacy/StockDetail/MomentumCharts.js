import React from 'react';
import { Line } from 'react-chartjs-2';
import { Row, Col } from 'react-bootstrap';
import { useAvailableSeries } from '@hooks/useAvailableSeries';
import { SERIES_COLORS, lineDataset, baseOptions, asPercent, asRatio } from './chartTheme';

/**
 * Each panel is its own chart on its own axis. Returns, ratios and
 * return-to-risk share no scale, so combining them would mean a second y-axis
 * -- which makes the crossings between series meaningless.
 */
const PANELS = [
  {
    title: 'Rolling Returns',
    format: asPercent,
    series: [
      { key: '30_day_returns', label: '30-day return' },
      { key: '60_day_returns', label: '60-day return' },
    ],
  },
  {
    title: 'Up / Down Day Ratio',
    format: asRatio,
    series: [
      { key: 'up_down_days_30', label: '30-day ratio' },
      { key: 'up_down_days_60', label: '60-day ratio' },
    ],
  },
  {
    title: 'Return to Risk',
    format: asRatio,
    series: [
      { key: '30_day_return_to_risk', label: '30-day' },
      { key: '60_day_return_to_risk', label: '60-day' },
    ],
  },
  {
    title: 'Volatility',
    format: asPercent,
    series: [
      { key: '30_day_volatility', label: '30-day volatility' },
      { key: '60_day_volatility', label: '60-day volatility' },
    ],
  },
];

const MomentumPanel = ({ dates, series, panel }) => {
  const availableKeys = useAvailableSeries(series, panel.series.map((s) => s.key));
  const shown = panel.series.filter((s) => availableKeys.includes(s.key));

  if (shown.length === 0) return null;

  const data = {
    labels: dates,
    datasets: shown.map((s, i) => lineDataset(s.label, series[s.key], SERIES_COLORS[i])),
  };

  return (
    <Col lg="6" className="mb-4">
      <h6 className="mb-2">{panel.title}</h6>
      <div style={{ height: '240px' }}>
        <Line options={baseOptions({ valueFormat: panel.format })} data={data} />
      </div>
    </Col>
  );
};

const MomentumCharts = ({ dates, series }) => {
  const panels = PANELS.filter((panel) =>
    panel.series.some((s) => Array.isArray(series[s.key]) && series[s.key].some((v) => v !== null))
  );

  if (panels.length === 0) return null;

  return (
    <div className="text-block">
      <h4 className="mb-4">Momentum &amp; Risk</h4>
      <Row>
        {panels.map((panel) => (
          <MomentumPanel key={panel.title} dates={dates} series={series} panel={panel} />
        ))}
      </Row>
    </div>
  );
};

export default MomentumCharts;
