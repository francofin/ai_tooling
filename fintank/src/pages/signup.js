/* eslint-disable @next/next/no-img-element */
import React, {useEffect, useState} from "react"
import Link from "next/link"
import {fireBaseAuth} from '@utils/fireBaseUtility';
import { sendSignInLinkToEmail } from "firebase/auth";
import { Container, Row, Col, Button, Form } from "react-bootstrap"
import Image from "@componentsLegacy/CustomImage"
import Icon from "@componentsLegacy/Icon"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faFacebookF, faGoogle } from "@fortawesome/free-brands-svg-icons"
import swal from 'sweetalert';
export async function getStaticProps() {
  return {
    props: {
      title: "Sign up",
      hideHeader: true,
      hideFooter: true,
      noPaddingTop: true,
    },
  }
}

const Signup = () => {

  const [email, setEmail] = useState(null);
  const [confirmEmail, setConfirmEmail] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async(e) =>{
    e.preventDefault();
    if(email === confirmEmail){
      setLoading(true);
        const auth = fireBaseAuth;
        const config = {
          url: process.env.NEXT_PUBLIC_CONFIRMATION_EMAIL_REDIRECT,
          handleCodeInApp: true
        }
      await sendSignInLinkToEmail(auth, email, config);
      window.localStorage.setItem('fintankSignInEmail', email);
      swal({
        title: `Success, Email sent to ${email}, Please check your email to complete your registration!`,
        icon: "success",
      });
      setEmail("");
      setConfirmEmail("");
      setLoading(false);  
    } else {
        swal({
          title:"Your Emails do no match, please check these values again.",
          icon:"error"
      });
    }
      
   }


  return (
    <Container fluid className="px-3">
      <Row className="min-vh-100">
        <Col md="8" lg="6" xl="5" className="d-flex align-items-center">
          <div className="w-100 py-5 px-md-5 px-xxl-6 position-relative">
            <div className="mb-4">
              <img
                src="/images/homepageImages/fintank7.jpg"
                alt="..."
                style={{ maxWidth: "15rem",
                borderRadius:"10px" }}
                className="img-fluid mb-3"
              />
              <h2>Sign up</h2>
              <p className="text-muted">
                Financial Freedom At Your Fingertips!
              </p>
            </div>
            <Form className="form-validate" onSubmit={handleSubmit}>
              <div className="mb-4">
                <Form.Label htmlFor="loginUsername">Email Address</Form.Label>
                <Form.Control
                  name="loginUsername"
                  id="loginUsername"
                  type="email"
                  value={email}
                  placeholder="name@address.com"
                  autoComplete="off"
                  required
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="mb-4">
                <Form.Label htmlFor="loginUsername">Confirm Email Address</Form.Label>
                <Form.Control
                  name="loginUsername"
                  id="loginUsername"
                  type="email"
                  value={confirmEmail}
                  placeholder="name@address.com"
                  autoComplete="off"
                  required
                  onChange={(e) => setConfirmEmail(e.target.value)}
                />
              </div>
              <div className="d-grid">
                <Button type="submit" size="lg" disabled={!email || loading}>Sign up</Button>
              </div>
            </Form>
            <hr data-content="Thank You For Trusting Fintank For Your Investing Needs" className="my-3 hr-text letter-spacing-2" />
            {/* <div className="d-grid gap-2">
              <Button variant="outline-muted" className="btn-social">
                <FontAwesomeIcon
                  icon={faGoogle}
                  size="2x"
                  className="btn-social-icon"
                />
                Connect <span className="d-none d-sm-inline">with Google</span>
              </Button>
            </div> */}
            <hr className="my-4" />
            <p className="text-sm text-muted">
              {`By signing up you agree to Fintank's`}{" "}
              <a href="#">Terms and Conditions</a> and{" "}
              <a href="#">Privacy Policy</a>.
            </p>

            <Link legacyBehavior href="/">
              <a className="close-absolute me-md-5 me-xl-6 pt-5">
                <Icon icon="close-1" className="w-3rem h-3rem" />
              </a>
            </Link>
          </div>
        </Col>
        <Col md="4" lg="6" xl="7" className="d-none d-md-block">
          <div className="bg-cover h-100 me-n3 position-relative">
            <Image
              src={`/images/homepageImages/login2.jpg`}
              alt=""
              className="bg-image"
              loading="eager"
              layout="fill"
              priority={true}
            />
          </div>
        </Col>
      </Row>
    </Container>
  )
}

export default Signup
