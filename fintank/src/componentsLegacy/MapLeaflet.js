import React, { useEffect, useRef } from "react"
import Link from "next/link"
import {
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  Tooltip,
  Circle,
  useMap,
  useMapEvent,
} from "react-leaflet"
import { latLngBounds } from "leaflet"
import "leaflet/dist/leaflet.css"
import Stars from "./Stars"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faEnvelopeOpen, faPhone } from "@fortawesome/free-solid-svg-icons"

const MapLeaflet = (props) => {
  const tileLayers = [
    {
      tiles:
        "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
      subdomains: "abcd",
    },
    {
      tiles: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    },
    {
      tiles:
        "https://stamen-tiles-{s}.a.ssl.fastly.net/toner/{z}/{x}/{y}{r}.png",
      attribution:
        'Map tiles by <a href="http://stamen.com">Stamen Design</a>, <a href="http://creativecommons.org/licenses/by/3.0">CC BY 3.0</a> &mdash; Map data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    },
    {
      tiles: "https://mapserver.mapy.cz/base-m/{z}-{x}-{y}",
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a>, <a href="https://seznam.cz">Seznam.cz, a.s.</a>',
    },
    {
      tiles: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
      subdomains: "abcd",
    },
    {
      tiles: "https://maps.wikimedia.org/osm-intl/{z}/{x}/{y}{r}.png",
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> contributors, <a href="https://wikimediafoundation.org/wiki/Maps_Terms_of_Use">Wikimedia maps</a>',
    },
  ]

  const [hover, setHover] = React.useState(false)

  const icon = L.icon({
    iconUrl: "/content/svg/marker.svg",
    shadowUrl: "",
    iconRetinaUrl: "/content/svg/marker.svg",
    iconSize: [25, 37.5],
    popupAnchor: [0, -18],
    tooltipAnchor: [0, 19],
  })

  const highlightIcon = L.icon({
    iconUrl: "/content/svg/marker-hover.svg",
    shadowUrl: "",
    iconRetinaUrl: "/content/svg/marker-hover.svg",
    iconSize: [25, 37.5],
    popupAnchor: [0, -18],
    tooltipAnchor: [0, 19],
  })

  const markers =
    props.geoJSON &&
    props.geoJSON.features &&
    props.geoJSON.features.map((feature) => [
      feature.geometry.coordinates[1],
      feature.geometry.coordinates[0],
    ])

  const [boundsLoaded, setBoundsLoaded] = React.useState(false)
  const SetBounds = () => {
    const map = useMap()

    let markerBounds = latLngBounds(markers)

    useEffect(() => {
      markerBounds.isValid() && map.fitBounds(markerBounds) // <===== Error: Bounds are not valid.
      setBoundsLoaded(true)
    }, [])

    return null
  }
  function Focus() {
    const map = useMapEvent({
      focus: () => {
        map.scrollWheelZoom.enable()
      },
      blur: () => {
        map.scrollWheelZoom.disable()
      },
    })
    return null
  }

  // Tooltip hover style
  const tooltipRefs = useRef([])
  useEffect(() => {
    tooltipRefs.current &&
      tooltipRefs.current.forEach((item) =>
        item &&
        item._contentNode.classList.contains(
          `map-custom-tooltip-${hover || props.hoverCard}`
        )
          ? item._contentNode.classList.add("active")
          : item._contentNode.classList.remove("active")
      )
  }, [props.hoverCard, hover])

  return (
    <MapContainer
      center={props.center && props.center}
      zoom={props.zoom}
      scrollWheelZoom={false}
      className={props.className}
      dragging={props.dragging}
      tap={props.tap}
    >
      <Focus />
      <TileLayer
        url={tileLayers[0].tiles}
        attribution={tileLayers[0].attribution}
      />
      {props.geoJSON &&
        props.geoJSON.features &&
        props.geoJSON.features.map((feature, index) => {
          const data = feature.properties
          return props.popupVenue ? (
            <Marker
              key={data.id}
              position={[
                feature.geometry.coordinates[1],
                feature.geometry.coordinates[0],
              ]}
              eventHandlers={{
                popupclose: () => setHover(false),
                popupopen: () => setHover(data.id),
                mouseover: () => setHover(data.id),
                mouseout: (e) => !e.target.isPopupOpen() && setHover(false),
              }}
              icon={
                hover === data.id || props.hoverCard === feature.properties.id
                  ? highlightIcon
                  : icon
              }
            >
              <Popup className="map-custom-popup" maxWidth="600" minWidth="200">
                <div className="popup-venue">
                  {data.image ? (
                    <div
                      className={`image d-none d-md-block`}
                      style={{
                        backgroundImage: `url(/content/img/photo/${data.image})`,
                      }}
                    />
                  ) : (
                    <div className="image" />
                  )}
                  <div className="text">
                    {data.name && (
                      <h6>
                        <Link href={data.link}>
                          <a>{data.name}</a>
                        </Link>
                      </h6>
                    )}
                    {data.about && <p>{data.about}</p>}
                    {data.address && (
                      <p className="text-muted mb-1">{data.address}</p>
                    )}
                    {data.email && (
                      <p className="text-muted mb-1">
                        <FontAwesomeIcon
                          icon={faEnvelopeOpen}
                          className="fa-fw text-dark me-2"
                        />
                        <a href={`mailto:${data.email}`}>{data.email}</a>
                      </p>
                    )}
                    {data.phone && (
                      <p className="text-muted mb-1">
                        <FontAwesomeIcon
                          icon={faPhone}
                          className="fa-fw text-dark me-2"
                        />
                        {data.phone}
                      </p>
                    )}
                  </div>
                </div>
              </Popup>
            </Marker>
          ) : (
            <Marker
              key={data.id}
              icon={icon}
              opacity={0}
              position={[
                feature.geometry.coordinates[1],
                feature.geometry.coordinates[0],
              ]}
              eventHandlers={{
                popupclose: () => setHover(false),
                popupopen: () => setHover(data.id),
                mouseover: () => setHover(data.id),
                mouseout: (e) => !e.target.isPopupOpen() && setHover(false),
              }}
            >
              <Tooltip
                permanent={true}
                interactive={true}
                direction="top"
                className={`map-custom-tooltip map-custom-tooltip-${data.id}`} // Tooltip unique className
                ref={(el) => (tooltipRefs.current[index] = el)} // Tooltip refs array
              >
                ${data.price}
              </Tooltip>

              <Popup className="map-custom-popup" maxWidth="600" minWidth="200">
                <div className="popup-rental">
                  {data.image ? (
                    <div
                      className={`image d-none d-md-block`}
                      style={{
                        backgroundImage: `url(/content/img/photo/${data.image})`,
                      }}
                    />
                  ) : (
                    <div className="image" />
                  )}
                  <div className="text">
                    {data.name && (
                      <h6>
                        <Link href={data.link}>
                          <a>{data.name}</a>
                        </Link>
                      </h6>
                    )}
                    <div className="text-xs">
                      <Stars stars={data.stars} />
                    </div>
                  </div>
                </div>
              </Popup>
            </Marker>
          )
        })}
      {props.markerPosition && (
        <Marker position={props.markerPosition} icon={icon} />
      )}
      {props.circlePosition && (
        <Circle
          center={props.circlePosition}
          color={"#4E66F8"}
          fillColor={"#8798fa"}
          opacity={0.5}
          radius={props.circleRadius}
          weight={2}
        />
      )}
      {!boundsLoaded && props.geoJSON && <SetBounds />}
    </MapContainer>
  )
}

export default MapLeaflet
