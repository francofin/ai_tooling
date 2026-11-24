/**
 * Thin a long daily {dates, value} series to one point a week, for drawing only.
 *
 * The treasury series on /capital-markets go back to 1962 (16k daily points
 * each, ~150k across the Economic tab). A ~600px chart cannot show more than
 * a few points per pixel, and building all of them stalled the tab switch.
 *
 * Keeps the last observation of each Monday-to-Sunday week (the week's close)
 * plus the first and last points, exact values only -- nothing is averaged.
 * Use it for the plotted line; anything that computes numbers (the bullet
 * commentary) must keep reading the full series.
 */
export const DISPLAY_POINT_LIMIT = 2000

const DAY_MS = 86_400_000

// 1970-01-01 was a Thursday, so +3 days puts week boundaries on Mondays.
const weekOf = (isoDate) => Math.floor((Date.parse(isoDate) / DAY_MS + 3) / 7)

export const weeklyForDisplay = (series, limit = DISPLAY_POINT_LIMIT) => {
  const dates = series?.dates
  if (!dates || dates.length <= limit) return series

  const last = dates.length - 1
  const keptDates = []
  const keptValues = []

  for (let i = 0; i <= last; i += 1) {
    if (i === 0 || i === last || weekOf(dates[i]) !== weekOf(dates[i + 1])) {
      keptDates.push(dates[i])
      keptValues.push(series.value[i])
    }
  }

  return { dates: keptDates, value: keptValues }
}
