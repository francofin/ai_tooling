/* eslint-disable @next/next/no-img-element */
import React, {useState, useEffect, useContext} from "react"
import Link from "next/link"
import swal from 'sweetalert';
import { signInWithEmailLink, updatePassword, getIdTokenResult, getAuth } from "firebase/auth";
import { AuthContext, DjangoAuthContext } from '@context/authContext';
import {fireBaseAuth} from '@utils/fireBaseUtility';
import {useRouter} from "next/router";
import { Container, Row, Col, Button, Form } from "react-bootstrap"
import Image from "@componentsLegacy/CustomImage"
import Icon from "@componentsLegacy/Icon"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faFacebookF, faGoogle } from "@fortawesome/free-brands-svg-icons"

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

const CompleteSignup = () => {

    const [email, setEmail] = useState("");
    const [firstName, setFirstName] = useState("");
    const [lastName, setLastName] = useState("");
    const [password, setPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [loading, setLoading] = useState(false);

    const {loading:djangoLoader, isAuthenticated, error, clearErrors, register, dispatch} = useContext(DjangoAuthContext);
    const router = useRouter();

    useEffect(() => {
        const userEmail = window.localStorage.getItem("fintankSignInEmail");
        setEmail(userEmail);
      }, []);


    useEffect(() => {
    if(error){
        console.log(error);
        swal({
        title: `Error, Logging In! ${error}`,
        icon: "error",
        });
        clearErrors();
    }

    // if(isAuthenticated && !loading){
    //   router.push("/");
    // }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isAuthenticated, error, loading]);


    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        const auth = getAuth();
        if(!email || !password){
          swal({
              title:"Email and password are required to complete the registration",
              icon:"error"
          });
          }
        else if(password !== confirmPassword){
            swal({
                title:"Your Passwords do no match, please try again.",
                icon:"error"
            });
        } 

        try{
          const result = await signInWithEmailLink(auth, email, window.location.href);
         
          if(result.user.emailVerified){
              window.localStorage.removeItem('fintankSignInEmail');
              let user = fireBaseAuth.currentUser;
              await updatePassword(user, password);
              const idTokenResult = await getIdTokenResult(user);
              dispatch({
                  type:'LOGGED_IN_USER',
                  payload:{email: user.email, token:idTokenResult.token}
              });
  
              register({firstName, lastName, email, password, confirmPassword}); 
          }
      } catch (err){
          console.log("Error with registering your information", err);
          setLoading(false);
          swal({
              title:`Error with registration: ${err.message}` ,
              icon:"error"
          })
  
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
              <h2>{`Complete Fintank's Registration`}</h2>
              <p className="text-muted">
                Fincancial Freedom at your Fingertips.
              </p>
            </div>
            <Form className="form-validate" onSubmit={handleSubmit}>
                <div className="mb-4">
                    <Form.Label htmlFor="loginUsername">First Name</Form.Label>
                    <Form.Control
                    name="firstName"
                    id="firstName"
                    type="text"
                    placeholder="First Name"
                    autoComplete="off"
                    value={firstName} 
                    onChange={(e) => setFirstName(e.target.value)} 
                    required
                    />
                </div>
                <div className="mb-4">
                    <Form.Label htmlFor="loginUsername">Last Name</Form.Label>
                    <Form.Control
                    name="lastName"
                    id="lastName"
                    type="text"
                    placeholder="Last Name"
                    autoComplete="off"
                    value={lastName} 
                    onChange={(e) => setLastName(e.target.value)}
                    required
                    />
                </div>
              <div className="mb-4">
                <Form.Label htmlFor="loginUsername">Email Address</Form.Label>
                <Form.Control
                  name="loginUsername"
                  id="loginUsername"
                  type="email"
                  placeholder="name@address.com"
                  autoComplete="off"
                  value={email}
                  required
                />
              </div>
              <div className="mb-4">
                <Form.Label htmlFor="loginPassword">Password</Form.Label>
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
              <div className="mb-4">
                <Form.Label htmlFor="loginPassword2">
                  Confirm your password
                </Form.Label>
                <Form.Control
                  name="loginPassword2"
                  id="loginPassword2"
                  type="password"
                  placeholder="Password"
                  value={confirmPassword} 
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                />
              </div>
              <div className="d-grid">
                <Button size="lg" type="submit">{loading && djangoLoader ? 'Loading': 'Complete Sign Up'}</Button>
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
              src={`/content/img/photo/photo-1497436072909-60f360e1d4b1.jpg`}
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

export default CompleteSignup
