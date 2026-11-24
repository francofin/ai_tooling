import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from "chart.js";

// Registered once here and imported for its side effect. The old EquityCharts /
// EconomicCharts each ran their own identical ChartJS.register() call.
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

export const indexLineOptions = {
  responsive: true,
  plugins: {
    legend: {
      position: "bottom",
    },
    title: {
      display: false,
      text: "Time Series Data",
    },
  },
  // Animating every point of every chart on each tab switch froze the page;
  // the tab content fades in with CSS instead (.capital-markets-tab-pane).
  animation: false,
  interaction: {
    mode: "index",
    intersect: false,
  },
};

// Label shown in the dropdown -> key on an equity_markets[pack] object.
export const FREQUENCY_KEYS = {
  Quarterly: "quarterly",
  Yearly: "yearly",
  "Three Year": "threeyear",
};

export const frequencies = Object.keys(FREQUENCY_KEYS).map((value) => ({
  value,
  label: value,
}));

export const DEFAULT_FREQUENCY = frequencies[0].value;
