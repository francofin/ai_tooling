# Homepage Heatmap Restyle

**Date:** 2026-06-11  
**Status:** Approved

## Summary

Restyle the existing flat treemap in `MoversSection.js` to use a dark terminal aesthetic — dark background, bordered cells, GitHub-palette green/red — with symbol and % change visible on every box regardless of size. An index dropdown lets users switch universes. Clicking any stock tile navigates to `/stocks/[symbol]`.

No backend changes required. The existing `/api/constituent-returns/{universe}/` endpoint returns `{x: symbol, y: changePercentage}` which is all the chart needs.

---

## What We're Building

Replace the existing ApexCharts treemap visual at the bottom of `MoversSection.js` with a restyled version. The chart behaviour (index selector, treemap type, height 750px) is unchanged. Only the ApexCharts options object and label formatter change.

### Visual Design

- **Background:** `#0d1117` (GitHub dark)
- **Cell borders:** coloured to match performance band (green/red)
- **Labels:** every box shows `[symbol, value%]` stacked — ApexCharts clips silently if the box is too small
- **Font size:** `11px` for labels (ApexCharts handles scaling)
- **Neutral (≈0%):** `#1c1c1e` fill, `#444` border

### Colour Scale (5 bands)

| Range | Fill | Border |
|---|---|---|
| ≤ −6% | `#5a0a10` | `#f85149` |
| −6% to −3% | `#3d0912` | `#f85149` |
| −3% to 0% | `#3d0912` | `#f85149` |
| 0% to +3% | `#0d3a18` | `#2ea043` |
| ≥ +3% | `#0d4a1f` | `#3fb950` |
| ~0% neutral | `#1c1c1e` | `#444` |

---

## Components & Data Flow

### Files changed

| File | Change |
|---|---|
| `src/hooks/useIndexHeatMap.js` | Update ApexCharts options: colour scale, dataLabels formatter, click event handler |
| `src/componentsLegacy/Homepage/MoversSection.js` | No JSX change — visual change is entirely in the hook |

### Hook changes (`useIndexHeatMap.js`)

1. **`plotOptions.treemap.colorScale.ranges`** — replace existing hex values with the 5-band dark palette above.
2. **`dataLabels.formatter`** — keep `[text, op.value + '%']` format; ensure it applies to all box sizes (no conditional hiding).
3. **`dataLabels.style.fontSize`** — set to `'11px'`.
4. **`chart.events.dataPointSelection`** — add callback:
   ```js
   (event, chartContext, config) => {
     const symbol = config.w.config.series[0].data[config.dataPointIndex]?.x
     if (symbol) router.push(`/stocks/${symbol}`)
   }
   ```
5. **`chart.background`** — set to `'#0d1117'`.
6. **`chart.foreColor`** — set to `#c9d1d9` (light text for dark bg).

`useRouter` from `next/router` must be imported in the hook.

### Series data

Unchanged — `series: [{ data: heatMapData }]` where `heatMapData` is `[{x: symbol, y: changePercentage}]`.

---

## Loading, Error & Edge Cases

- **Loading:** show a 750px-tall skeleton `div` with pulse animation while `heatMapOptions` is `undefined`.
- **Error / empty data:** if fetch throws or `heat_map` is empty, `heatMapOptions` stays `undefined`; the `ReactApexChart` block is skipped (existing behaviour).
- **SSR guard:** `typeof window !== "undefined"` check stays in place; `ReactApexChart` loaded via `dynamic(..., { ssr: false })`.
- **Stock navigation:** `router.push('/stocks/${symbol}')` on tile click. Returns 404 until the stock page is built — acceptable.
- **Text overflow:** ApexCharts silently drops label lines that don't fit in a small box — no custom truncation needed.

---

## What Is Not Changing

- Gainers/losers Swiper sections in `MoversSection.js`
- Index `<Select>` dropdown and `constituentIndexMaps` options
- `/api/constituent-returns/{universe}/` backend endpoint
- Series data shape `[{data: [{x, y}]}]`
- Chart height (750px)
- Chart type (`treemap`)
