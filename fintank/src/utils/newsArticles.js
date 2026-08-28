/**
 * Shared rules for which news articles are fit to display.
 *
 * The homepage fetches its articles at build time and the profile rail fetches
 * them in the browser, so the filter lives here rather than in either one — the
 * two feeds should never disagree about what is worth showing.
 */

// This source returns items whose bodies are scraped boilerplate rather than
// article text.
const EXCLUDED_SITES = new Set(["newslanes"])

/**
 * Drops excluded sources and anything with no image, since every card in both
 * feeds leads with one and a missing image leaves a broken frame.
 */
export const filterDisplayableArticles = (articles) =>
  (Array.isArray(articles) ? articles : []).filter(
    (article) => !EXCLUDED_SITES.has(article?.site) && !!article?.image
  )
