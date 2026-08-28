import React from "react"
import Link from "next/link"
import { Card } from "react-bootstrap"
import Image from "./CustomImage"
import Icon from "./Icon"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import {
  faBath,
  faBed,
  faMapMarker,
  faRulerCombined,
  faTag,
} from "@fortawesome/free-solid-svg-icons"

const CardProperty = (props) => {
  const data = props.data
  return (
    <Card className="h-100 border-0 shadow">
      <div className="card-img-top overflow-hidden gradient-overlay">
        <Image
          src={`/content/${data.img}`}
          width={1350}
          height={900}
          layout="responsive"
          alt={data.title}
          loading={props.eager ? "eager" : "lazy"}
          className="img-fluid"
          sizes="(max-width:576px) 100vw, (max-width:991px) 50vw, 280px"
        />
        <Link legacyBehavior href={data.link}>
          <a className="tile-link" />
        </Link>
        <div className="card-img-overlay-top text-end">
          <a href="#" className="card-fav-icon position-relative z-index-40">
            <Icon icon="heart-1" className="text-white" />
          </a>
        </div>
      </div>
      <Card.Body className="d-flex align-items-center">
        <div className="w-100">
          <Card.Title as="h6">
            <Link legacyBehavior href={data.link}>
              <a className="text-decoration-none text-dark">{data.title}</a>
            </Link>
          </Card.Title>
          <Card.Subtitle className="text-sm text-secondary mb-2" as="p">
            <FontAwesomeIcon
              icon={faMapMarker}
              className="text-secondary opacity-4 me-1"
            />
            {data.location}
          </Card.Subtitle>
          <p className="text-sm text-muted text-uppercase">{data.type}</p>
          <p className="card-text d-flex justify-content-between text-gray-800 text-sm">
            <span className="me-1">
              <FontAwesomeIcon
                icon={faRulerCombined}
                className="text-primary text-primary opacity-4 text-xs me-1"
              />
              {data.meters} m<sup>2</sup>
            </span>
            <span className="me-1">
              <FontAwesomeIcon
                icon={faBed}
                className="text-primary opacity-4 text-xs me-1"
              />
              {data.bedrooms}
            </span>
            <span className="me-1">
              <FontAwesomeIcon
                icon={faBath}
                className="text-primary opacity-4 text-xs me-1"
              />
              {data.bathrooms}
            </span>
            <span>
              <FontAwesomeIcon
                icon={faTag}
                className="text-primary opacity-4 text-xs me-1"
              />
              {data.price}
            </span>
          </p>
        </div>
      </Card.Body>
    </Card>
  )
}

export default CardProperty
