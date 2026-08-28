import React from "react"
import Image from "./CustomImage"

import { Card, Button } from "react-bootstrap"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faClock } from "@fortawesome/free-regular-svg-icons"
import { faLongArrowAltRight } from "@fortawesome/free-solid-svg-icons"

const NewsPost = (props) => {
  const post = props.data
  const onOpen = props.onOpen
  const articleUrl = post.url || post.link

  const adjustTimeStamp = (date) => {
    const options = { year: "numeric", month: "long", day: "numeric"}
    return new Date(date).toLocaleDateString(undefined, options)
  }

  // Content is raw HTML from the news API; strip tags so the plain-text teaser
  // never shows tag fragments like "<strong>" or "li>".
  const stripHtml = (html) => (html || "").replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim()

  const handleOpen = (e) => {
    if (!onOpen) return
    e.preventDefault()
    onOpen(post)
  }

  return (
    <Card className="border-0 h-100 shadow">
      <a href={articleUrl} target="_blank" rel="noopener noreferrer" onClick={handleOpen}>
        <Image
          src={`/api/imagefetcher?url=${encodeURIComponent(post.image)}`}
          alt="..."
          width={1080}
          height={720}
          layout="intrinsic"
          className="img-fluid card-img-top"
          loading={props.eager ? "eager" : "lazy"}
        />
      </a>
      <Card.Body>
        <span className="text-uppercase text-muted text-sm letter-spacing-2">
          {post.site}
        </span>
        <h5 className="my-2">
          <a href={articleUrl} className="text-dark" target="_blank" rel="noopener noreferrer" onClick={handleOpen}>
            {post.title}
          </a>
        </h5>
        <p className="text-gray-500 text-sm my-3">
          <FontAwesomeIcon icon={faClock} className="me-2" />
          {adjustTimeStamp(post.date)}
        </p>
        <p className="my-2 text-muted text-sm">{stripHtml(post.content).substring(0, 115) + "..."}</p>
        <a href={articleUrl} target="_blank" rel="noopener noreferrer" onClick={handleOpen}>
          <Button className="ps-0" variant="link">
            Read more <FontAwesomeIcon icon={faLongArrowAltRight} />
          </Button>
        </a>
      </Card.Body>
    </Card>
  )
}

export default NewsPost
