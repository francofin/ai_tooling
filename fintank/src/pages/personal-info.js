import React, { useEffect, useState, useContext } from "react"
import Link from "next/link"
import Select from "react-select"
import {
  Container,
  Row,
  Col,
  Button,
  Collapse,
  Form,
  Card,
  Breadcrumb,
} from "react-bootstrap"
import { DjangoAuthContext } from '@context/authContext';
import data from "@data/user-personal.json"
import Icon from "@componentsLegacy/Icon"
import {
  faAddressBook,
  faBirthdayCake,
  faEnvelopeOpen,
  faIdCard,
  faPhone,
} from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"

export async function getStaticProps() {
  return {
    props: {
      nav: {
        light: true,
        classes: "shadow",
        color: "white",
      },
      loggedUser: true,
      title: "Personal info - forms",
    },
  }
}

const UserPersonal = () => {
  const {user, userProfile} = useContext(DjangoAuthContext);
  const [personalCollapse, setPersonalCollapse] = React.useState(false)
  const [addressCollapse, setAddressCollapse] = React.useState(false)
  const [name, setName] = useState(user?.first_name)
  const [birthdate, setBirthDate] = useState("06/22/1980")
  const [phoneNumber, setPhoneNumber] = useState("+42055544466")



  return (
    <section className="account-page py-5">
      <Container>
        <Breadcrumb listProps={{ className: "ps-0 justify-content-start" }}>
          <Breadcrumb.Item linkAs={Link} href="/">
            Home
          </Breadcrumb.Item>
          <Breadcrumb.Item linkAs={Link} href="/user-account">
            Account
          </Breadcrumb.Item>
          <Breadcrumb.Item active>Personal info</Breadcrumb.Item>
        </Breadcrumb>

        <h1 className="hero-heading mb-0">{data.title}</h1>
        <p className="text-muted mb-5">{data.subtitle}</p>
        <Row>
          <Col lg="7">
            <div className="text-block">
              <Row className="mb-3">
                <Col sm="9">
                  <h5>Personal details</h5>
                </Col>
                <Col sm="3" className="text-end">
                  <Button
                    variant="link"
                    className="ps-0 collapsed"
                    onClick={() => setPersonalCollapse(!personalCollapse)}
                  >
                    Update
                  </Button>
                </Col>
              </Row>
              <p className="text-sm text-muted">
              <React.Fragment>
                <FontAwesomeIcon icon={faIdCard} className="me-2 fa-fw" />
                {user?.first_name}{" "}{user?.last_name}
                { <br />}
              </React.Fragment>
              <React.Fragment>
                <FontAwesomeIcon icon={faEnvelopeOpen} className="me-2 fa-fw" />
                {user?.role}
                { <br />}
              </React.Fragment>
              <React.Fragment>
                <FontAwesomeIcon icon={faEnvelopeOpen} className="me-2 fa-fw" />
                {user?.email}
                { <br />}
              </React.Fragment>
              </p>
              <Collapse in={personalCollapse}>
                <Form>
                  <Row className="pt-4">
                    <Col md="6" className="mb-4">
                      <Form.Label htmlFor="name">Name</Form.Label>
                      <Form.Control
                        type="text"
                        name="name"
                        id="name"
                        defaultValue={name}
                      />
                    </Col>
                    <Col md="6" className="mb-4">
                      <Form.Label htmlFor="date">Date of birth</Form.Label>
                      <Form.Control
                        type="text"
                        name="date"
                        id="date"
                        defaultValue={birthdate}
                      />
                    </Col>
                    <Col md="6" className="mb-4">
                      <Form.Label htmlFor="email">Email address</Form.Label>
                      <Form.Control
                        type="email"
                        name="email"
                        id="email"
                        defaultValue={user?.email}
                      />
                    </Col>
                    <Col md="6" className="mb-4">
                      <Form.Label htmlFor="phone">Phone number</Form.Label>
                      <Form.Control
                        type="text"
                        name="phone"
                        id="phone"
                        defaultValue= {phoneNumber}
                      />
                    </Col>
                  </Row>
                  <Button
                    type="submit"
                    variant="outline-primary"
                    className=" mb-4"
                  >
                    Save your personal details
                  </Button>
                </Form>
              </Collapse>
            </div>
        </Col>
          <Col md="6" lg="4" className="ms-lg-auto">
            <Card className="border-0 shadow">
              <Card.Header className="bg-primary-light py-4 border-0">
                <div className="d-flex align-items-center">
                  <div>
                    <h4 className="h6 subtitle text-sm text-primary">
                      What info is shared with others?
                    </h4>
                  </div>
                  <Icon
                    icon="identity-1"
                    className="svg-icon-light w-3rem h-3rem ms-3 text-primary flex-shrink-0"
                  />
                </div>
              </Card.Header>
              <Card.Body className="p-4">
                <p className="text-muted text-sm card-text">
                  Fintank does not releases contact information for users.
                </p>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      </Container>
    </section>
  )
}

export default UserPersonal
