import React, { useMemo, useState } from 'react';
import { Form, Button, ButtonGroup, Badge, CloseButton, Spinner } from 'react-bootstrap';
import { Line, Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Tooltip,
  Legend,
} from 'chart.js';
import { useFinancialStatements } from '@hooks/useFinancialStatements';
import { STATEMENT_TYPES } from '@utils/stockApi';
import { SECTIONS, formatValue, scaled, unitOf } from '@utils/statementFields';
import { SERIES_COLORS, GRID_COLOR, TICK_COLOR, MAX_SERIES, lineDataset } from './chartTheme';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Tooltip, Legend);

const TYPE_LABELS = Object.fromEntries(STATEMENT_TYPES.map((t) => [t.key, t.label]));

// Grouped as "Income Statement · Revenue" etc. Ids carry the statement type
// because some keys (net_income, inventory, D&A) appear in more than one.
const FIELD_GROUPS = STATEMENT_TYPES.flatMap((type) =>
  (SECTIONS[type.key] || []).map(([section, fields]) => ({
    label: `${type.label} · ${section}`,
    fields: fields.map(([key, label]) => ({ id: `${type.key}:${key}`, type: type.key, key, label })),
  }))
);
const FIELDS = Object.fromEntries(FIELD_GROUPS.flatMap((g) => g.fields).map((f) => [f.id, f]));

const keyCounts = Object.values(FIELDS).reduce((counts, f) => {
  counts[f.key] = (counts[f.key] || 0) + 1;
  return counts;
}, {});
const seriesLabel = (field) =>
  keyCounts[field.key] > 1 ? `${field.label} (${TYPE_LABELS[field.type]})` : field.label;

const RANGES = [
  ['3Y', 12],
  ['5Y', 20],
  ['10Y', 40],
  ['All', Infinity],
];

const DEFAULT_FIELDS = ['income_statements:revenue', 'income_statements:net_income'];

// Dollar amounts share an axis only while they are within this factor of the
// largest series on it; anything smaller gets its own so it does not flatline.
const SHARED_AXIS_SPREAD = 10;

const UNIT_TITLES = {
  amount: (currency) => (currency ? `Amount (${currency})` : 'Amount'),
  percent: () => 'Margin (%)',
  perShare: (currency) => (currency ? `Per share (${currency})` : 'Per share'),
  shares: () => 'Shares',
};

const UNIT_TICKS = {
  amount: (v) => scaled(v),
  percent: (v) => `${Number(v).toFixed(0)}%`,
  perShare: (v) => Number(v).toFixed(2),
  shares: (v) => scaled(v),
};

const assignAxes = (series) => {
  const axes = [];
  // Largest first, so each amount axis is anchored by its biggest series.
  const ordered = [...series].sort((a, b) => b.maxAbs - a.maxAbs);
  ordered.forEach((s) => {
    const axis = axes.find(
      (a) =>
        a.unit === s.unit &&
        (s.unit !== 'amount' || s.maxAbs === 0 || a.maxAbs / s.maxAbs <= SHARED_AXIS_SPREAD)
    );
    if (axis) {
      axis.members.push(s);
    } else {
      axes.push({ id: `y${axes.length}`, unit: s.unit, maxAbs: s.maxAbs, members: [s] });
    }
  });
  return axes;
};

