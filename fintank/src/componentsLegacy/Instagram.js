import React from "react"
import { Container } from "react-bootstrap"
import { Swiper, SwiperSlide } from "swiper/react"
import Image from "./CustomImage"
import data from "@data/instagram.json"

const Instagram = () => {
  const params = {
    className: `instagram-slider`,
    slidesPerView: 4,
    breakpoints: {
      1900: {
        slidesPerView: 16,
      },
      1500: {
        slidesPerView: 12,
      },
      1200: {
        slidesPerView: 10,
      },
      991: {
        slidesPerView: 8,
      },
      768: {
        slidesPerView: 5,
      },
    },
  }
  return (
    <section>
      <Container fluid className="px-0">
        <Swiper {...params}>
          {data &&
            data.map((img, index) => (
              <SwiperSlide key={index} className="overflow-hidden">
                <a
                  href={img.link}
                  className="d-block"
                  style={{ lineHeight: 0 }}
                >
                  <Image
                    src={`/content/${img.img}`}
                    width={160}
                    height={160}
                    className="img-fluid hover-scale"
                    alt="..."
                  />
                </a>
              </SwiperSlide>
            ))}
        </Swiper>
      </Container>
    </section>
  )
}

export default Instagram
