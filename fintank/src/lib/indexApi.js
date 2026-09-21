import axios from "axios"

/**
 * Every /indexes/<slug> request lives here, so no component builds a URL.
 *
 * The page this replaces called five endpoints that no longer existed and one
 * that hit FMP straight from the browser with NEXT_PUBLIC_FMP_API in the query
 * string. Everything below goes to Django, which holds the keys and the Redis
 * cache.
 */

const API_URL =
  process.env.NEXT_PUBLIC_FINTANK_API_URL ?? "http://localhost:8000/api"

const fetcher = async (url) => {
  const response = await axios.get(url)
  return response.data
}

/** Price series, moving averages, the header ribbon, and the peer list. */
export const indexSeriesUrl = (slug, { years } = {}) =>
  `${API_URL}/index-series/${slug}/${years ? `?years=${years}` : ""}`

export const fetchIndexSeries = (slug, options) =>
  fetcher(indexSeriesUrl(slug, options))

/** One index against one peer: replaces the five comparison pack endpoints. */
export const indexComparisonUrl = (slug, peerKey, { years } = {}) =>
  `${API_URL}/index-comparison/${slug}/${peerKey}/${years ? `?years=${years}` : ""}`

export const fetchIndexComparison = (slug, peerKey, options) =>
  fetcher(indexComparisonUrl(slug, peerKey, options))

/** Constituent contribution to index volatility and to period return. */
export const indexRiskUrl = (slug, { limit } = {}) =>
  `${API_URL}/index-risk/${slug}/${limit ? `?limit=${limit}` : ""}`

export const fetchIndexRisk = (slug, options) => fetcher(indexRiskUrl(slug, options))

/** Sector contribution to index return, plus constituent breadth, by window. */
export const indexSectorContributionUrl = (slug) =>
  `${API_URL}/index-sector-contribution/${slug}/`

export const fetchIndexSectorContribution = (slug) =>
  fetcher(indexSectorContributionUrl(slug))

/** Constituent quotes feeding both the movers panel and the valuation table. */
export const indexQuotesUrl = (slug) => `${API_URL}/index-quotes/${slug}/`

export const fetchIndexQuotes = (slug) => fetcher(indexQuotesUrl(slug))

export { fetcher }
