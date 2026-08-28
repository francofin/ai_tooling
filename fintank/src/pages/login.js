/* eslint-disable @next/next/no-img-element */
import Link from "next/link"
import { DjangoAuthContext } from '@context/authContext';
import React, {useState, useEffect, useContext} from 'react';
import { useRouter } from 'next/router';
import { Container, Row, Col, Button, Form } from "react-bootstrap"
import Image from "@componentsLegacy/CustomImage"
import Icon from "@componentsLegacy/Icon"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faFacebookF, faGoogle } from "@fortawesome/free-brands-svg-icons"
import swal from 'sweetalert';
import {fireBaseAuth, googleAuthProvider, facebookAuthProvider} from '@utils/fireBaseUtility';
import { signInWithEmailAndPassword, signInWithPopup, getIdTokenResult } from "firebase/auth";

export async function getStaticProps() {
  return {
    props: {
      title: "Sign in",
      hideHeader: true,
      hideFooter: true,
      noPaddingTop: true,
    },
  }
}

const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState(''); 
  const [loading, setLoading] = useState(false)

  const router = useRouter();
  const auth = fireBaseAuth;
  const {loading:DjangoLoader, isAuthenticated, error, login, clearErrors, dispatch} = useContext(DjangoAuthContext);

  useEffect(() => {
    if(error){
      console.log(error);
      swal({
        title: `Error, Logging In! ${error}`,
        icon: "error",
      });
      clearErrors();
    }

    if(isAuthenticated && DjangoLoader){
      router.push("/");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, error, DjangoLoader])


  const handleOnSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    try{
      await signInWithEmailAndPassword(auth, email, password)
        .then(async (result) => {
          const {user} = result;
          const idTokenResult = await getIdTokenResult(user);
          dispatch({
            type:'LOGGED_IN_USER',
            payload:{email: user.email, token:idTokenResult.token}
        });   
      });

      setLoading(false);
      

    } catch (err){
      console.log(err)
      swal({
        title:"Incorrect details, please review your login Credentials",
        icon: "error"
      })
    }
    
    login({username:email, password});
  }


  const logInWithGoogle = async (e) => {
    e.preventDefault();
    setLoading(true);

    try{
      await signInWithPopup(auth, googleAuthProvider)
      .then( async (result) => {
        console.log("Google Auth", result);
        const {user} = result;
        const idTokenResult = await getIdTokenResult(user);
        dispatch({
          type:'LOGGED_IN_USER',
          payload:{email: user.email, token:idTokenResult.token}
      });

      login({username:email, password});
      router.push('/');
      })

    }
    catch(err){
      swal({
        title:`Please review your Google login Credentials. ${err}`,
        icon: "error"
      })
    }
    
  }

  return (
    <Container fluid className="px-3">
      <Row className="min-vh-100">
        <Col md="8" lg="6" xl="5" className="d-flex align-items-center">
          <div className="w-100 py-5 px-md-5 px-xl-6 position-relative">
            <div className="mb-5">
              <img
                src="/images/homepageImages/fintank7.jpg"
                alt="..."
                style={{
                  maxWidth: "15rem",
                  borderRadius:"10px"
                }}
                className="img-fluid mb-3"
              />
              <h2>Welcome back</h2>
            </div>
            <Form className="form-validate" onSubmit={handleOnSubmit}>
              <div className="mb-4">
                <Form.Label htmlFor="loginUsername">Email Address</Form.Label>
                <Form.Control
                  name="loginUsername"
                  id="loginUsername"
                  type="email"
                  placeholder="name@address.com"
                  autoComplete="off"
                  required
                  value={email} 
                  onChange={(e) => setEmail(e.target.value)} 
                />
              </div>
              <div className="mb-4">
                <Row>
                  <Col>
                    <Form.Label htmlFor="loginPassword">Password</Form.Label>
                  </Col>
                  <Col xs="auto">
                    <a href="#" className="form-text small text-primary">
                      Forgot password?
                    </a>
                  </Col>
                </Row>
                <Form.Control
                  name="loginPassword"
                  id="loginPassword"
                  type="password"
                  placeholder="Password"
                  value={password} 
                  onChange={(e) => setPassword(e.target.value)} 
                  required
                />
              </div>
              {/* <div className="mb-4">
                <Form.Check
                  name="loginRemember"
                  id="loginRemember"
                  type="checkbox"
                  className="text-muted"
                  label={
                    <span className="text-sm">Remember me for 30 days</span>
                  }
                />
              </div> */}
              <div className="d-grid">
                <Button size="lg" type="submit">Sign in</Button>
              </div>
            </Form>
            <hr data-content="Thank You For Trusting Fintank For Your Investing Needs" className="my-3 hr-text letter-spacing-2" />
            <div className="d-grid gap-2">
              <Button variant="outline-muted" className="btn-social"  type="submit" onClick={logInWithGoogle}>
                <FontAwesomeIcon
                  icon={faGoogle}
                  size="2x"
                  className="btn-social-icon"
                />
                Connect <span className="d-none d-sm-inline">with Google</span>
              </Button>
            </div>

            <hr className="my-4" />
            <p className="text-center">
              <small className="text-muted text-center">{`Don't have an account yet?`}&nbsp;
                <Link legacyBehavior href="/signup">
                  <a>Sign Up</a>
                </Link>
              </small>
            </p>

            <Link legacyBehavior href="/">
              <a className="close-absolute me-md-5 me-xl-6 pt-5">
                <Icon icon="close-1" className="w-3rem h-3rem" />
              </a>
            </Link>
          </div>
        </Col>
        <Col md="4" lg="6" xl="7" className="d-none d-md-block">
          <div className="bg-cover h-100 me-n3  position-relative">
            <Image
              src={`/images/homepageImages/login4.jpg`}
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

export default Login
