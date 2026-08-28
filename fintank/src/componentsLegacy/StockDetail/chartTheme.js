/**
 * Shared chart styling for the stock detail page.
 *
 * The four series colors are validated as a categorical set (adjacent-pair CVD
 * separation, normal-vision separation, and >= 3:1 contrast on a light surface),
 * so they must be assigned in this fixed order and never cycled. The price line
 * is deliberately not one of them -- it is the reference series, drawn in ink so
 * the moving averages read as annotations against it.
 */
export const SERIES_COLORS = ['#2a78d6', '#eb6834', '#4a3aa7', '#e34948'];
export const REFERENCE_COLOR = '#0b0b0b';
export const GRID_COLOR = 'rgba(11, 11, 11, 0.08)';
export const TICK_COLOR = '#52514e';

export const MAX_SERIES = SERIES_COLORS.length;

export const lineDataset = (label, data, color, { reference = false } = {}) => ({
  label,
  data,
  borderColor: color,
  backgroundColor: color,
  borderWidth: reference ? 2.5 : 2,
  pointRadius: 0,
  pointHoverRadius: 4,
  tension: 0.1,
  spanGaps: true,
});

export const baseOptions = ({ valueFormat = (v) => v, zeroLine = null } = {}) => ({
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index', intersect: false },
  plugins: {
    legend: {
      position: 'bottom',
      labels: { boxWidth: 12, boxHeight: 2, usePointStyle: false, color: TICK_COLOR },
    },
    tooltip: {
      callbacks: {
        label: (ctx) => `${ctx.dataset.label}: ${valueFormat(ctx.parsed.y)}`,
      },
    },
  },
  scales: {
    x: {
      grid: { display: false },
      ticks: { color: TICK_COLOR, maxTicksLimit: 8, autoSkip: true },
    },
    y: {
      grid: { color: GRID_COLOR, drawBorder: false },
      ticks: { color: TICK_COLOR, callback: valueFormat },
      ...(zeroLine !== null ? { suggestedMin: zeroLine } : {}),
    },
  },
});

export const asPercent = (v) => (v === null || v === undefined ? '' : `${(v * 100).toFixed(1)}%`);
export const asRatio = (v) => (v === null || v === undefined ? '' : v.toFixed(2));
export const asPrice = (v) => (v === null || v === undefined ? '' : `$${v.toFixed(2)}`);
