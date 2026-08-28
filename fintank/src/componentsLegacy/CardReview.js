import React from "react"

import Stars from "./Stars"
import Avatar from "./Avatar"

const CardReview = (props) => {
  const data = props.data
  return (
    <div className="d-flex d-block d-sm-flex review">
      <div className="text-md-center me-4 me-xl-5">
        <Avatar size="xl" image={`/content/img/avatar/${data.avatar}`} border />

        <span className="text-uppercase text-muted text-sm">{data.date}</span>
      </div>
      <div>
        <h6 className="mt-2 mb-1">{data.title}</h6>
        <div className="mb-2">
          <Stars size="xs" color="text-primary" stars={data.stars} />
        </div>
        <p className="text-muted text-sm">{data.content}</p>
      </div>
    </div>
  )
}

export default CardReview
