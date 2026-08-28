import React, { useMemo } from "react"
import dynamic from "next/dynamic"
import { Spinner } from "react-bootstrap"
import {
  fmtPrice,
  fmtPercent,
  fmtTimestamp,
  quoteDetailRows,
} from "../../utils/quoteFormat"
import { toNumber, tileSizer, bandColor } from "../../utils/heatMapScale"

// ApexCharts reaches for `window` at import time, so it can only load client-side.
// Same treatment as the homepage treemap in `Homepage/MoversSection.js`.
const ReactApexChart = dynamic(() => import("react-apexcharts"), { ssr: false })

/**
 * Renders the same hover card the markets grid shows, built from the quote the
 * tile was created with. Apex hands back only the point index, so the quotes are
 * carried alongside the series and looked up by position.
 */
const tooltipMarkup = (quote, change) => {
  const changeColor = change > 0 ? "#4ade80" : change < 0 ? "#f87171" : "#9ca3af"

  const rows = quoteDetailRows(quote)
    .map(
      ([label, value]) => `
        <div style="display:flex;justify-content:space-between;gap:1.25rem">
          <span style="opacity:.6">${label}</span>
          <span>${value}</span>
        </div>`
    )
    .join("")

  return `
    <div style="padding:.65rem .8rem;font-size:.78rem;line-height:1.5;color:#f3f4f6;background:#111827;border-radius:6px">
      <div style="font-weight:600;font-size:.85rem">${quote.name ?? quote.symbol}</div>
      <div style="opacity:.55;margin-bottom:.35rem">${quote.symbol}</div>
      <div style="display:flex;align-items:baseline;gap:.5rem;margin-bottom:.4rem">
        <span style="font-weight:600;font-size:.95rem">$${fmtPrice(quote.price)}</span>
        <span style="color:${changeColor}">${fmtPercent(change)}</span>
      </div>
      ${rows}
      ${
        quote.timestamp != null
          ? `<div style="opacity:.45;margin-top:.4rem;font-size:.68rem">${fmtTimestamp(quote.timestamp)}</div>`
          : ""
      }
    </div>`
}

/**
 * Treemap of the quotes the markets page lists — one tile per index, sized by how
 * far it moved and coloured by which way.
 *
 * @param quotes   quote objects as returned by the markets hooks
 * @param title    heading drawn above the map; pass null to omit
 * @param height   chart height in px
 * @param loading  renders the placeholder instead of the chart
 */
const IndexHeatMap = ({ quotes, title = "Index Performance", height = 420, loading = false }) => {
  // `ordered` backs the tooltip, label and colour lookups, so it has to stay in
  // step with the series Apex draws — all of them come off this one sort.
  const { series, ordered, colors } = useMemo(() => {
    const usable = []
    for (const quote of Array.isArray(quotes) ? quotes : []) {
      const change = toNumber(quote?.changesPercentage)
      if (quote?.symbol && change !== null) usable.push({ quote, change })
    }

    if (usable.length === 0) return { ordered: [], series: [{ data: [] }], colors: [] }

    // Strongest gainer first, so Apex lays the map out from the top-left corner
    // in the same order the sizing expresses.
    const sorted = usable.sort((a, b) => b.change - a.change)
    const sizeOf = tileSizer(sorted.map((entry) => entry.change))

    return {
      ordered: sorted,
      colors: sorted.map((entry) => bandColor(entry.change)),
      series: [
        {
          data: sorted.map((entry) => ({
            x: entry.quote.symbol,
            y: sizeOf(entry.change),
          })),
        },
      ],
    }
  }, [quotes])

  const options = useMemo(
    () => ({
      legend: { show: false },
      chart: {
        type: "treemap",
        toolbar: { show: false },
        background: "transparent",
        foreColor: "#e5e7eb",
        animations: { enabled: false },
      },
      // `y` now carries tile size rather than the move, so the colour band can no
      // longer be derived from it. `distributed` takes the colour for each tile
      // from this array instead, position by position.
      colors,
      dataLabels: {
        enabled: true,
        style: { fontSize: "12px", fontWeight: 500 },
        // `op.value` is the shifted tile size, so the label reads the true change
        // off the entry behind the tile instead.
        formatter: (text, op) => {
          const entry = ordered[op.dataPointIndex]
          return entry ? [text, fmtPercent(entry.change)] : text
        },
        offsetY: -4,
      },
      plotOptions: {
        treemap: {
          distributed: true,
          enableShades: false,
        },
      },
      states: {
        hover: { filter: { type: "lighten", value: 0.12 } },
        active: { filter: { type: "none" } },
      },
      tooltip: {
        custom: ({ dataPointIndex }) => {
          const entry = ordered[dataPointIndex]
          return entry ? tooltipMarkup(entry.quote, entry.change) : ""
        },
      },
    }),
    [ordered, colors]
  )

  const placeholder = (
    <div
      style={{
        height,
        background: "rgba(13, 17, 23, 0.55)",
        borderRadius: 6,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {loading ? (
        <Spinner animation="border" variant="light" role="status">
          <span className="visually-hidden">Loading...</span>
        </Spinner>
      ) : (
        <span className="text-inverse text-opacity-50 small">No index data available</span>
      )}
    </div>
  )

  return (
    <div className="index-heat-map">
      {title && <div className="fw-bold mb-2">{title}</div>}
      {loading || ordered.length === 0 ? (
        placeholder
      ) : (
        <ReactApexChart options={options} series={series} type="treemap" height={height} />
      )}
    </div>
  )
}

export default IndexHeatMap
