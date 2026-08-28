import React from "react"
import Link from "next/link"
import { Container, Row, Col, Breadcrumb } from "react-bootstrap"
import data from "@data/faq.json"
import Image from "@componentsLegacy/CustomImage"
export async function getStaticProps() {
  return {
    props: {
      nav: {
        light: true,
        classes: "shadow",
        color: "white",
      },
      title: "Faq",
    },
  }
}

const Faq = () => {
  const groupByN = (n, data) => {
    let result = []
    for (let i = 0; i < data.length; i += n) result.push(data.slice(i, i + n))
    return result
  }
  return (
    <React.Fragment>
        <section className="d-flex align-items-center dark-overlay hero py-3 py-lg-5">
          <Image
            src={`/images/homeImages/world.jpg`}
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

      <section className="py-6">
        <Container>
          {data.questionGroups &&
            data.questionGroups.map((group) => {
              const groupedQuestions =
                group.questions && groupByN(2, group.questions)
              return (
                <div key={group.title} className="py-4" >
                  <h2 className="mb-5 text-primary">{group.title}</h2>
                  <Row>
                    {groupedQuestions.map((questions) => (
                      <Col md="6" key={questions[0].title}>
                        {questions.map((question) => (
                          <React.Fragment key={question.title}>
                            <h5>{question.title}</h5>
                            <p className="text-muted mb-4" dangerouslySetInnerHTML={{ __html: question.content }} />
                              {/* {question.content}
                            </p> */}
                          </React.Fragment>
                        ))}
                      </Col>
                    ))}
                  </Row>
                </div>
              )
            })}
        </Container>
      </section>
    </React.Fragment>
  )
}

export default Faq
