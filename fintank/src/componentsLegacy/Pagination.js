import { faAngleLeft, faAngleRight } from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import React from "react"

import { Pagination } from "react-bootstrap"

const PaginationComponent = () => {
  return (
    <Pagination
      aria-label="Page navigation example"
      className="d-flex justify-content-center"
    >
      <Pagination.First href="#">
        <FontAwesomeIcon icon={faAngleLeft} />
      </Pagination.First>
      <Pagination.Item href="#" active>
        1
      </Pagination.Item>
      <Pagination.Item href="#">2</Pagination.Item>
      <Pagination.Item href="#">3</Pagination.Item>
      <Pagination.Last href="#">
        <FontAwesomeIcon icon={faAngleRight} />
      </Pagination.Last>
    </Pagination>
  )
}

export default PaginationComponent
s