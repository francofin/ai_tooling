import { BarElement, Chart as ChartJS } from "chart.js";

// The capital-markets module registers the line/category/tooltip pieces once
// for the whole app; importing it here reuses that registration instead of
// repeating it. The old page ran its own ChartJS.register() call, making three
// separate registrations across the codebase.
import { indexLineOptions } from "@utils/capitalMarkets/chartOptions";

// Bars are only used by this page's risk decomposition, so the element is
// registered here rather than in the shared module.
ChartJS.register(BarElement);

export { indexLineOptions };

const percentTick = (value) => `${Number(value).toFixed(1)}%`;

/** Spreads and returns, where the y-axis reads as a percentage. */
export const percentLineOptions = {
  ...indexLineOptions,
  scales: {
    y: {
      ticks: { callback: percentTick },
    },
  },
};

/** Index level against the VIX: two series that share no scale. */
export const dualAxisOptions = {
  ...indexLineOptions,
  interaction: { mode: "index", intersect: false },
  scales: {
    y: {
      type: "linear",
      display: true,
      position: "left",
    },
    y1: {
      type: "linear",
      display: true,
      position: "right",
      grid: { drawOnChartArea: false },
    },
  },
};

/** Horizontal bars for contribution to volatility and period return. */
export const horizontalBarOptions = {
  indexAxis: "y",
  responsive: true,
  elements: { bar: { borderWidth: 2 } },
  plugins: {
    legend: { position: "bottom" },
    title: { display: false },
  },
  scales: {
    x: {
      ticks: { callback: percentTick },
    },
  },
};
