import React, { useMemo } from 'react'
import dynamic from 'next/dynamic'
import { indicatorMeta } from '@utils/technicalSpec'

const ReactApexChart = dynamic(() => import('react-apexcharts'), { ssr: false })

const toEpoch = (date) => new Date(`${date}T00:00:00Z`).getTime()

export const CHART_HEIGHT = 320

/** hex '#rrggbb' lightened toward white by `amount` (0..1). */
const lighten = (hex, amount) => {
  const n = parseInt(hex.slice(1), 16)
  const mix = (channel) => Math.round(channel + (255 - channel) * amount)
  const r = mix((n >> 16) & 0xff)
  const g = mix((n >> 8) & 0xff)
  const b = mix(n & 0xff)
  return `#${[r, g, b].map((c) => c.toString(16).padStart(2, '0')).join('')}`
}

const SHADE_STEP = 0.28
const MAX_SHADE = 0.7

/**
 * One color per overlay, so two instances of the same indicator (SMA(50)
 * against SMA(200)) don't draw as two indistinguishable lines -- the whole
 * reason multi-instance overlays exist ("plotting SMA(50) against SMA(200)
 * is the main point of that control").
 *
 * The shade for a token is its rank by period among its *own name's*
 * currently-rendered siblings -- not its position in `overlays` (which also
 * holds every other overlay name) and not an index into the pre-filter
 * spec. Ranking by each token's own period keeps a token's color stable
 * when `warnings` drops a longer-period sibling on a short-history symbol:
 * the backend only ever drops the *longer* window an instance can't cover,
 * so a surviving shorter-period token's rank among whatever siblings remain
 * never changes, only the removed token's color disappears with it.
 */
const overlayColors = (overlays) => {
  const byName = {}
  overlays.forEach(({ name, token }) => {
    if (!byName[name]) byName[name] = []
    byName[name].push(token)
  })

  const ordinals = new Map()
  Object.values(byName).forEach((tokens) => {
    tokens
      .slice()
      .sort((a, b) => Number(a.split(':')[1]) - Number(b.split(':')[1]))
      .forEach((token, ordinal) => ordinals.set(token, ordinal))
  })

  return overlays.map(({ token, name }) => {
    const base = indicatorMeta[name].plots[0].color
    const ordinal = ordinals.get(token) ?? 0
    return ordinal === 0 ? base : lighten(base, Math.min(ordinal * SHADE_STEP, MAX_SHADE))
  })
}

/**
 * Candlesticks, volume on a second axis, and every overlay indicator.
 *
 * `chart.id` is mandatory, not decorative -- see the table in the plan.
 */
const PriceChart = ({ symbol, dates, candle, volume, averageVolume, overlays }) => {
  const series = useMemo(() => {
    const x = dates.map(toEpoch)
    return [
      {
        name: symbol,
        type: 'candlestick',
        data: candle.map((point, i) => ({ x: x[i], y: point.y })),
      },
      ...overlays.map(({ token, name, series: values }) => ({
        name: `${indicatorMeta[name].label} (${token})`,
        type: 'line',
        data: values.map((value, i) => ({ x: x[i], y: value })),
      })),
      {
        name: 'Volume',
        type: 'column',
        data: volume.map((point, i) => ({ x: x[i], y: point.y })),
      },
    ]
  }, [symbol, dates, candle, volume, overlays])

  const options = useMemo(
    () => ({
      chart: {
        id: `${symbol}:price`,
        group: `panel-${symbol}`,
        type: 'line',
        height: CHART_HEIGHT,
        toolbar: { show: false },
        animations: { enabled: false },
        zoom: { enabled: false },
      },
      dataLabels: { enabled: false },
      stroke: { width: [1, ...overlays.map(() => 2), 0], curve: 'straight' },
      colors: ['#26a69a', ...overlayColors(overlays), '#d9dce3'],
      // left is 8 - 10, not a typo. Dropping the axis titles and hiding the
      // volume axis below (see yaxis) removes the *variable* part of the
      // grid-rect mismatch with the oscillator sub-panels, but one fixed 10px
      // remains: node_modules/apexcharts/src/modules/dimensions/YAxis.js
      // getTotalYAxisWidth() adds a flat 10px to every visible label's width
      // whenever a chart's own `yaxis` array has more than one entry
      // (`w.globals.yAxisScale.length > 1`). This chart's array always has
      // >= 2 entries -- price + volume, even with zero overlays -- so that
      // 10px always applies here; OscillatorChart passes a single object
      // (array length 1), so it never applies there. It's a fixed constant,
      // not a per-overlay one -- adding overlays only adds more *hidden*
      // entries, which contribute 0 width and don't change this count.
      // Because getTotalYAxisWidth() feeds directly into this chart's
      // translateX (left edge of the grid) while the grid's *right* edge is
      // independent of it (dimensions/Dimensions.js: translateX gains the
      // total axis width, gridWidth loses the same total, so it cancels out
      // of translateX + gridWidth), taking exactly 10px off grid.padding.left
      // -- and only left, right is untouched at 8 to match the oscillators --
      // cancels this residual and re-equalizes both the left edge and, by
      // that cancellation, the width of the two grid rects at every index,
      // not just at the first candle.
      grid: { padding: { left: -2, right: 8 } },
      xaxis: { type: 'datetime', labels: { datetimeUTC: true } },
      yaxis: [
        {
          seriesName: symbol,
          // No `title` here on purpose. A left-axis title adds real pixel
          // width (node_modules/apexcharts/src/modules/dimensions/YAxis.js
          // getyAxisTitleCoords/getTotalYAxisWidth) that the oscillator
          // sub-panels below never carry, which used to push this chart's
          // grid rect start further right than theirs and defeat the
          // crosshair sync grid.padding/minWidth are supposed to guarantee.
          labels: { minWidth: 56, formatter: (v) => (v == null ? '' : v.toFixed(2)) },
        },
        ...overlays.map(() => ({ seriesName: symbol, show: false })),
        {
          // Hidden, not just untitled: an opposite axis reserves its own
          // width via getTotalYAxisWidth even with no title, and oscillator
          // sub-panels never carry a right-side axis at all. Volume only
          // needs its own *scale* (to fit bars under the candles), not a
          // readable number -- so the axis is fully hidden and the bars
          // still render, scaled, without reserving any right-side width.
          seriesName: 'Volume',
          opposite: true,
          show: false,
          max: averageVolume ? averageVolume * 6 : undefined,
        },
      ],
      legend: { show: true, position: 'top', fontSize: '11px' },
      tooltip: { shared: true, x: { format: 'dd MMM yyyy' } },
    }),
    [symbol, overlays, averageVolume],
  )

  return (
    <div role="img" aria-label={`${symbol} price and volume chart`}>
      <ReactApexChart options={options} series={series} height={CHART_HEIGHT} />
    </div>
  )
}

export default PriceChart
