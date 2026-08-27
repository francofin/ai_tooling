import React, { useMemo } from 'react'
import dynamic from 'next/dynamic'
import { indicatorMeta } from '@utils/technicalSpec'

const ReactApexChart = dynamic(() => import('react-apexcharts'), { ssr: false })

const toEpoch = (date) => new Date(`${date}T00:00:00Z`).getTime()

export const OSCILLATOR_HEIGHT = 160

/**
 * One oscillator sub-panel, rendered entirely from the indicator's `plots`.
 *
 * `plots` is what keeps "kind drives rendering" honest: MACD's three series
 * against RSI's one would otherwise force a special case by name here, which
 * is the indicator-specific branching this rebuild exists to remove.
 *
 * Colors come from the metadata keyed by token, never from ApexCharts' default
 * positional palette: an indicator dropped via `warnings` on a short-history
 * symbol would otherwise shift every later series a slot, so the same
 * indicator would render a different color in different columns.
 */
const OscillatorChart = ({ symbol, token, name, entry, dates }) => {
  const meta = indicatorMeta[name]

  const series = useMemo(() => {
    const x = dates.map(toEpoch)
    return meta.plots
      .filter((plot) => Array.isArray(entry[plot.key]))
      .map((plot) => ({
        name: plot.label,
        type: plot.type,
        data: entry[plot.key].map((value, i) => ({ x: x[i], y: value })),
      }))
  }, [meta, entry, dates])

  const options = useMemo(
    () => ({
      chart: {
        id: `${symbol}:${token}`,
        group: `panel-${symbol}`,
        type: series.length > 1 ? 'line' : meta.plots[0].type,
        height: OSCILLATOR_HEIGHT,
        toolbar: { show: false },
        animations: { enabled: false },
        zoom: { enabled: false },
      },
      dataLabels: { enabled: false },
      colors: meta.plots.map((plot) => plot.color),
      stroke: { width: meta.plots.map((plot) => (plot.type === 'column' ? 0 : 2)) },
      grid: { padding: { left: 8, right: 8 } },
      xaxis: { type: 'datetime', labels: { show: false } },
      yaxis: {
        labels: {
          minWidth: 56,
          // ADL runs to 1e8; an unformatted label would widen the axis and
          // shift this sub-panel's plot area out of alignment with its peers.
          formatter: (v) => (v == null ? '' : Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v.toFixed(2)),
        },
        // Never anchor ADL at zero: full-history cumulation gives it a large
        // constant offset and a zero floor flattens the whole year.
        forceNiceScale: !meta.autoscale,
      },
      annotations: {
        yaxis: (entry.bands ?? []).map((band) => ({
          y: band,
          borderColor: '#c7ccd6',
          strokeDashArray: 4,
          label: { text: String(band), style: { fontSize: '10px' } },
        })),
      },
      legend: { show: series.length > 1, position: 'top', fontSize: '11px' },
      tooltip: { shared: true, x: { format: 'dd MMM yyyy' } },
    }),
    [symbol, token, meta, entry.bands, series.length],
  )

  return (
    <div role="img" aria-label={`${symbol} ${meta.label} chart`} className="mt-2">
      <div className="small text-muted">{`${meta.label} (${token})`}</div>
      <ReactApexChart options={options} series={series} height={OSCILLATOR_HEIGHT} />
    </div>
  )
}

export default OscillatorChart
