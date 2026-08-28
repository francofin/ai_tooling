import React, { useState } from "react"
import Link from "next/link"
import { Container, Row, Col } from "react-bootstrap"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faAngleDoubleRight } from "@fortawesome/free-solid-svg-icons"
import NewsPost from "../NewsPost"
import ArticleModal from "../ArticleModal"

const NewsSection = ({ articles, data }) => {
  const [activePost, setActivePost] = useState(null)

  if (!articles?.length) return null

  return (
    <section className="py-6 bg-gray-100">
      <Container>
        <Row className="mb-5">
          <Col md="8">
            <p className="subtitle text-primary">{data.blogPosts.subTitle}</p>
            <h2>{data.blogPosts.title}</h2>
          </Col>
          <Col md="4" className="d-md-flex align-items-center justify-content-end">
            <Link href={data.blogPosts.buttonLink} className="text-muted text-sm" target="_blank">
              {data.blogPosts.button}
              <FontAwesomeIcon icon={faAngleDoubleRight} className="ms-2" />
            </Link>
          </Col>
        </Row>
        <Row>
          {articles.slice(0, 64).map((post) => (
            <Col key={post.link} lg="3" sm="6" className="mb-4 hover-animate">
              <NewsPost data={post} onOpen={setActivePost} />
            </Col>
          ))}
        </Row>
      </Container>

      <ArticleModal post={activePost} onHide={() => setActivePost(null)} />
    </section>
  )
}

export default NewsSection
