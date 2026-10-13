import useSWR from "swr"
import axios from "axios"
import { filterDisplayableArticles } from "../utils/newsArticles"
import { withIsLoading } from "./swrLoading"

// The same Django endpoint the homepage reads at build time. Going through the
// backend keeps the upstream news API key server-side.
const URL = `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/get_articles/fmp/`

const fetcher = async (url) => {
  const res = await axios.get(url)
  return filterDisplayableArticles(res.data)
}

/**
 * News articles for client-rendered pages, already filtered to the displayable
 * set. Returns the SWR result plus a derived `isLoading` (SWR 1.3.0 has none).
 */
export const useNewsArticles = () =>
  withIsLoading(
    URL,
    useSWR(URL, fetcher, {
      // Wire stories turn over slowly and this feed is a sidebar, not the point of
      // the page, so it refreshes on the same cadence as the index quotes.
      refreshInterval: 600000,
    })
  )
