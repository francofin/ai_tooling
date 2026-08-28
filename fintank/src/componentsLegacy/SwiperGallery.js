import Image from "./CustomImage"
import React, {useEffect, useState, useRef, useCallback} from "react"

import { Swiper, SwiperSlide } from "swiper/react"
// import Lightbox from "react-image-lightbox"
import Lightbox from "yet-another-react-lightbox"
import "yet-another-react-lightbox/styles.css"
import { Navigation, Autoplay, Pagination } from "swiper"
const SwiperGallery = (props) => {
  const data = props.data
  const [lightBoxOpen, setLightBoxOpen] = useState(false)
  const [activeImage, setActiveImage] = useState(0)
  const navigationPrevRef = useRef(null)
  const navigationNextRef = useRef(null)
  const onClick = (index) => {
    setActiveImage(index)
    setLightBoxOpen(!lightBoxOpen)
  }

  const edgeSlidesClick = useCallback((index) => {
    onClick(index)
  }, [])

useEffect(() => {
    const firstSlide = document.querySelector(".swiper-slide-prev")
    const lastSlide = document.querySelector(".swiper-slide-duplicate-next")

    firstSlide.addEventListener("click", () => edgeSlidesClick(data.length - 1))
    firstSlide.previousSibling.addEventListener("click", () =>
      edgeSlidesClick(data.length - 2)
    )
    lastSlide.addEventListener("click", () => edgeSlidesClick(1))
    lastSlide.previousSibling.addEventListener("click", () =>
      edgeSlidesClick(0)
    )
    return () => {
      firstSlide.removeEventListener("click", () => edgeSlidesClick())
      firstSlide.previousSibling.removeEventListener("click", () =>
        edgeSlidesClick()
      )
      lastSlide.addEventListener("click", () => edgeSlidesClick())
      lastSlide.previousSibling.addEventListener("click", () =>
        edgeSlidesClick()
      )
    }
  }, [edgeSlidesClick])

  const params = {
    slidesPerView: 3,
    modules: [Navigation, Autoplay],
    spaceBetween: 0,
    loop: true,
    roundLengths: true,
    centeredSlides: true,
    navigation: {
      nextEl: navigationPrevRef.current,
      prevEl: navigationPrevRef.current,
    },
    speed:2000,
    autoplay:{
      delay: 10000,
    }
  }
  const customStyles = {
    overlay: {
      zIndex: "1030",
    },
    bodyOpen: {
      position: "fixed",
    },
  }

  return (
    <React.Fragment>
      <Swiper
        {...params}
        onInit={(swiper) => {
          swiper.params.navigation.prevEl = navigationPrevRef.current
          swiper.params.navigation.nextEl = navigationNextRef.current
          swiper.navigation.init()
          swiper.navigation.update()
        }}
      >
        {data.map((item, index) => (
          <SwiperSlide key={index} className="img-gallery" style={{ cursor: "pointer" }}>
            <Image
              src={`/images/Research/${item.img}`}
              width={1350}
              height={900}
              layout="responsive"
              alt={item.alt}
              loading="eager"
              className="img-fluid img-gallery"
              sizes="35vw"
              onClick={() => onClick(index)}
            />
          </SwiperSlide>
        ))}
        <div
          ref={navigationPrevRef}
          className="swiper-button-prev swiper-button-white"
        />
        <div
          ref={navigationNextRef}
          className="swiper-button-next swiper-button-white"
        />
      </Swiper>

      {lightBoxOpen && (
        <Lightbox
          mainSrc={`/images/Research/${data[activeImage].img}`}
          nextSrc={`/images/Research/${
            data[(activeImage + 1) % data.length].img
          }`}
          prevSrc={`/images/Research/${
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

export default SwiperGallery
