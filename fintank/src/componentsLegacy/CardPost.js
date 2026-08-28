import React from "react"
import Link from "next/link"
import Image from "./CustomImage"
import { Card, Button } from "react-bootstrap"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faClock } from "@fortawesome/free-regular-svg-icons"
import { faLongArrowAltRight } from "@fortawesome/free-solid-svg-icons"

const CardPost = (props) => {

  const adjustTimeStamp = (date) => {
    const options = { year: "numeric", month: "long", day: "numeric"}
    return new Date(date).toLocaleDateString(undefined, options)
  }

  const post = props.data
  return (
    <Card className="border-0 h-100 shadow">
      <Link legacyBehavior href={`${post.url}`}>
        <a className="">
          <Image
            src={`${post?.image}`}
            alt="..."
            width={1080}
            height={720}
            layout="intrinsic"
            className="img-fluid card-img-top"
            loading={props.eager ? "eager" : "lazy"}
          />
        </a>
      </Link>
      <Card.Body>
        <a
          href="#"
          className="text-uppercase text-muted text-sm letter-spacing-2"
        >
          {post.category}
        </a>
        <h5 className="my-2">
          <Link legacyBehavior href={`${post.url}`}>
            <a className="text-dark">{post.title}</a>
          </Link>
        </h5>
        <p className="text-gray-500 text-sm my-3">
          <FontAwesomeIcon icon={faClock} className="me-2" />
          {adjustTimeStamp(post.created_at)}
        </p>
        <p className="my-2 text-muted text-sm">{post.description}</p>
        <Link href={`${post.url}`} passHref>
          <Button className="ps-0" variant="link">
            Read more <FontAwesomeIcon icon={faLongArrowAltRight} />
          </Button>
        </Link>
      </Card.Body>
    </Card>
  )
}

export default CardPost
