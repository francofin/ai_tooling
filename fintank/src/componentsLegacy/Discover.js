import React from "react"
import { Container, Row, Col } from "react-bootstrap"
import Icon from "./Icon"

const Discover = (props) => {
  return (
    <section className={props.className}>
      <Container>
        <div className="pb-lg-4">
          <p className="subtitle text-secondary">{props.subTitle}</p>
          <h2 className="mb-5">{props.title}</h2>
        </div>
        <Row>
          {props.blocks.map((block) => (
            <Col
              key={block.title}
              sm="6"
              lg={12 / props.blocks.length}
              className="mb-3 mb-lg-0"
            >
              <div className="px-0 pe-lg-3">
                <div className={`icon-rounded mb-3 bg-${block.color}-light`}>
                  <Icon
                    icon={block.icon}
                    className={`w-2rem h-2rem text-${block.color}`}
                  />
                </div>
                <h3 className="h6 text-uppercase">{block.title}</h3>
                <p className="text-muted text-sm">{block.content}</p>
              </div>
            </Col>
          ))}
        </Row>
      </Container>
    </section>
  )
}

export default Discover
