import React from "react";
import { Container, Row, Col } from "react-bootstrap";

/**
 * Shown when the very first static build could not reach /economic-data/.
 * After one successful build ISR keeps serving the last good page instead, so
 * a backend blip never surfaces this.
 */
const DataUnavailable = () => (
  <Container className="py-6">
    <Row>
      <Col lg="8" className="mx-auto text-center">
        <h3 className="mb-3">Market data is temporarily unavailable</h3>
        <p className="text-muted fw-light mb-0">
          We could not load the capital markets series just now. This page
          refreshes automatically, so please check back shortly.
        </p>
      </Col>
    </Row>
  </Container>
);

export default DataUnavailable;
