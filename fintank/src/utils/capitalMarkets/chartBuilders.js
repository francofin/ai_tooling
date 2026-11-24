import { FREQUENCY_KEYS } from "./chartOptions";
import { weeklyForDisplay } from "./downsample.mjs";

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
export const buildLineChart = ({ series, label, color }) => {
  // Long daily series are drawn weekly; see downsample.mjs. The commentary
  // reads the full series, so no figure on the page changes.
  const shown = weeklyForDisplay(series);
  return {
    labels: shown?.dates ?? [],
    datasets: [
      {
        label,
        data: shown?.value ?? [],
        borderColor: color,
        backgroundColor: color,
        borderWidth: 1.5,
        // No dot per point: hundreds to thousands of dots per chart were most
        // of the drawing cost. The hover tooltip still shows the nearest point.
        pointRadius: 0,
        pointHoverRadius: 3,
      },
    ],
  };
};

/** Pick one frequency out of an equity_markets[pack] object. */
export const selectFrequencySeries = (pack, frequency) =>
  pack?.[FREQUENCY_KEYS[frequency]] ?? null;

/** A series is drawable only if it has at least one point. */
export const hasSeriesData = (series) => Boolean(series?.value?.length);
