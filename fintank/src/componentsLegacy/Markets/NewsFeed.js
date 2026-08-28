import React, { useState } from "react"
import { Card, Spinner } from "react-bootstrap"
import NewsPost from "../NewsPost"
import ArticleModal from "../ArticleModal"
import { useNewsArticles } from "../../hooks/useNewsArticles"

/**
 * The homepage news cards in a scrolling column, for use in a sidebar.
 *
 * Uses the homepage's own `NewsPost`, so the cards stay identical; only the
 * layout differs — the list scrolls inside a fixed height rather than extending
 * the page.
 *
 * @param title  heading above the list
 * @param limit  how many articles to render
 */
const NewsFeed = ({ title = "Market news", limit = 30 }) => {
  const { data: articles, error, isLoading } = useNewsArticles()
  const [activePost, setActivePost] = useState(null)

  const visible = (articles ?? []).slice(0, limit)

  return (
    <Card className="mb-3">
      <div className="list-group list-group-flush">
        <div className="list-group-item fw-bold px-3">{title}</div>

        {/* The scroll lives on this element, not the card, so the heading stays
            put while the articles move under it. */}
        <div className="news-feed-scroll px-3 py-3">
          {isLoading && (
            <div className="text-center py-4">
              <Spinner animation="border" variant="light" size="sm" role="status">
                <span className="visually-hidden">Loading...</span>
              </Spinner>
            </div>
          )}

          {error && (
            <p className="text-inverse text-opacity-50 small mb-0 py-2">
              Market news is unavailable right now.
            </p>
          )}

          {!isLoading && !error && visible.length === 0 && (
            <p className="text-inverse text-opacity-50 small mb-0 py-2">No articles available.</p>
          )}

          {visible.map((post) => (
            <div key={post.url || post.link} className="news-feed-item hover-animate">
              <NewsPost data={post} onOpen={setActivePost} />
            </div>
          ))}
        </div>
      </div>

      <ArticleModal post={activePost} onHide={() => setActivePost(null)} />
    </Card>
  )
}

export default NewsFeed
