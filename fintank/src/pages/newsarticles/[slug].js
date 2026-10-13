import React, {useCallback, useEffect, useState} from "react"
import Link from "next/link"
import { Container, Row, Col, Button, Badge } from "react-bootstrap"
import Swiper from "@componentsLegacy/Swiper"
import SearchBar from "@componentsLegacy/SearchBar"
import PopularCities from "@componentsLegacy/PopularCities"
import ArticleModal from "@componentsLegacy/ArticleModal"
import Discover from "@componentsLegacy/Discover"
import Brands from "@componentsLegacy/Brands"
import data from "@data/news.json"
import { formatArticleDate } from "@utils/newsDate"
import geoJSON from "@data/restaurants-geojson.json"
import Image from "@componentsLegacy/CustomImage"
import topics from "@data/topic.json"
import axios from 'axios';
import { useRouter } from "next/router"
import bannerImages from "@data/banner.json"

import { selectImages } from "@utils/imageSelect"

export function getAllTopicIds() {
  return topics.posts.map((post) => ({
    params: {
      slug: post.slug,
    },
  }))
}

export async function getTopicData(slug) {
  for (var i = 0; i < topics.posts.length; i++) {
    if (topics.posts[i].slug == slug) {
      return {
        stockItem: topics.posts[i],
        slug
      }
    }
  }
}

export async function getServerSideProps({ params }) {
    const topic = params.slug

    let responseNews = { data: [], tag: topic }
    try {
        const res = await axios.get(`${process.env.NEXT_PUBLIC_FINTANK_API_URL}/get_articles/${topic}/`)
        responseNews = { data: Array.isArray(res.data) ? res.data : [], tag: topic }
    } catch (e) {
        console.error("News fetch failed:", e.message)
    }

    return {
        props: {
            nav: {
                light: true,
                classes: "shadow",
                color: "white",
            },
            title: "News",
            responseNews,
            topic,
        },
    }
}