const StatementsChart = ({ symbol }) => {
  const [selected, setSelected] = useState(DEFAULT_FIELDS);
  const [chartType, setChartType] = useState('line');
  const [range, setRange] = useState('5Y');

  const wanted = new Set(selected.map((id) => FIELDS[id].type));
  // One hook per statement, enabled only when a selected field needs it. The
  // SWR keys match the table's, so a tab already opened costs no request.
  const statements = {
    income_statements: useFinancialStatements(symbol, 'income_statements', wanted.has('income_statements')),
    balance_sheet_statements: useFinancialStatements(
      symbol,
      'balance_sheet_statements',
      wanted.has('balance_sheet_statements')
    ),
    cash_flow_statements: useFinancialStatements(symbol, 'cash_flow_statements', wanted.has('cash_flow_statements')),
  };

  const isLoading = [...wanted].some((type) => statements[type].isLoading);
  const failed = [...wanted].filter((type) => statements[type].error);

  const { data, options, hasData } = useMemo(() => {
    const byDate = {};
    [...wanted].forEach((type) => {
      (statements[type].rows || []).forEach((row) => {
        byDate[row.date] = byDate[row.date] || { period: row.period, values: {} };
        byDate[row.date].values[type] = row;
      });
    });
    const limit = RANGES.find(([name]) => name === range)[1];
    const dates = Object.keys(byDate).sort().slice(-limit);

    const series = selected.map((id, i) => {
      const field = FIELDS[id];
      const raw = dates.map((date) => {
        const value = byDate[date].values[field.type]?.[field.key];
        const number = value === null || value === undefined ? null : Number(value);
        return Number.isFinite(number) ? number : null;
      });
      const unit = unitOf(field.key);
      // Ratios are stored as fractions; the axis reads in percent.
      const plotted = raw.map((v) => (v !== null && unit === 'percent' ? v * 100 : v));
      const maxAbs = Math.max(0, ...plotted.filter((v) => v !== null).map(Math.abs));
      return { id, field, raw, plotted, unit, maxAbs, color: SERIES_COLORS[i] };
    });

    const axes = assignAxes(series);
    const axisOf = Object.fromEntries(axes.flatMap((a) => a.members.map((m) => [m.id, a.id])));
    const currency = [...wanted]
      .flatMap((type) => statements[type].rows || [])
      .find((row) => row.reported_currency)?.reported_currency;

    const datasets = series.map((s) => {
      const base =
        chartType === 'bar'
          ? { label: seriesLabel(s.field), data: s.plotted, backgroundColor: s.color, borderColor: s.color }
          : { ...lineDataset(seriesLabel(s.field), s.plotted, s.color), pointRadius: 2 };
      return { ...base, yAxisID: axisOf[s.id], rawValues: s.raw, fieldKey: s.field.key };
    });

    const scales = {
      x: {
        grid: { display: false },
        ticks: { color: TICK_COLOR, maxTicksLimit: 10, autoSkip: true },
      },
    };
    axes.forEach((axis, i) => {
      // A single-series axis takes that series' colour so it is clear which
      // line it measures; shared axes stay neutral.
      const color = axis.members.length === 1 ? axis.members[0].color : TICK_COLOR;
      scales[axis.id] = {
        type: 'linear',
        position: i % 2 === 0 ? 'left' : 'right',
        beginAtZero: chartType === 'bar',
        grid: i === 0 ? { color: GRID_COLOR, drawBorder: false } : { drawOnChartArea: false },
        ticks: { color, callback: UNIT_TICKS[axis.unit] },
        title: { display: true, text: UNIT_TITLES[axis.unit](currency), color },
      };
    });

    return {
      hasData: series.some((s) => s.raw.some((v) => v !== null)),
      data: { labels: dates, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            position: 'bottom',
            labels: { boxWidth: 12, boxHeight: chartType === 'bar' ? 12 : 2, color: TICK_COLOR },
          },
          tooltip: {
            callbacks: {
              title: (items) => {
                const date = items[0]?.label;
                const period = byDate[date]?.period;
                return period ? `${date} (${period})` : date;
              },
              label: (ctx) =>
                `${ctx.dataset.label}: ${formatValue(ctx.dataset.rawValues[ctx.dataIndex], ctx.dataset.fieldKey)}`,
            },
          },
        },
        scales,
      },
    };
    // `statements` is rebuilt every render; its rows are what actually change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    selected,
    chartType,
    range,
    statements.income_statements.rows,
    statements.balance_sheet_statements.rows,
    statements.cash_flow_statements.rows,
  ]);

  const full = selected.length >= MAX_SERIES;
  const addField = (event) => {
    const id = event.target.value;
    if (id && !selected.includes(id) && !full) setSelected([...selected, id]);
  };
  const removeField = (id) => setSelected(selected.filter((s) => s !== id));

  const ChartComponent = chartType === 'bar' ? Bar : Line;

  return (
    <div className="mt-4">
      <h5 className="mb-3">Chart the statements</h5>

      <div className="d-flex flex-wrap gap-2 align-items-center mb-2">
        <Form.Select
          size="sm"
          style={{ maxWidth: '340px' }}
          value=""
          onChange={addField}
          disabled={full}
          aria-label="Add a field to the chart"
        >
          <option value="">
            {full ? `Up to ${MAX_SERIES} fields; remove one to add another` : 'Add a field…'}
          </option>
          {FIELD_GROUPS.map((group) => (
            <optgroup key={group.label} label={group.label}>
              {group.fields.map((field) => (
                <option key={field.id} value={field.id} disabled={selected.includes(field.id)}>
                  {field.label}
                </option>
              ))}
            </optgroup>
          ))}
        </Form.Select>

        <ButtonGroup size="sm" aria-label="Chart type">
          {['line', 'bar'].map((type) => (
            <Button
              key={type}
              variant={chartType === type ? 'primary' : 'outline-primary'}
              onClick={() => setChartType(type)}
            >
              {type === 'line' ? 'Line' : 'Bar'}
            </Button>
          ))}
        </ButtonGroup>

        <ButtonGroup size="sm" aria-label="Period range">
          {RANGES.map(([name]) => (
            <Button
              key={name}
              variant={range === name ? 'secondary' : 'outline-secondary'}
              onClick={() => setRange(name)}
            >
              {name}
            </Button>
          ))}
        </ButtonGroup>

        {isLoading && <Spinner animation="border" size="sm" />}
      </div>

      <div className="d-flex flex-wrap gap-2 mb-3">
        {selected.map((id, i) => (
          <Badge
            key={id}
            bg="light"
            text="dark"
            className="d-inline-flex align-items-center gap-2 border fw-normal"
          >
            <span
              style={{ width: 10, height: 10, borderRadius: 2, background: SERIES_COLORS[i] }}
              aria-hidden="true"
            />
            {seriesLabel(FIELDS[id])}
            <CloseButton
              style={{ fontSize: '0.6rem' }}
              aria-label={`Remove ${seriesLabel(FIELDS[id])}`}
              onClick={() => removeField(id)}
            />
          </Badge>
        ))}
      </div>

      {failed.length > 0 && (
        <p className="text-muted text-sm">
          Could not load {failed.map((type) => TYPE_LABELS[type].toLowerCase()).join(' and ')} for{' '}
          {symbol}.
        </p>
      )}

      {selected.length === 0 ? (
        <p className="text-muted">Add a field to start charting.</p>
      ) : hasData ? (
        <div style={{ height: '360px' }}>
          <ChartComponent options={options} data={data} />
        </div>
      ) : (
        !isLoading && <p className="text-muted">No data for the selected fields.</p>
      )}
    </div>
  );
};

export default StatementsChart;
