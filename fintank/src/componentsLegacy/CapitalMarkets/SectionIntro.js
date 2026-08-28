import React from "react";
import { Row, Col } from "react-bootstrap";

const SectionIntro = ({ title, children }) => (
  <Row className="pt-3">
    <Col lg="12">
      <div className="text-block">
        <h3 className="mb-3">{title}</h3>
        <p className="text-muted fw-light">{children}</p>
      </div>
    </Col>
  </Row>
);

export default SectionIntro;
