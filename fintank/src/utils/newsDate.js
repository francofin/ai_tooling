/**
 * Publish dates for news articles across every feed.
 *
 * The backend adds `published_at` (ISO 8601) to each article. The raw fields it
 * comes from are unparseable or misleading on their own: scraped topic feeds
 * carry ages like "2h" relative to when they were scraped, and FMP's
 * "2026-09-18 21:00:16" has a space that Safari refuses to parse.
 */
export const articleDate = (article) => {
  const raw =
    article?.published_at || article?.datePublished || article?.publishedDate || article?.date
  if (!raw) return null
  const parsed = new Date(String(raw).replace(" ", "T"))
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

const LONG_DATE = { year: "numeric", month: "long", day: "numeric" }

/** "September 20, 2026", or "" when the article has no usable date. */
export const formatArticleDate = (article, options = LONG_DATE) => {
  const date = articleDate(article)
  return date ? date.toLocaleDateString(undefined, options) : ""
}
