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
