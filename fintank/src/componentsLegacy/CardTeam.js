import React from "react"
import Link from "next/link"
import { Card } from "react-bootstrap"
import Image from "@componentsLegacy/CustomImage"

const CardTeam = (props) => {
  const data = props.data
  return (
    <Card className="border-0 hover-animate bg-transparent">
        <a className="position-relative">
          <div className="card-img-top team-img">
            <Image
              src={`/images/homeImages/${data.img}`}
              alt="Stock and Market Research"
              width={408}
              height={420}
              layout="responsive"
              className="img-fluid"
              sizes="(max-width:576px) 100vw, (max-width:1199px) 30vw, 350px"
            />
          </div>
          <div
            className={`team-circle false ${
              data.color ? `bg-${data.color}` : ""
            }`}
          />
        </a>
      <Card.Body className="team-body text-center">
        <Card.Title as="h6">{data.title}</Card.Title>
        <Card.Subtitle as="p" className="text-muted text-xs text-uppercase">
          {data.content}
        </Card.Subtitle>
      </Card.Body>
    </Card>
  )
}

export default CardTeam
