import React from "react"
import { Container } from "react-bootstrap"
import Swiper from "../Swiper"
import { useHomeIndex } from "../../hooks/useHomeIndex"

const IndexReturnsSection = ({ data }) => {
  const indexData = useHomeIndex()

  if (!data.topBlocks) return null

  return (
    <section className="py-6 bg-gray-100">
      <Container>
        <div className="text-center pb-lg-4">
          <p className="subtitle text-primary">{data.topBlocks.subTitle}</p>
          <h2 className="mb-5">{data.topBlocks.title}</h2>
        </div>
        <Swiper
          className="swiper-container-mx-negative pt-3 pb-5"
          wrapperClasses="dark-overlay"
          indexReturns
          perView={1}
          md={2}
          lg={3}
          xl={4}
          data={indexData.data}
          loop
          speed={1000}
          pagination
          autoplay={{ delay: 5000 }}
        />
      </Container>
    </section>
  )
}

export default IndexReturnsSection
