import React, { useMemo } from 'react'
import dynamic from 'next/dynamic'
import { indicatorMeta } from '@utils/technicalSpec'

const ReactApexChart = dynamic(() => import('react-apexcharts'), { ssr: false })

const toEpoch = (date) => new Date(`${date}T00:00:00Z`).getTime()

export const CHART_HEIGHT = 320

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
      colors: ['#26a69a', ...overlays.map(({ name }) => indicatorMeta[name].plots[0].color), '#d9dce3'],
      grid: { padding: { left: 8, right: 8 } },
      xaxis: { type: 'datetime', labels: { datetimeUTC: true } },
      yaxis: [
        {
          seriesName: symbol,
          labels: { minWidth: 56, formatter: (v) => (v == null ? '' : v.toFixed(2)) },
          title: { text: 'Price' },
        },
        ...overlays.map(() => ({ seriesName: symbol, show: false })),
        {
          seriesName: 'Volume',
          opposite: true,
          labels: {
            minWidth: 56,
            formatter: (v) => (v == null ? '' : `${(v / 1e6).toFixed(1)}M`),
          },
          title: { text: 'Volume' },
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
