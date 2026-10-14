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
  Alert,
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

  const emptyPasswords = { old_password: "", new_password: "", new_password2: "" }
  const [passwords, setPasswords] = React.useState(emptyPasswords)
  const [passwordErrors, setPasswordErrors] = React.useState({})
  const [passwordStatus, setPasswordStatus] = React.useState(null) // null | "saving" | "saved"

  const onPasswordChange = (field) => (e) => {
    setPasswords((p) => ({ ...p, [field]: e.target.value }))
    setPasswordErrors((errs) => ({ ...errs, [field]: undefined, detail: undefined }))
    setPasswordStatus(null)
  }

  const passwordError = (field) => {
    const value = passwordErrors[field]
    return Array.isArray(value) ? value.join(" ") : value
  }

  const submitPassword = async (e) => {
    // Never let the browser submit this form natively: a GET would put the
    // passwords in the URL, and so in history and server logs.
    e.preventDefault()

    const errors = {}
    if (!passwords.old_password) errors.old_password = "Enter your current password."
    if (!passwords.new_password) errors.new_password = "Enter a new password."
    if (passwords.new_password !== passwords.new_password2) errors.new_password2 = "Passwords do not match."
    if (Object.keys(errors).length) {
      setPasswordErrors(errors)
      return
    }

    setPasswordStatus("saving")
    try {
      const res = await fetch("/api/auth/changePassword", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(passwords),
      })
      const body = await res.json().catch(() => ({}))
      if (res.ok) {
        setPasswords(emptyPasswords)
        setPasswordErrors({})
        setPasswordStatus("saved")
        return
      }
      setPasswordStatus(null)
      if (res.status === 401) {
        setPasswordErrors({ detail: body.detail || "Your session has expired. Please log in again." })
        return
      }
      setPasswordErrors(
        Object.keys(body).length ? body : { detail: "Could not update your password. Please try again." }
      )
    } catch {
      setPasswordStatus(null)
      setPasswordErrors({ detail: "Could not reach the server. Please try again." })
    }
  }

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
    <section className="account-page py-5">
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
                  <p className="text-sm text-muted">Change the password you use to log in.</p>
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
                {/*
                  No `name` attributes on these inputs: even if this script fails
                  to load, a native submit then has nothing to put in a URL.
                */}
                <Form noValidate onSubmit={submitPassword} method="post" action="#">
                  {passwordStatus === "saved" && (
                    <Alert variant="success" className="mt-4 mb-0">
                      Password updated. Use your new password next time you log in.
                    </Alert>
                  )}
                  {passwordErrors.detail && (
                    <Alert variant="danger" className="mt-4 mb-0">
                      {passwordError("detail")}
                    </Alert>
                  )}
                  <Row className="mt-4">
                    <Col xs="12" className="mb-4">
                      <Form.Label htmlFor="password-current">
                        Current Password
                      </Form.Label>
                      <Form.Control
                        type="password"
                        id="password-current"
                        autoComplete="current-password"
                        value={passwords.old_password}
                        onChange={onPasswordChange("old_password")}
                        isInvalid={!!passwordErrors.old_password}
                      />
                      <Form.Control.Feedback type="invalid">
                        {passwordError("old_password")}
                      </Form.Control.Feedback>
                    </Col>
                    <Col md="6" className="mb-4">
                      <Form.Label htmlFor="password-new">
                        New Password
                      </Form.Label>
                      <Form.Control
                        type="password"
                        id="password-new"
                        autoComplete="new-password"
                        value={passwords.new_password}
                        onChange={onPasswordChange("new_password")}
                        isInvalid={!!passwordErrors.new_password}
                      />
                      <Form.Control.Feedback type="invalid">
                        {passwordError("new_password")}
                      </Form.Control.Feedback>
                    </Col>
                    <Col md="6" className="mb-4">
                      <Form.Label htmlFor="password-confirm">
                        Confirm Password
                      </Form.Label>
                      <Form.Control
                        type="password"
                        id="password-confirm"
                        autoComplete="new-password"
                        value={passwords.new_password2}
                        onChange={onPasswordChange("new_password2")}
                        isInvalid={!!passwordErrors.new_password2}
                      />
                      <Form.Control.Feedback type="invalid">
                        {passwordError("new_password2")}
                      </Form.Control.Feedback>
                    </Col>
                  </Row>
                  <Button type="submit" variant="outline-primary" disabled={passwordStatus === "saving"}>
                    {passwordStatus === "saving" ? "Updating…" : "Update Password"}
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
