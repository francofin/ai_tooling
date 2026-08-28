import React from "react"
import dynamic from "next/dynamic"
import UseWindowSize from "@hooks/UseWindowSize"

let MapLeaflet
const Map = (props) => {
  const [mapLoaded, setMapLoaded] = React.useState(false)
  const [dragging, setDragging] = React.useState(false)
  const [tap, setTap] = React.useState(false)
  const size = UseWindowSize()

  React.useEffect(() => {
    MapLeaflet = dynamic(() => import("./MapLeaflet"), {
      ssr: false,
    })
    setMapLoaded(true)
  }, [])

  React.useEffect(() => {
    if (mapLoaded) {
      setDragging(size.width > 700)
      setTap(size.width > 700)
    }
  }, [size, mapLoaded])
  return mapLoaded ? (
    <MapLeaflet dragging={dragging} tap={tap} {...props} />
  ) : (
    <p>loading</p>
  )
}

export default Map
