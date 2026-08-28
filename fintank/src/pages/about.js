import React from "react"
import Link from "next/link"
import { Container, Row, Col, Breadcrumb } from "react-bootstrap"
import data from "@data/team.json"
import CardTeam from "@componentsLegacy/CardTeam"
import Image from "@componentsLegacy/CustomImage"

export async function getStaticProps() {
  return {
    props: {
      nav: {
        light: true,
        classes: "shadow",
        color: "white",
      },
      title: "Team",
    },
  }
}

const Team = () => {
  const Team = (data) => {
    return (
      <Row>
        {data.map((item, i) => (
          <Col key={i} sm={12 / data.length} className="mb-3 mb-lg-0">
            <CardTeam data={item} />
          </Col>
        ))}
      </Row>
    )
  }
  return (
    <React.Fragment>
      <section className="d-flex align-items-center dark-overlay hero py-3 py-lg-5">
          <Image
            src={`/images/homeImages/simpleonthesurface.jpg`}
            layout="fill"
            className="bg-image"
            alt="Hero image"
            loading="eager"
            priority={true}
          />
          <Container className="py-6 py-lg-7 text-white overlay-content text-center">
            <Row>
              <Col xl="10" className="mx-auto">
                <h1 className="display-3 fw-bold text-shadow">
                {data.subtitle}
                </h1>
                <p className="text-lg text-shadow mt-3">{data.content}</p>
              </Col>
            </Row>
          </Container>
        </section>

      {data.founders && (
        <section className="pt-6 pb-4">
          <Container>
            <h6 className="subtitle text-center text-primary mb-5">
              {data.founders.title}
            </h6>
            {Team(data.founders.items)}
          </Container>
        </section>
      )}
      {data.quote && (
        <section className="py-5">
          <Container className="bg-gray-100 py-5 px-3 px-lg-5 rounded-3 shadow-sm">
            <Row>
              <Col lg="5">
                <div className="p-5">
                  <Image
                    src={`/images/homeImages/${data.quote.avatar}`}
                    alt={data.quote.author}
                    width={600}
                    height={600}
                    layout="responsive"
                    className="img-fluid rounded-circle shadow-sm"
                    sizes="(max-width: 576px) 100vw, 530px"
                  />
                </div>
              </Col>
              <Col lg="6" className="d-flex align-items-center">
                <div>
                  <blockquote className="blockquote-icon">
                    <p className="text-md text-gray-700 mb-4">
                    {data.quote.title}{" "}
                    </p>
                    <h6 className="text-lg text-uppercase text-primary">
                      — {data.quote.author}
                    </h6>
                  </blockquote>
                </div>
              </Col>
            </Row>
          </Container>
        </section>
      )}
      {/* {data.sales && (
        <section className="py-6">
          <Container>
            <h6 className="subtitle text-center mb-4">{data.sales.title}</h6>
            {Team(data.sales.items)}
          </Container>
        </section>
      )} */}

    </React.Fragment>
  )
}

export default Team
