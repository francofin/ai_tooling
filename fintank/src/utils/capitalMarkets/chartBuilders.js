import { FREQUENCY_KEYS } from "./chartOptions";

/**
 * Chart.js line config for one {dates, value} series from /economic-data/.
 *
 * Deliberately a pure function rather than the useCapitalMarketCharter /
 * useEquitySpreadCharter hooks it replaces. Those built the chart inside an
 * effect that also set the label and colour via setState, so the chart was
 * assembled from the *previous* render's label and colour, and the equity one
 * read a stale `selectedFrequency` -- switching the dropdown drew the
 * previously selected frequency. With no state there is nothing to be stale.
 */
export const buildLineChart = ({ series, label, color }) => ({
  labels: series?.dates ?? [],
  datasets: [
    {
      label,
      data: series?.value ?? [],
      borderColor: color,
      backgroundColor: color,
      pointRadius: 1,
    },
  ],
});

/** Pick one frequency out of an equity_markets[pack] object. */
export const selectFrequencySeries = (pack, frequency) =>
  pack?.[FREQUENCY_KEYS[frequency]] ?? null;

/** A series is drawable only if it has at least one point. */
export const hasSeriesData = (series) => Boolean(series?.value?.length);
