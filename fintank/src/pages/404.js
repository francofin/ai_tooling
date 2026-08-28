import React from 'react';
import Link from 'next/link';
import { Container, Row, Col, Button } from 'react-bootstrap';

// The Pages Router needs its own 404 page. Without one, a `notFound: true`
// from getServerSideProps falls through to the App Router, which has no
// not-found boundary and renders a 500 instead.
const NotFound = () => (
  <section>
    <Container className="py-5 text-center">
      <Row>
        <Col lg="6" className="mx-auto">
          <h1 className="mb-3">Not found</h1>
          <p className="text-muted mb-4">
            We couldn&apos;t find that page. The symbol may not be covered by our data yet.
          </p>
          <Link href="/" passHref legacyBehavior>
            <Button variant="outline-primary">Back to home</Button>
          </Link>
        </Col>
      </Row>
    </Container>
  </section>
);

export default NotFound;