const News = (props) => {

    const newsData = props.responseNews
    // const newsFromHook = useNewsGenerator(props.topic);

    // Track articles whose images fail to load at runtime, keyed by url/link.
    // A broken image can only be detected via onError, not by field presence,
    // so these are demoted from the image swiper into the text-only list.
    const [failedImageIds, setFailedImageIds] = useState(() => new Set())

    // Clicking any article (swiper card, list row, or block story) opens this
    // article in an in-place modal instead of navigating to the external site.
    const [activePost, setActivePost] = useState(null)

    const handleOpenArticle = (e, article) => {
      e.preventDefault()
      setActivePost(article)
    }

    const getArticleId = (news) => news.url || news.link

    const handleImageError = useCallback((article) => {
      const id = article?.url || article?.link
      if (!id) return
      setFailedImageIds((prev) => {
        if (prev.has(id)) return prev
        const next = new Set(prev)
        next.add(id)
        return next
      })
    }, [])

    const hasImageField = (news) => Boolean(news.image || news.thumbnail)
    const  newsDataWithImages = newsData.data.filter((news) => hasImageField(news) && !failedImageIds.has(getArticleId(news)))
    const newsNoImages = newsData.data.filter((news) => !hasImageField(news) || failedImageIds.has(getArticleId(news)))
    // const newsNoImages = newsDataWithImages.data.filter((news, i) => !news.image)
    const imagesForBanner = bannerImages.bannerImages

    const [randomImage, setRandomImage] = useState(0)

    const topicImages = selectImages(props.topic)

    useEffect(() => {
      let randomIndex = Math.floor(Math.random()*imagesForBanner.length)
      setRandomImage(randomIndex)

    }, [imagesForBanner])




  return (
    <React.Fragment>
      {data.hero && (
        <section className="d-flex align-items-center dark-overlay">
          <Image
            src={`/images/${imagesForBanner[randomImage].img}`}
            layout="fill"
            className="bg-image"
            alt="Hero image"
            loading="eager"
            priority={true}
          />
          <Container className="py-6 py-lg-7 text-white overlay-content text-center">
            <Row>
              <Col xl="10" className="mx-auto">
                <h1 className="display-3 fw-bold text-shadow">
                  {data.hero.title}
                </h1>
                <p className="text-lg text-shadow">{data.hero.subTitle}</p>
              </Col>
            </Row>
          </Container>
        </section>
      )}
      <Container>
      </Container>
      {data.popularCities && (
        <PopularCities
          title={data.popularCities.title}
          // subTitle={newsFromHook?.tag}
          subTitle={newsData.tag}
          blockStories={newsData.data.slice(0,5)}
          // blockStories={newsFromHook?.data.splice(0,5)}
          topicImage = {topicImages}
          onOpen={setActivePost}
        />
      )}
      {data.popular && (
        <section className="py-3 bg-gray-100">
          <Container>
            <div className="text-center pb-lg-4">
              <p className="subtitle text-primary">{data.popular.subTitle}</p>
              <h2 className="mb-5">{data.popular.title}</h2>
            </div>
          </Container>
          <Container fluid>
            <Swiper
              className="swiper-container-mx-negative items-slider-full px-lg-5 pt-3 pb-5"
              perView={1}
              spaceBetween={20}
              loop
              roundLengths
              md={2}
              lg={3}
              xl={4}
              xxl={5}
              xxxl={6}
              data={newsDataWithImages}
              newsCards
              onImageError={handleImageError}
              onOpen={setActivePost}
              pagination
            />

          </Container>
        </section>
      )}

      {data.travel && (
        <section className="py-6 py-lg-7 position-relative dark-overlay">
          <Image
            src={`/images/markets/marketbanner.jpg`}
            layout="fill"
            className="bg-image"
            alt={data.travel.title}
          />
          <Container>
            <div className="overlay-content text-white py-lg-5 text-center">
              <p className="subtitle text-white letter-spacing-4 mb-4">
                {data.travel.subtitle}
              </p>
              <h3 className="display-3 fw-bold text-serif text-shadow mb-5">
                {data.travel.title}
              </h3>
              <p className="lead text-shadow mb-5">{data.travel.content}</p>
            </div>
          </Container>
        </section>
      )}

      {data.bottomBlock && (
        <div className="list-group shadow mb-5">
        {newsNoImages.map((message, index) => (
          // Map through messages from json file
          <div
            key={index}
            className="list-group-item list-group-item-action p-4"
          >
            <Row>
              <Col
                xs="2"
                lg="1"
                className="align-self-lg-center py-3 d-flex align-items-lg-center"
              >
              </Col>
              <Col xs="9" lg="4" className="align-self-center mb-3 mb-lg-0">
                <div className="d-flex align-items-center mb-1 mb-lg-3">
                  <h2 className="h5 mb-0" dangerouslySetInnerHTML={{__html: `${message.name ? message.name : message.title}`}} />
                </div>
                <p className="text-sm text-muted">{message.category ? message.category : ""}</p>
                <Badge
                  pill
                  bg={"success-light"}
                  text={"success"}
                  className="p-2"
                >
                <p dangerouslySetInnerHTML ={{__html: `${message.provider ? message.provider[0].name : (message.site || message.source || '')}`}} />
                </Badge>
                <Link legacyBehavior href={message.url || message.link}>
                  <a className="stretched-link" target="_blank" onClick={(e) => handleOpenArticle(e, message)}></a>
                </Link>
              </Col>
              <Col xs="10" lg="7" className="ms-auto">
                <Row>
                  <Col md="8" className="py-3">
                    <p className="text-sm mb-0" dangerouslySetInnerHTML ={{__html: `${message.description || message.text || message.snippet || ''}`}} />
                  </Col>
                  <Col md="4" className="text-end py-3">
                    <p className="text-sm">{formatArticleDate(message)}</p>
                  </Col>
                  <Link legacyBehavior href={message.url || message.link}>
                    <a className="stretched-link" target="_blank" onClick={(e) => handleOpenArticle(e, message)}></a>
                  </Link>
                </Row>
              </Col>
            </Row>
          </div>
        ))}
      </div>
      )}

      <ArticleModal post={activePost} onHide={() => setActivePost(null)} />

    </React.Fragment>
  )
}

export default News
