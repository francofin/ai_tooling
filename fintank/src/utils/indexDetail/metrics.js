/**
 * The metric catalogue for the index detail page.
 *
 * Every option carries a stable `value` that matches a backend metric key, with
 * the human string kept alongside as `label`. The hooks this replaces switched
 * on the display text ("120 Day Moving Average"), which is how the "60 Day
 * Return Spread" branch ended up assigning `day_30_return_spread` -- the page
 * showed 30-day data under a 60-day heading. A key mismatch here is a missing
 * chart, not a silently wrong one.
 */

export const METRICS = [
  {
    id: "moving_average",
    label: "Moving Averages",
    family: "moving_average",
    shape: "pair",
    blurb:
      "Moving averages lag, since they depend on past prices, but they show the trend of buying or selling pressure. A shorter average tracks the near-term trend; a longer one takes in far more history and is better suited to judging long-run support and resistance.",
    frequencies: [
      { value: "ma_10", label: "10 Day" },
      { value: "ma_20", label: "20 Day" },
      { value: "ma_50", label: "50 Day" },
      { value: "ma_120", label: "120 Day" },
      { value: "ma_200", label: "200 Day" },
    ],
  },
  {
    id: "return_spread",
    label: "Return Differential",
    family: "return_spread",
    shape: "spread",
    blurb:
      "The spread between the two indexes' trailing returns. Beyond marking support and resistance, relative performance of this kind is widely used by institutional investors to steer allocation decisions.",
    frequencies: [
      { value: "ret_30", label: "30 Day" },
      { value: "ret_60", label: "60 Day" },
      { value: "ret_90", label: "90 Day" },
      { value: "ret_120", label: "120 Day" },
      { value: "ret_1y", label: "1 Year" },
      { value: "ret_3y", label: "3 Year" },
    ],
  },
  {
    id: "beta",
    label: "Rolling Beta",
    family: "beta",
    shape: "single",
    blurb:
      "Beta measures how much this index moves with the comparison index. A beta of 1 means the two move point for point; below 1 means it moves less than the comparison, above 1 means it amplifies it. This is systematic risk measured against the peer rather than against a domestic market.",
    frequencies: [
      { value: "beta_30", label: "30 Day" },
      { value: "beta_60", label: "60 Day" },
      { value: "beta_90", label: "90 Day" },
      { value: "beta_120", label: "120 Day" },
      { value: "beta_1y", label: "1 Year" },
    ],
  },
  {
    id: "volatility_spread",
    label: "Volatility Spread",
    family: "volatility_spread",
    shape: "spread",
    blurb:
      "Annualised rolling volatility of this index less the comparison. Set against a foreign market or a different size band, the gap indicates how much more or less risk the index and its holdings carry than the peer.",
    frequencies: [
      { value: "vol_30", label: "30 Day" },
      { value: "vol_60", label: "60 Day" },
      { value: "vol_90", label: "90 Day" },
      { value: "vol_120", label: "120 Day" },
      { value: "vol_1y", label: "1 Year" },
      { value: "vol_3y", label: "3 Year" },
    ],
  },
  {
    id: "return_to_risk_spread",
    label: "Return to Risk",
    family: "return_to_risk_spread",
    shape: "spread",
    blurb:
      "Return per unit of risk, this index less the comparison, with volatility annualised. A positive spread means the index delivered more return for the risk taken than the peer did over the same window.",
    frequencies: [
      { value: "rr_30", label: "30 Day" },
      { value: "rr_60", label: "60 Day" },
      { value: "rr_90", label: "90 Day" },
      { value: "rr_120", label: "120 Day" },
      { value: "rr_1y", label: "1 Year" },
      { value: "rr_3y", label: "3 Year" },
    ],
  },
];

export const DEFAULT_METRIC_ID = METRICS[0].id;

export const getMetric = (metricId) =>
  METRICS.find((metric) => metric.id === metricId) ?? METRICS[0];

/**
 * Frequencies the payload actually carries. A proxy ETF with a short history
 * has no 3-year columns, so the option disappears rather than drawing an empty
 * chart -- the same reasoning as the backend omitting the column.
 */
export const availableFrequencies = (metric, metrics) => {
  const family = metrics?.[metric.family];
  if (!family) return [];
  return metric.frequencies.filter((option) => family[option.value]);
};

/** Percent-formatted metrics; beta and price levels are plain numbers. */
export const isPercentMetric = (metric) =>
  metric.family === "return_spread" || metric.family === "volatility_spread";
