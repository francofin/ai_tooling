import React from "react"
import Link from "next/link"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faArrowTrendUp, faArrowTrendDown } from "@fortawesome/free-solid-svg-icons"
import { useHomeIndex } from "../../hooks/useHomeIndex"

const IndexReturnsSidePanel = () => {
  const { data: response } = useHomeIndex()
  const quotes = Array.isArray(response?.data) ? response.data : []

  if (quotes.length === 0) return null

  const items = quotes.slice(0, 7)

  return (
    <div
      className="d-none d-lg-flex flex-column"
      style={{
        position: "absolute",
        right: "2.5rem",
        top: "50%",
        transform: "translateY(-50%)",
        zIndex: 40,
        width: "330px",
        background: "rgba(10, 10, 20, 0.82)",
        borderRadius: "8px",
        backdropFilter: "blur(6px)",
        border: "1px solid rgba(255,255,255,0.1)",
      }}
    >
      <div className="px-3 pt-3 pb-1">
        <p
          className="text-uppercase mb-0"
          style={{ fontSize: "0.65rem", letterSpacing: "0.15em", color: "rgba(255,255,255,0.5)" }}
        >
          Market Indices
        </p>
      </div>
      {items.map((item, i) => {
        const positive = item.changesPercentage >= 0
        const isLast = i === items.length - 1
        return (
          <Link key={item.symbol} href={`/index-chart/${item.symbol}`} legacyBehavior>
            <a
              className="text-decoration-none d-flex align-items-center px-3 py-3"
              style={{
                borderBottom: isLast ? "none" : "1px solid rgba(255,255,255,0.07)",
                transition: "background 0.15s",
              }}
            >
              <FontAwesomeIcon
                icon={positive ? faArrowTrendUp : faArrowTrendDown}
                style={{ color: positive ? "#22c55e" : "#ef4444", width: "14px", flexShrink: 0 }}
                className="me-3"
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                  className="fw-semibold text-white"
                  style={{ fontSize: "0.82rem", lineHeight: 1.2 }}
                >
                  {item.symbol}
                </div>
                <div
                  style={{
                    fontSize: "0.68rem",
                    color: "rgba(255,255,255,0.45)",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {item.name}
                </div>
              </div>
              <div className="text-end ms-2" style={{ flexShrink: 0 }}>
                <div className="text-white" style={{ fontSize: "0.82rem", lineHeight: 1.2 }}>
                  ${Number(item.price).toFixed(2)}
                </div>
                <div
                  style={{
                    fontSize: "0.72rem",
                    color: positive ? "#22c55e" : "#ef4444",
                    lineHeight: 1.2,
                  }}
                >
                  {positive ? "+" : ""}
                  {Number(item.changesPercentage).toFixed(2)}%
                </div>
              </div>
            </a>
          </Link>
        )
      })}
    </div>
  )
}

export default IndexReturnsSidePanel
