import React from "react"
import Link from "next/link"
import { Card } from "react-bootstrap"
import Icon from "./Icon"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faArrowTrendDown, faArrowTrendUp } from "@fortawesome/free-solid-svg-icons"

const MoverReturns = (props) => {


  return (
    <Card className="h-100 border-0 shadow">
      <div className="card-img-top overflow-hidden my-2 px-3" >
        {props.data.newGrade === 'Buy' || props.data.newGrade === 'Overweight' ?
          <FontAwesomeIcon icon={faArrowTrendUp} size="3x" pull="left" style={{color:"green"}}/> :
          <FontAwesomeIcon icon={faArrowTrendDown} size="3x" pull="left" style={{color:"red"}}/>
        }
      
        <Link legacyBehavior href="/detail-rooms">
          <a
            className="tile-link"
            // aria-label={`Read more about ${data.title}`}
          />
        </Link>
      </div>
      <hr />
      <Card.Body className="d-flex align-items-center">
        <div className="w-100">
          <Card.Title as="h6">
            <Link legacyBehavior href={props.data.newsURL}>
              <a className="text-decoration-none text-dark" target={"_blank"}>{props.data.symbol}</a>
            </Link>
            <p>
              {props.data.newsTitle}
            </p>
          </Card.Title>
          <Card.Subtitle className="d-flex mb-3" as="div">
            {props.data.newGrade === 'Outperform' || props.data.newGrade === 'Buy' ?
            <>
                <p className="flex-grow-1 mb-0 text-md" style={{color:"green"}}>
                Sentiment: {props.data.newGrade}
              </p>
              <hr />
              <p className="flex-grow-1 mb-0 text-md" style={{color:"green"}}>
                Price when posted: ${(props?.data?.priceWhenPosted)?.toFixed(2)}
              </p>
            </>:
            <>
                <p className="flex-grow-1 mb-0 text-md" style={{color:"red"}}>
                    Sentiment: {props.data.newGrade}
                </p>
                <hr />
                <p className="flex-grow-1 mb-0 text-md" style={{color:"red"}}>
                {props.data.priceWhenPosted ? (props.data.priceWhenPosted).toFixed(2): ""}
                </p>
            </>
            }
            
            <p className="flex-shrink-1 mb-0 card-stars text-xs text-end">
              {/* <Stars stars={data.stars} /> */}
            </p>
          </Card.Subtitle>
          <Card.Text className="text-muted">
            <span className="h6 text-primary">Source: {props.data.gradingCompany}</span>
            <span className="h6 text-primary">Date Published: {props.data.publishedDate}</span>
          </Card.Text>
        </div>
      </Card.Body>
    </Card>
  )
}

export default MoverReturns
