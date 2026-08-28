/**
 * Build an ApexCharts `chart.id` that survives its own destroy path.
 *
 * ApexCharts registers an instance under the RAW id (`apexcharts.js:34` sets
 * `globals.chartID = config.chart.id`, and `:61` pushes that into
 * `Apex._chartInstances`), but `destroy()` looks the entry up under the
 * ESCAPED id (`:406`, `c.id === Utils.escapeString(chartID)`).
 *
 * `Utils.escapeString` rewrites every character in
 * `` ` ~!@#$%^&*()|+\=?;:'",.<>{}[]\/ `` to `x`, so any id containing one of
 * them never matches on destroy: the splice silently does nothing and the
 * destroyed chart stays registered with its modules nulled out. The next
 * chart to render walks `getGroupedCharts()` — whose filter is page-wide,
 * not group-scoped — hits that corpse, and throws
 * `Cannot read properties of null (reading 'getPreviousPaths')`.
 *
 * Our ids are built from a ticker and an indicator token, so they naturally
 * contain `:` (`AAPL:sma:50`) and can contain `.` (`RQP.TO`) — they hit this
 * on every single unmount. React StrictMode double-invokes effects in dev,
 * so one corpse per chart appears the moment the page loads.
 *
 * The encoding below is injective: unsafe characters become `_<charCode>_`
 * rather than collapsing to a shared `x`. That matters because a lossy
 * mapping would make `BRK.A` and `BRK-A` — both real tickers — collide on a
 * single rail, and `destroy()` splices the FIRST id match, so a collision
 * would deregister a chart still on screen.
 */
const UNSAFE = /[`~!@#$%^&*()|+\-=?;:'",.<>{}[\]\\/\s]/g

export const chartId = (...parts) => parts.join('_').replace(UNSAFE, (char) => `_${char.charCodeAt(0)}_`)
