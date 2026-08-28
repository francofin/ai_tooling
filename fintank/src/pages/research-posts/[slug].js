import React from "react"
import axios from "axios"
import Link from "next/link"

import { Container, Row, Col } from "react-bootstrap"
import Image from "@componentsLegacy/CustomImage"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faClock } from "@fortawesome/free-regular-svg-icons"

const API = process.env.NEXT_PUBLIC_FINTANK_API_URL

/**
 * Research article detail.
 *
 * The body is markdown held in S3 and rendered to HTML by the journal app, so
 * this page only fetches and lays out. See
 * docs/superpowers/plans/2026-08-24-journal-articles-from-s3.md.
 *
 * Server-rendered rather than statically generated: articles are published by
 * writing a file to S3, and getStaticPaths would need a rebuild before a new one
 * became reachable.
 */
export async function getServerSideProps({ params, res }) {
  const nav = { light: true, classes: "shadow", color: "white" }

  try {
    const response = await axios.get(`${API}/journals/${params.slug}/`)
    return {
      props: { nav, title: response.data.title, article: response.data },
    }
  } catch (error) {
    // A 404 status with our own state rather than `notFound: true`: that hands
    // off to the App Router's not-found path, which throws inside AppProviders
    // and surfaces as a 500. Same workaround as indexes/[slug].js.
    res.statusCode = error?.response?.status === 404 ? 404 : 503
    return { props: { nav, title: "Article not found", missingSlug: params.slug } }
  }
}

const formatDate = (value) => {
  if (!value) return null
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return null
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  })
}

const MissingArticle = ({ slug }) => (
  <section>
    <Container className="py-6 text-center">
      <Row>
        <Col lg="6" className="mx-auto">
          <h1 className="mb-3">Article not found</h1>
          <p className="text-muted mb-4">
            We don&apos;t have a research post at <code>{slug}</code>.
          </p>
          <Link href="/research-posts">Browse research</Link>
        </Col>
      </Row>
    </Container>
  </section>
)

const ResearchPost = ({ article, missingSlug }) => {
  if (missingSlug) return <MissingArticle slug={missingSlug} />

  // The banner is its own frontmatter field because it is a wide crop, but it
  // falls back to the card image so one asset still works.
  const banner = article.banner || article.image
  const published = formatDate(article.created_at)

  return (
    <div className="research-article">
      {/*
        The banner artwork carries its own headline, so the page does not draw
        one over it -- that produced two overlapping titles. It is shown whole at
        its own aspect ratio rather than cropped into a hero band, and the h1
        stays in the document, hidden, so screen readers and search engines still
        see the article title.
      */}
      {banner && (
        <section className="research-article-banner mb-5">
          <h1 className="visually-hidden">{article.title}</h1>
          <Image
            src={banner}
            alt={article.title}
            width={1880}
            height={647}
            layout="responsive"
            loading="eager"
            priority={true}
          />
        </section>
      )}

      <section>
        <Container>
          <Row>
            <Col lg="10" xl="8" className="mx-auto">
              <p className="py-3 mb-4 text-muted text-center fw-light">
                {article.category && (
                  <span className="text-uppercase letter-spacing-2 me-3">
                    {article.category}
                  </span>
                )}
                {published && (
                  <>
                    <FontAwesomeIcon icon={faClock} className="me-2" />
                    {published}
                  </>
                )}
              </p>

              {article.description && (
                <p className="lead mb-5 text-center">{article.description}</p>
              )}
            </Col>
          </Row>

          <Row>
            <Col xl="8" lg="10" className="mx-auto mb-5">
              {/*
                The HTML is rendered server-side from markdown we authored and
                uploaded to our own S3 bucket, so it is first-party content —
                the same trust level as the rest of the app. If the generation
                pipeline ever inlines third-party text, sanitise it in the
                backend renderer before it reaches here.
              */}
              <div
                className="text-content"
                dangerouslySetInnerHTML={{ __html: article.html }}
              />
            </Col>
          </Row>
        </Container>
      </section>
    </div>
  )
}

export default ResearchPost
