import React, { useEffect, useState } from "react"
import DOMPurify from "dompurify"
import { Modal, Button, Spinner } from "react-bootstrap"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faAngleDoubleRight } from "@fortawesome/free-solid-svg-icons"
import { faClock } from "@fortawesome/free-regular-svg-icons"
import Image from "./CustomImage"
import { formatArticleDate } from "@utils/newsDate"

// News article content is raw HTML from a third-party API (and, once we extract
// it, from arbitrary news sites), so it MUST be sanitized before rendering.
// Only runs client-side (modal opens on click).
const sanitizeContent = (html) => {
  if (typeof window === "undefined" || !html) return ""
  DOMPurify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName === "A" && node.hasAttribute("href")) {
      node.setAttribute("target", "_blank")
      node.setAttribute("rel", "noopener noreferrer")
    }
  })
  const clean = DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ["p", "strong", "em", "ul", "ol", "li", "br", "a", "h2", "h3", "blockquote"],
    ALLOWED_ATTR: ["href", "target", "rel"],
  })
  DOMPurify.removeHook("afterSanitizeAttributes")
  return clean
}

// Articles arrive in different shapes across the news categories (bing/fmp/
// stock/crypto), so normalize every field the modal needs from either variant.
const normalize = (post) => ({
  title: post.name || post.title || "",
  body: post.content || post.text || post.description || post.snippet || "",
  source: post.provider?.[0]?.name || post.site || post.source || "",
  url: post.url || post.link || "",
  date: formatArticleDate(post),
  image:
    post.image?.thumbnail?.contentUrl ||
    post.thumbnail ||
    (typeof post.image === "string" ? post.image : ""),
})


// The feeds only give us a snippet, so once the modal opens we try to extract
// the full story server-side. If the existing body is already long, it's
// effectively full content and not worth a round trip.
const ALREADY_RICH_THRESHOLD = 1000

// Successful (and failed) extractions cached across opens, keyed by article url.
const extractionCache = new Map()

const ArticleModal = ({ post, onHide }) => {
  const article = post ? normalize(post) : null
  const articleUrl = article?.url || ""
  const snippet = article?.body || ""
  const skipExtraction = snippet.length > ALREADY_RICH_THRESHOLD

  const [fullContent, setFullContent] = useState("")
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setFullContent("")
    setLoading(false)
    if (!articleUrl || skipExtraction) return

    // Instant if we've already extracted (or tried) this article this session.
    const cached = extractionCache.get(articleUrl)
    if (cached !== undefined) {
      setFullContent(cached)
      return
    }

    let cancelled = false
    const controller = new AbortController()
    setLoading(true)

    fetch(`/api/articlefetcher?url=${encodeURIComponent(articleUrl)}`, {
      signal: controller.signal,
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        const extracted = data?.content || ""
        extractionCache.set(articleUrl, extracted)
        if (!cancelled) setFullContent(extracted)
      })
      .catch(() => {
        // Silent fallback to the snippet; "Open full article" is the escape hatch.
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [articleUrl, skipExtraction])

  // Keep whichever body is longer/richer — extraction can only improve things.
  const displayBody = fullContent.length > snippet.length ? fullContent : snippet

  return (
    <Modal show={!!post} onHide={onHide} size="lg" centered scrollable>
      {article && (
        <>
          <Modal.Header closeButton>
            <Modal.Title className="h5 mb-0">{article.title}</Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {article.image && (
              <Image
                src={`/api/imagefetcher?url=${encodeURIComponent(article.image)}`}
                alt="..."
                width={1080}
                height={720}
                layout="intrinsic"
                className="img-fluid rounded mb-3"
              />
            )}
            <span className="text-uppercase text-muted text-sm letter-spacing-2">
              {article.source}
            </span>
            <p className="text-gray-500 text-sm my-2">
              <FontAwesomeIcon icon={faClock} className="me-2" />
              {article.date}
            </p>
            <div
              className="text-muted mt-3"
              dangerouslySetInnerHTML={{ __html: sanitizeContent(displayBody) }}
            />
            {loading && (
              <p className="text-muted text-sm mt-2 d-flex align-items-center">
                <Spinner animation="border" size="sm" className="me-2" role="status" />
                Loading full article…
              </p>
            )}
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={onHide}>
              Close
            </Button>
            <Button
              as="a"
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              variant="primary"
            >
              Open full article <FontAwesomeIcon icon={faAngleDoubleRight} className="ms-2" />
            </Button>
          </Modal.Footer>
        </>
      )}
    </Modal>
  )
}

export default ArticleModal
