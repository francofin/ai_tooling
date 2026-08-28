/**
 * Windowing helpers for the index charts.
 *
 * Chart.js is given a pre-sliced series rather than being asked to zoom, so the
 * axes rescale to whatever window is selected and the latest-level banner
 * reports the last point actually on screen.
 */

/**
 * Narrows a Chart.js data object to an inclusive index window.
 *
 * Every dataset is sliced with the labels so the price line and the volume bars
 * stay aligned — slicing one without the other silently shifts the series
 * against its dates.
 *
 * @param chartData  `{ labels, datasets }` as built by `useIndexCharter`
 * @param range      `[start, end]` inclusive label indices
 * @returns          a new data object; the input is not mutated
 */
export const sliceChartData = (chartData, range) => {
  const labels = chartData?.labels ?? []
  const datasets = chartData?.datasets ?? []
  if (!range) return { labels, datasets }

  const [start, end] = range
  // Guard against a stale range left over from a longer series: an out-of-order
  // or out-of-bounds window would silently produce an empty chart.
  const lo = Math.max(0, Math.min(start, labels.length - 1))
  const hi = Math.max(lo, Math.min(end, labels.length - 1))

  return {
    labels: labels.slice(lo, hi + 1),
    datasets: datasets.map((dataset) => ({
      ...dataset,
      data: (dataset.data ?? []).slice(lo, hi + 1),
    })),
  }
}

/**
 * The full window for a series of `length` points, as `[start, end]`.
 * An empty series still yields a valid degenerate range so the slider has bounds.
 */
export const fullRange = (length) => [0, Math.max(0, length - 1)]
