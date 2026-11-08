/**
 * Pure Chart.js config builders for the index detail page.
 *
 * Every one of these replaces a stateful hook (useMetricCharts,
 * useSingleMetricCharts, useCovarChart, useVixChart). Those built their chart
 * inside an effect that also set the series via setState, so each chart was
 * assembled from the previous render's data -- changing the frequency drew the
 * frequency before it. They also called setChartCreated(true) unconditionally,
 * so a section unhid and rendered an empty canvas before any data arrived.
 * With no state there is nothing to be stale, and callers gate on the data.
 */

export const SERIES_COLORS = {
  base: "rgb(53, 162, 235)",
  peer: "rgb(255, 99, 132)",
  accent: "rgb(75, 192, 120)",
  neutral: "rgb(148, 163, 184)",
};

/** One line: a spread, a beta, or any single series. */
export const buildLineChart = ({ dates, values, label, color = SERIES_COLORS.base }) => ({
  labels: dates ?? [],
  datasets: [
    {
      label,
      data: values ?? [],
      borderColor: color,
      backgroundColor: color,
      pointRadius: 0,
      borderWidth: 2,
      spanGaps: true,
    },
  ],
});

/** Two lines on one axis: this index and its comparison, same units. */
export const buildPairChart = ({ dates, base, peer, baseLabel, peerLabel }) => ({
  labels: dates ?? [],
  datasets: [
    {
      label: baseLabel,
      data: base ?? [],
      borderColor: SERIES_COLORS.base,
      backgroundColor: SERIES_COLORS.base,
      pointRadius: 0,
      borderWidth: 2,
      spanGaps: true,
    },
    {
      label: peerLabel,
      data: peer ?? [],
      borderColor: SERIES_COLORS.peer,
      backgroundColor: SERIES_COLORS.peer,
      pointRadius: 0,
      borderWidth: 2,
      spanGaps: true,
    },
  ],
});

/** Two lines, two axes: index level against the VIX, which share no scale. */
export const buildDualAxisChart = ({ dates, base, peer, baseLabel, peerLabel }) => ({
  labels: dates ?? [],
  datasets: [
    {
      label: baseLabel,
      data: base ?? [],
      borderColor: SERIES_COLORS.base,
      backgroundColor: SERIES_COLORS.base,
      pointRadius: 0,
      borderWidth: 2,
      spanGaps: true,
      yAxisID: "y",
    },
    {
      label: peerLabel,
      data: peer ?? [],
      borderColor: SERIES_COLORS.peer,
      backgroundColor: SERIES_COLORS.peer,
      pointRadius: 0,
      borderWidth: 2,
      spanGaps: true,
      yAxisID: "y1",
    },
  ],
});

/** Price with whichever moving averages the payload carries. */
export const buildPriceChart = ({ dates, price, overlays = [], priceLabel }) => ({
  labels: dates ?? [],
  datasets: [
    {
      label: priceLabel,
      data: price ?? [],
      borderColor: SERIES_COLORS.base,
      backgroundColor: SERIES_COLORS.base,
      pointRadius: 0,
      borderWidth: 2,
      spanGaps: true,
    },
    ...overlays.map(({ label, values, color }) => ({
      label,
      data: values ?? [],
      borderColor: color,
      backgroundColor: color,
      pointRadius: 0,
      borderWidth: 1,
      borderDash: [4, 4],
      spanGaps: true,
    })),
  ],
});

/** Horizontal bars for the risk decomposition. */
export const buildBarChart = ({ labels, values, label, color }) => ({
  labels: labels ?? [],
  datasets: [
    {
      label,
      data: values ?? [],
      borderColor: color,
      backgroundColor: color,
      borderWidth: 1,
    },
  ],
});

/** A series is drawable only once it holds at least one real number. */
export const hasValues = (values) =>
  Array.isArray(values) && values.some((value) => value !== null && value !== undefined);

/** The payload is sparse, so anything that is not a real number is not a value. */
const toFiniteNumber = (value) => {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

/**
 * Median of a series, ignoring gaps. Null when the series holds no numbers.
 *
 * The median rather than the mean, because one bad print in a sparse series
 * should not move the typical level the scale decision is made from.
 */
export const finiteMedian = (values) => {
  if (!Array.isArray(values)) return null;
  const numbers = values
    .map(toFiniteNumber)
    .filter((value) => value !== null)
    .sort((a, b) => a - b);
  if (numbers.length === 0) return null;
  const middle = Math.floor(numbers.length / 2);
  return numbers.length % 2 === 0
    ? (numbers[middle - 1] + numbers[middle]) / 2
    : numbers[middle];
};

const DEFAULT_SCALE_GAP = 4;

/**
 * Whether two same-unit series are too far apart in level to share one y-axis.
 *
 * An index in the thousands plotted against the VIX in the teens flattens the
 * VIX onto the baseline, which is how the moving-average tab used to read for
 * the volatility peer. Comparing typical levels rather than naming a symbol
 * keeps any future low-level peer working, and keeps genuinely comparable
 * indexes (S&P 500 against the Nasdaq) on one axis so the chart stays honest.
 *
 * Returns false whenever the question cannot be answered -- an empty or
 * all-null series, or a median of zero -- so the shared axis stays the default.
 */
export const needsDualAxis = (base, peer, { threshold = DEFAULT_SCALE_GAP } = {}) => {
  const baseMedian = finiteMedian(base);
  const peerMedian = finiteMedian(peer);
  if (baseMedian === null || peerMedian === null) return false;
  if (baseMedian === 0 || peerMedian === 0) return false;

  const limit =
    Number.isFinite(threshold) && threshold > 0 ? threshold : DEFAULT_SCALE_GAP;
  const ratio = Math.abs(baseMedian / peerMedian);
  if (!Number.isFinite(ratio) || ratio === 0) return false;

  // Magnitude, so the answer does not depend on which series came first.
  return Math.max(ratio, 1 / ratio) > limit;
};
