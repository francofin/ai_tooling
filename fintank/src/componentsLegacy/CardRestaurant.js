import React from "react"
import Link from "next/link"
import { Card, Badge } from "react-bootstrap"
import Stars from "@componentsLegacy/Stars"
import Image from "./CustomImage"
import Icon from "./Icon"

const CardRestaurant = (props) => {
  const data = props.data
  return (
    <Card className="h-100 border-0 shadow">
      <div
        style={{
          minHeight: "200px",
        }}
        className="card-img-top overflow-hidden dark-overlay"
      >
        <Image
          src={`/content/img/photo/${data.image}`}
          layout="fill"
          className="bg-image"
          alt={data.name}
          sizes={
            props.sizes
              ? props.sizes
              : "(max-width:576px) 100vw, (max-width:991px) 50vw, 280px"
          }
        />
        <Link legacyBehavior href={data.link}>
          <a className="tile-link" />
        </Link>
        <div className="card-img-overlay-bottom z-index-20">
          <h4 className="text-white text-shadow">{data.name}</h4>
          <p className="mb-2 text-xs">
            <Stars stars={data.stars} />
          </p>
        </div>
        <div className="card-img-overlay-top d-flex justify-content-between align-items-center">
          <Badge pill bg="transparent" className="px-3 py-2">
            {data.category}
          </Badge>
          <a href="#" className="card-fav-icon position-relative z-index-40">
            <Icon icon="heart-1" className="text-white" />
          </a>
        </div>
      </div>
      <Card.Body>
        <p className="text-sm text-muted mb-3">
          {data.about.substring(0, 115) + "..."}
        </p>
        <p className="text-sm text-muted text-uppercase mb-1">
          By
          <Link legacyBehavior href="/user-profile">
            <a className="text-dark ms-1">{data.person}</a>
          </Link>
        </p>
        <p className="text-sm mb-0">
          {data.tags.map((tag, index) => (
            <a key={index} className="me-1" href="#">
              {tag}
              {index < data.tags.length - 1 && ","}
            </a>
          ))}
        </p>
      </Card.Body>
    </Card>
  )
}

export default CardRestaurant
