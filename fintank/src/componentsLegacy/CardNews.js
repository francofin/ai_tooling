import React, {useState} from "react"
import Link from "next/link"
import { Card, Badge } from "react-bootstrap"
import Stars from "@componentsLegacy/Stars"
import Image from "./CustomImage"
import Icon from "./Icon"
import marketImages from "@data/markets.json"

const CardNews = (props) => {
  const data = props.data
  const [articleData, setArticleData] = useState(data)


  // useEffect(() => {
  //   setArticleData(data)


  // }, [data])

//   console.log("props", articleData)

  const imgUrl = articleData?.image?.thumbnail?.contentUrl || articleData?.thumbnail || articleData?.image
  const imageSrc = imgUrl ? `/api/imagefetcher?url=${encodeURIComponent(imgUrl)}` : `/images/${marketImages.marketImages[5].img}`

  const handleImageError = () => {
    // Only demote articles that actually had a real image URL; the static
    // fallback image loading fine should never move a card to the text list.
    if (imgUrl) {
      props.onImageError?.(data)
    }
  }

  const handleOpen = (e) => {
    // When a modal handler is supplied, open it in-place instead of navigating
    // to the external article; otherwise keep the default external behavior.
    if (!props.onOpen) return
    e.preventDefault()
    props.onOpen(data)
  }


  return (
    <Card className="h-100 border-0 shadow">
      <div
        style={{
          minHeight: "200px",
        }}
        className="card-img-top overflow-hidden dark-overlay"
      >
        <Image
          src={imageSrc}
          layout="fill"
          className="bg-image"
          alt={data?.name || data?.title}
          sizes={props.sizes || "(max-width:576px) 100vw, (max-width:991px) 50vw, 280px"}
          onError={handleImageError}
        />
        
        <Link legacyBehavior href={data?.url || data?.link}>
          <a className="tile-link" onClick={handleOpen} />
        </Link>
        <div className="card-img-overlay-bottom z-index-20">
          <h5 className="text-white text-shadow" dangerouslySetInnerHTML={{__html: `${(data?.name || data?.title || '').slice(0,60)}`}} />
          <p className="text-white mb-2 text-xs" dangerouslySetInnerHTML ={{__html: `${data?.provider?.[0]?.name || data?.site || data?.source || ''}`}} />
        </div>
        <div className="card-img-overlay-top d-flex justify-content-between align-items-center">
          <Badge pill bg="transparent" className="px-3 py-2">
            {data?.category ? data?.category : " "}
          </Badge>
        </div>
      </div>
      <Card.Body>
        <p className="text-sm text-muted mb-3" dangerouslySetInnerHTML ={{__html: `${(data?.description || data?.text || data?.snippet || data?.content || '').substring(0, 115)}...`}} />
          
        {/* <p className="text-sm mb-0">
          {data.tags.map((tag, index) => (
            <a key={index} className="me-1" href="#">
              {tag}
              {index < data.tags.length - 1 && ","}
            </a>
          ))}
        </p> */}
      </Card.Body>
    </Card>
  )
}

export default CardNews
