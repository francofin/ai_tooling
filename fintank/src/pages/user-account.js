import React from "react"
import Link from "next/link"
import { Container, Row, Col, Card, Breadcrumb } from "react-bootstrap"
import data from "@data/user-account.json"
import Icon from "@componentsLegacy/Icon"

export async function getStaticProps() {
  return {
    props: {
      nav: {
        light: true,
        classes: "shadow",
        color: "white",
      },
      title: "User Dashboard",
    },
  }
}

const UserDashboard = () => {
  return (
    <section className="py-5">
      <Container>
        <Breadcrumb listProps={{ className: "ps-0 justify-content-start" }}>
          <Breadcrumb.Item linkAs={Link} href="/">
            Home
          </Breadcrumb.Item>
          <Breadcrumb.Item active>Your dashboard</Breadcrumb.Item>
        </Breadcrumb>

        <h1 className="hero-heading mb-0">{data.title}</h1>
        <p className="text-muted mb-5">{data.subtitle}</p>
        <Row>
          {data.cards.map((card) => (
            <Col xs="6" md="4" className="mb-30px" key={card.title}>
              <Card className="h-100 border-0 shadow hover-animate">
                <Card.Body>
                  <div className="icon-rounded bg-secondary-light mb-3">
                    <Icon
                      icon={card.icon}
                      className="text-secondary w-2rem h-2rem"
                    />
                  </div>
                  <Card.Title className="mb-3" as="h5">
                    <Link
                      href={card.link}
                      className="text-decoration-none text-dark stretched-link"
                    >
                      {card.title}
                    </Link>
                  </Card.Title>
                  <Card.Text className="text-muted text-sm">
                    {card.content}
                  </Card.Text>
                </Card.Body>
              </Card>
            </Col>
          ))}
        </Row>
      </Container>
    </section>
  )
}

export default UserDashboard
