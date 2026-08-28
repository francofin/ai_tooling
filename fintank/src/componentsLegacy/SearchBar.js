import { faCrosshairs } from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import React from "react"
import { Row, Col, Form, Button } from "react-bootstrap"
import Select from "react-select"

const SearchBar = (props) => {
  const customSelectStyles = {
    control: (provided, state) => ({
      ...provided,
      border: "0 solid #fff",
    }),
    indicatorSeparator: (provided, state) => ({
      display: "none",
    }),
    menu: (provided, state) => ({
      ...provided,
      color: "#272727",
      border: "0 solid #fff",
      boxShadow: "0 0 1.2rem rgba(0, 0, 0, .15)",
    }),
  }

  return (
    <div className={`search-bar ${props.className}`}>
      <Form action="#">
        <Row>
          <Col lg="5" className="d-flex align-items-center form-group">
            <Form.Control
              type="text"
              name="search"
              placeholder="Search Ticker"
              className="border-0 shadow-0"
            />
          </Col>
          {/* <Col
            lg="3"
            md={props.halfInputs ? "6" : "12"}
            className="d-flex align-items-center form-group"
          >
            <div className="input-label-absolute input-label-absolute-right w-100">
              <Form.Label htmlFor="location" className="label-absolute">
                <FontAwesomeIcon icon={faCrosshairs} />
                <span className="sr-only">City</span>
              </Form.Label>
              <Form.Control
                type="text"
                name="location"
                placeholder="Location"
                id="location"
                className="border-0 shadow-0"
              />
            </div>
          </Col> */}
          <Col
            lg="4"
            md={props.halfInputs ? "6" : false}
            className="d-flex align-items-center form-group no-divider"
          >
            <Select
              id={"select-" + props.id}
              options={props.options}
              placeholder="Asset Class"
              className="selectpicker w-100"
              classNamePrefix="selectpicker"
              styles={customSelectStyles}
              instanceId={"select-" + props.id}
              aria-label="Categories"
            />
          </Col>
          <Col
            lg="3"
            className={`d-grid ${props.btnMb ? `mb-${props.btnMb}` : ``}`}
          >
            <Button
              type="submit"
              className={`h-100 ${
                props.btnClassName ? props.btnClassName : ""
              }`}
            >
              Search Ticker
            </Button>
          </Col>
        </Row>
      </Form>
    </div>
  )
}

export default SearchBar
