import React, { useRef } from "react"
import Link from "next/link"

import { Container, Row, Col, Button, Card, Badge } from "react-bootstrap"

import Stars from "./Stars"
import { Pagination, Parallax, Autoplay, EffectFade } from "swiper"
import "swiper/css/effect-fade"
import { Swiper, SwiperSlide } from "swiper/react"
import Image from "./CustomImage"
import Icon from "./Icon"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faAngleRight } from "@fortawesome/free-solid-svg-icons"

const RichSwiper = (props) => {
  const paginationRef = useRef(null)
  const breakpoints = []
  if (props.sm) {
    breakpoints[565] = {
      slidesPerView: props.sm,
    }
  }

  if (props.md) {
    breakpoints[768] = {
      slidesPerView: props.md,
    }
  }
  if (props.lg) {
    breakpoints[991] = {
      slidesPerView: props.lg,
    }
  }
  if (props.xl) {
    breakpoints[1200] = {
      slidesPerView: props.xl,
    }
  }
  if (props.xxl) {
    breakpoints[1400] = {
      slidesPerView: props.xxl,
    }
  }
  if (props.xxxl) {
    breakpoints[1600] = {
      slidesPerView: props.xxxl,
    }
  }
  const params = {
    className: props.className,
    slidesPerView: props.perView,
    centeredSlides: props.centeredSlides,
    modules: [Pagination, Parallax, Autoplay, EffectFade],
    autoplay: props.autoplay ? { delay: props.autoplay, disableOnInteraction: false } : false,
    effect: props.effect ?? "slide",
    fadeEffect: props.effect === "fade" ? { crossFade: true } : undefined,
    loop: props.loop,
    speed: props.speed ? props.speed : 400,
    parallax: props.parallax,
    breakpoints: breakpoints,
    pagination: {
      el: paginationRef.current ? paginationRef.current : undefined,
      type: "bullets",
      clickable: true,
      dynamicBullets: true,
    },
  }

  return props.data ? (
    <Swiper
      {...params}
      onBeforeInit={(swiper) => {
        swiper.params.pagination.el = paginationRef.current
      }}
    >
      {props.data.map((slide, index) => (
        <SwiperSlide key={slide.title} className="dark-overlay">
          <Image
            src={slide.img.startsWith("/") ? slide.img : `/content/${slide.img}`}
            layout="fill"
            className="bg-image"
            alt="Hero image"
            loading="eager"
            priority={props.priority && index === 0}
          />
          <Container className="h-100">
            <div
              data-swiper-parallax={slide.parallax}
              className="d-flex h-100 text-white overlay-content align-items-center"
            >
              <div className="w-100">
                <Row>
                  <Col lg={slide.blocks ? "12" : "6"}>
                    <p className="subtitle text-white letter-spacing-3 mb-3 fw-light">
                      {slide.subTitle}
                    </p>
                    <h2
                      style={{ lineHeight: "1" }}
                      className="display-3 fw-bold mb-3"
                    >
                      {slide.title}
                    </h2>
                    <p className="mb-5">{slide.content}</p>
                    {slide.button && (
                      <Link href={slide.buttonLink} passHref>
                        <Button
                          variant="outline-light"
                          className={slide.buttonClasses}
                        >
                          {slide.button}
                          <FontAwesomeIcon
                            icon={faAngleRight}
                            className="ms-2"
                          />
                        </Button>
                      </Link>
                    )}
                  </Col>
                  <Col
                    lg={slide.iconsRight ? "6" : "12"}
                    className="ps-lg-5 my-3 my-md-5 my-lg-0"
                  >
                    {slide.iconsRight &&
                      slide.iconsRight.map((icon) => (
                        <a
                          key={icon.title}
                          href="#"
                          className="d-flex text-reset text-decoration-none hover-animate mb-2 mb-md-5"
                        >
                          <div className="icon-rounded bg-white opacity-7 flex-shrink-0 me-4">
                            <Icon
                              icon={icon.icon}
                              className="text-dark w-2rem h-2rem"
                            />
                          </div>
                          <div>
                            <h5>{icon.title}</h5>
                            {icon.badge && (
                              <Badge text="dark" bg="light">
                                {icon.badge}
                              </Badge>
                            )}
                            {icon.content && <p>{icon.content}</p>}
                          </div>
                        </a>
                      ))}
                  </Col>
                </Row>
                {slide.blocks && (
                  <Row>
                    {slide.blocks.map((block) => (
                      <Col
                        key={block.title}
                        md="4"
                        className="d-none d-md-block mb-5"
                      >
                        <Card className="h-100 border-0 shadow-lg bg-dark hover-animate">
                          <div className="card-img-top overflow-hidden gradient-overlay">
                            <Image
                              src={`/content/${block.img}`}
                              width={400}
                              height={267}
                              layout="responsive"
                              alt={block.title}
                              className="img-fluid"
                              sizes="(max-width: 576px) 100vw, 530px"
                            />
                            <Link href={block.link} className="tile-link" />
                            <div className="card-img-overlay-top text-end">
                              <a
                                href="#"
                                className="card-fav-icon position-relative z-index-40"
                              >
                                <Icon icon="heart-1" className="text-white" />
                              </a>
                            </div>
                          </div>
                          <Card.Body className=" d-flex align-items-center">
                            <div className="w-100">
                              <Card.Title as="h6">
                                <Link
                                  href={block.link}
                                  className="text-decoration-none text-white"
                                >
                                  {block.title}
                                </Link>
                              </Card.Title>
                              <Card.Subtitle className="d-flex">
                                <p className="flex-grow-1 mb-0 text-muted text-sm">
                                  {block.location}
                                </p>
                                <p className="flex-shrink-1 mb-0 card-stars text-xs text-end">
                                  <Stars stars={block.stars} />
                                </p>
                              </Card.Subtitle>
                            </div>
                          </Card.Body>
                        </Card>
                      </Col>
                    ))}
                  </Row>
                )}
                {slide.iconsBottom && (
                  <Row className="mt-3 mt-md-5">
                    {slide.iconsBottom.map((icon) => (
                      <Col key={icon.title} md="4" className="mb-2 mb-md-0">
                        <a
                          href="#"
                          className="d-flex text-reset text-decoration-none hover-animate"
                        >
                          <div className="icon-rounded bg-white opacity-7 flex-shrink-0 me-4">
                            <Icon
                              icon={icon.icon}
                              className="text-dark w-2rem h-2rem"
                            />
                          </div>
                          <div>
                            <h5>{icon.title}</h5>
                            {icon.badge && (
                              <Badge text="light" bg="transparent">
                                {icon.badge}
                              </Badge>
                            )}
                            {icon.content && <p>{icon.content}</p>}
                          </div>
                        </a>
                      </Col>
                    ))}
                  </Row>
                )}
              </div>
            </div>
          </Container>
        </SwiperSlide>
      ))}
      <div
        ref={paginationRef}
        className={`swiper-pagination ${
          props.paginationClass ? props.paginationClass : ""
        }`}
      />
    </Swiper>
  ) : (
    "loading"
  )
}

export default RichSwiper
