import { faStar } from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import React from "react"

const Stars = (props) => {
  const starsArray = []
  for (let i = 1; i <= 5; i++) {
    i <= props.stars
      ? starsArray.push(
          <FontAwesomeIcon
            key={i}
            icon={faStar}
            size={props.size ? props.size : "1x"}
            className={props.color ? props.color : "text-warning"}
          />
        )
      : starsArray.push(
          <FontAwesomeIcon
            key={i}
            icon={faStar}
            size={props.size ? props.size : "1x"}
            className="text-gray-300"
          />
        )
  }
  return starsArray
}

export default Stars
