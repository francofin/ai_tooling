import React, {useContext} from "react"
import Link from "next/link"
import { useRouter } from "next/router"
import { DjangoAuthContext } from '@context/authContext';
import {
  Container,
  Row,
  Col,
  Button,
  Collapse,
  Badge,
  Form,
  Card,
  Breadcrumb,
} from "react-bootstrap"

import data from "@data/user-security.json"
import Icon from "@componentsLegacy/Icon"

export async function getStaticProps() {
  return {
    props: {
      nav: {
        light: true,
        classes: "shadow",
        color: "white",
      },
      loggedUser: true,
      title: "Personal & security - forms",
    },
  }
}

const UserSecurity = () => {
  const [loginCollapse, setLoginCollapse] = React.useState(false)

  const {logout, dispatch} = useContext(DjangoAuthContext);
  const router = useRouter();

  // Read off `navigator` only after mount — it does not exist during SSR, and
  // `userAgentData` is absent entirely in Firefox/Safari.
  const [deviceLabel, setDeviceLabel] = React.useState("")
  React.useEffect(() => {
    const ua = navigator.userAgent || ""
    const brands = navigator.userAgentData?.brands || []
    const brand = brands.length ? brands[brands.length - 1].brand : ""
    setDeviceLabel([ua.slice(13, 28).trim(), brand].filter(Boolean).join(" "))
  }, [])

  const logOutHandler = async() => {
    dispatch({
      type:'LOGGED_IN_USER',
      payload: null
    })

    logout();
    router.push('/login');
  }

  const adjustTimeStamp = (date) => {
    const options = { year: "numeric", month: "long", day: "numeric"}
    return new Date(date).toLocaleDateString(undefined, options)
  }

  const successCallBack = (position) => {
    console.log(position)
  }
  // console.log(navigator.geolocation.getCurrentPosition(successCallBack))
  // console.log(navigator)

  return (
    <section className="py-5">
      <Container>
        <Breadcrumb listProps={{ className: "ps-0 justify-content-start" }}>
          <Breadcrumb.Item linkAs={Link} href="/">
            Home
          </Breadcrumb.Item>
          <Breadcrumb.Item linkAs={Link} href="/user-account">
            Account
          </Breadcrumb.Item>
          <Breadcrumb.Item active>{data.title}</Breadcrumb.Item>
        </Breadcrumb>

        <h1 className="hero-heading mb-0">{data.title}</h1>
        <p className="text-muted mb-5">{data.subtitle}</p>
        <Row>
          <Col lg="7">
            <div className="text-block">
              <h3 className="mb-4">Login</h3>
              <Row>
                <Col sm="8">
                  <h6>Password</h6>
                  <p className="text-sm text-muted">Last updated 3 years ago</p>
                </Col>
                <Col className="text-end">
                  <Button
                    onClick={() => setLoginCollapse(!loginCollapse)}
                    variant="link"
                    className="ps-0 text-primary"
                  >
                    Update
                  </Button>
                </Col>
              </Row>
              <Collapse in={loginCollapse}>
                <Form>
                  <Row className="mt-4">
                    <Col xs="12" className="mb-4">
                      <Form.Label htmlFor="password-current">
                        Current Password
                      </Form.Label>
                      <Form.Control
                        type="password"
                        name="password-current"
                        id="password-current"
                      />
                    </Col>
                    <Col md="6" className="mb-4">
                      <Form.Label htmlFor="password-new">
                        New Password
                      </Form.Label>
                      <Form.Control
                        type="password"
                        name="password-new"
                        id="password-new"
                      />
                    </Col>
                    <Col md="6" className="mb-4">
                      <Form.Label htmlFor="password-confirm">
                        Confirm Password
                      </Form.Label>
                      <Form.Control
                        type="password"
                        name="password-confirm"
                        id="password-confirm"
                      />
                    </Col>
                  </Row>
                  <Button type="submit" variant="outline-primary">
                    Update Password
                  </Button>
                </Form>
              </Collapse>
            </div>
            <div className="text-block">
              <h3 className="mb-4">Social accounts</h3>
              <Row>
                <Col sm="8">
                  <h6>Google</h6>
                  <p className="text-sm text-muted">Connected</p>
                </Col>
                <Col className="text-end">
                  {/* <Button variant="link" className="ps-0 text-primary">
                    Disconnect
                  </Button> */}
                </Col>
              </Row>
            </div>
            <div className="text-block mb-5 mb-lg-0">
              <h3 className="mb-4">Device history</h3>
              <div className="d-flex">
                <div className="icon-rounded bg-secondary-light">
                  <Icon
                    icon="imac-screen-1"
                    className="text-secondary w-2rem h-2rem"
                  />
                </div>
                <div className="pt-2 ms-3">
                  <strong>{deviceLabel}</strong>&nbsp;
                  <Badge
                    bg="secondary-light"
                    text="secondary"
                    className="text-uppercase"
                  >
                    Current Session
                  </Badge>
                  <p className="text-sm text-muted">
                    {adjustTimeStamp(new Date())} {new Date().toLocaleTimeString()}
                  </p>
                  <Button variant="text" className="text-primary ps-0" type="submit" onClick={logOutHandler}>
                    Log out
                  </Button>
                </div>
              </div>
            </div>
          </Col>
          <Col md="6" lg="4" className="ms-lg-auto">
            <Card className="border-0 shadow">
              <Card.Header className="bg-primary-light py-4 border-0">
                <div className="d-flex align-items-center">
                  <div>
                    <h4 className="h6 subtitle text-sm text-primary">
                      {`Let's make your account more secure`}
                    </h4>
                  </div>
                  <Icon
                    icon="shield-security-1"
                    className="svg-icon-light w-3rem h-3rem ms-3 text-primary flex-shrink-0"
                  />
                </div>
              </Card.Header>
              <Card.Body className="p-4">
                <h6 className="card-text">Your account security:</h6>
                <p className="card-text mb-4">
                  <Badge bg="info-light" text="info">
                    Medium
                  </Badge>
                </p>
                <Card.Text className="text-muted">
                  We’re always working on ways to increase safety in our
                  community.{" "}
                </Card.Text>
                <Card.Text className="text-muted card-text">
                  That’s why we look at every account to make sure it’s as
                  secure as possible.
                </Card.Text>
                <hr />
                <Button variant="outline-primary" size="sm">
                  Improve
                </Button>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      </Container>
    </section>
  )
}

export default UserSecurity
