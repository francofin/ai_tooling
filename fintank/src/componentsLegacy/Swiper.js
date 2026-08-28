import React from "react"
import CardRestaurant from "./CardRestaurant"
import CardRoom from "./CardRoom"
import CardPoster from "./CardPoster"
import CardProperty from "./CardProperty"
import CardNews from "./CardNews"
import PriceTarget from "./PriceTarget"
import MarketReturns from "./MarketReturns"
import Sentiments from './Sentiments'
import { Navigation, Pagination, Autoplay, EffectFade, Grid } from "swiper"
import { Swiper, SwiperSlide } from "swiper/react"
import Image from "./CustomImage";
import MoverReturns from "./MoverReturns"

const SwiperComponent = (props) => {
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
    modules: [Navigation, Pagination, Autoplay, EffectFade, Grid],
    slidesPerView: props.perView ? props.perView : 1,
    effect: props.effect,
    allowTouchMove: props.allowTouchMove === false ? false : true,
    spaceBetween: props.spaceBetween ? props.spaceBetween : 0,
    centeredSlides: props.centeredSlides,
    roundLengths: props.roundLengths,
    loop: props.loop,
    speed: props.speed ? props.speed : 400,
    parallax: props.parallax,
    breakpoints: breakpoints,
    autoplay: props.autoplay,
    pagination: props.pagination !== undefined && {
      type: "bullets",
      clickable: true,
      dynamicBullets: true,
    },
    navigation: props.navigation !== undefined,
  }

  return Array.isArray(props.data) && props.data.length > 0 ? (
    <Swiper {...params}>
      {props.data.map((slide, index) =>
        props.simple ? (
          <SwiperSlide key={index}>
            <Image
              src={`/images/homeImages/${slide}`}
              layout="fill"
              className="bg-image"
              alt="Stocks to Outperform"
              loading="eager"
            />
          </SwiperSlide>
        ) : (
          <SwiperSlide key={index} className="h-auto px-2">
            {props.cards && (
              <div className="w-100 h-100 hover-animate">
                <CardRoom data={slide.properties} />
              </div>
            )}
            {props.indexReturns && (
              <div className="w-100 h-100 hover-animate">
                <MarketReturns data={slide} />
            </div>
            )}
            {props.moverReturns && (
              <div className="w-100 h-100 hover-animate">
                <MoverReturns data={slide} />
            </div>
            )}
            {props.sentimentScores && (
              <div className="w-100 h-100 hover-animate">
                <Sentiments data={slide} />
            </div>
            )}
            {props.priceTargetData && (
              <div className="w-100 h-100 hover-animate">
                <PriceTarget data={slide} />
            </div>
            )}
            {props.propertyCards && (
              <div className="w-100 h-100 hover-animate">
                <CardProperty data={slide} />
              </div>
            )}
            {props.imgCards && <CardPoster data={slide} />}
            {props.restaurantCards && (
              <div className="w-100 h-100 hover-animate">
                <CardRestaurant data={slide.properties} />
              </div>
            )}
            {props.newsCards && (
              <div className="w-100 h-100 hover-animate">
                <CardNews data={slide} onImageError={props.onImageError} onOpen={props.onOpen} />
              </div>
            )}
          </SwiperSlide>
        )
      )}
    </Swiper>
  ) : (
    "loading"
  )
}

export default SwiperComponent
