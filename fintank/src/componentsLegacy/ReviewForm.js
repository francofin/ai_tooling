import React from "react"

import { Button, Collapse, Form, FormGroup, Row, Col } from "react-bootstrap"

const ReviewForm = () => {
  const [reviewCollapse, setReviewCollapse] = React.useState(false)
  return (
    <div className="py-5">
      <Button
        type="button"
        variant="outline-primary"
        onClick={() => setReviewCollapse(!reviewCollapse)}
      >
        Leave a review
      </Button>
      <Collapse id="leaveReview" className="mt-4" in={reviewCollapse}>
        <div>
          <h5 className="mb-4">Leave a review</h5>
          <Form className="form">
            <Row>
              <Col sm="6">
                <div className="mb-4">
                  <Form.Label htmlFor="name">Your name *</Form.Label>
                  <Form.Control
                    type="text"
                    name="name"
                    id="name"
                    placeholder="Enter your name"
                    required
                  />
                </div>
              </Col>
              <Col sm="6">
                <div className="mb-4">
                  <Form.Label htmlFor="rating">Your name *</Form.Label>
                  <Form.Select
                    name="rating"
                    id="rating"
                    className="focus-shadow-0"
                  >
                    <option value="5">
                      &#9733;&#9733;&#9733;&#9733;&#9733; (5/5)
                    </option>
                    <option value="4">
                      &#9733;&#9733;&#9733;&#9733;&#9734; (4/5)
                    </option>
                    <option value="3">
                      &#9733;&#9733;&#9733;&#9734;&#9734; (3/5)
                    </option>
                    <option value="2">
                      &#9733;&#9733;&#9734;&#9734;&#9734; (2/5)
                    </option>
                    <option value="1">
                      &#9733;&#9734;&#9734;&#9734;&#9734; (1/5)
                    </option>
                  </Form.Select>
                </div>
              </Col>
            </Row>
            <div className="mb-4">
              <Form.Label htmlFor="email">Your email *</Form.Label>
              <Form.Control
                type="email"
                name="email"
                id="email"
                placeholder="Enter your  email"
                required
              />
            </div>
            <div className="mb-4">
              <Form.Label htmlFor="review">Review text *</Form.Label>
              <Form.Control
                rows="4"
                type="textarea"
                name="review"
                id="review"
                placeholder="Enter your  email"
                required
              />
            </div>
            <Button type="submit">Post review</Button>
          </Form>
        </div>
      </Collapse>
    </div>
  )
}

export default ReviewForm
