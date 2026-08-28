import React from "react"

import { Row, Col } from "react-bootstrap"

import Lightbox from "react-image-lightbox"
import "react-image-lightbox/style.css"
import Image from "./CustomImage"

const Gallery = (props) => {
  const data = props.data
  const [lightBoxOpen, setLightBoxOpen] = React.useState(false)
  const [activeImage, setActiveImage] = React.useState(0)

  const onClick = (index) => {
    setActiveImage(index)
    setLightBoxOpen(!lightBoxOpen)
  }
  const customStyles = {
    overlay: {
      zIndex: "1040",
    },
    bodyOpen: {
      position: "fixed",
    },
  }
  return (
    <React.Fragment>
      <Row className={props.rowClasses}>
        {data.map((item, index) => (
          <Col
            key={index}
            xs={props.xs}
            sm={props.sm}
            md={props.md}
            lg={props.lg}
            xl={props.xl}
            className={props.colClasses}
          >
            <Image
              key={index}
              src={`/content/img/photo/${item.img}`}
              width={1350}
              height={900}
              alt={item.alt}
              layout="responsive"
              className="img-fluid img-gallery"
              sizes="(max-width:991px) 50vw, 240px"
              onClick={() => onClick(index)}
            />
          </Col>
        ))}
      </Row>

      {lightBoxOpen && (
        <Lightbox
          mainSrc={`/content/img/photo/${data[activeImage].img}`}
          nextSrc={`/content/img/photo/${
            data[(activeImage + 1) % data.length].img
          }`}
          prevSrc={`/content/img/photo/${
            data[(activeImage + data.length - 1) % data.length].img
          }`}
          onCloseRequest={() => setLightBoxOpen(false)}
          imageCaption={data[activeImage].title}
          onMovePrevRequest={() =>
            setActiveImage((activeImage + data.length - 1) % data.length)
          }
          onMoveNextRequest={() =>
            setActiveImage((activeImage + 1) % data.length)
          }
          enableZoom={false}
          reactModalStyle={customStyles}
        />
      )}
    </React.Fragment>
  )
}

export default Gallery
