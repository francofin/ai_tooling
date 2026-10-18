import React from "react"

/**
 * Fintank logo: a shark-fin mark cutting a waterline, plus the wordmark.
 *
 * Replaces public/images/homepageImages/fintank.png, which was a 899x506
 * marketing banner with the navy #181D2F baked into every pixel (the file
 * carried an alpha channel but was 100% opaque, which is why the
 * `background: transparent` on the old <img> did nothing). It was squeezed
 * into a 150x70 nav slot, so its tagline was illegible anyway.
 *
 * Drawn rather than rastered so it stays sharp at any size, carries no
 * background, and takes its colour from CSS instead of from pixels. The
 * wordmark is real text in Playfair Display -- already loaded for the whole
 * app in src/pages/_document.js -- so it is selectable, searchable, and
 * needs no font baked into a file.
 *
 *   size      height of the mark in px; the wordmark scales from it
 *   tone      "brand" (blue mark, inherits text colour) for light surfaces,
 *             "light" (sage mark, cream text) for dark ones
 *   wordmark  false renders the mark alone (favicon, tight spaces)
 */

// Mark geometry lives in a 40x40 box. The waterline strokes deliberately run
// PAST the fin on both sides and are drawn over its base: a closed shape
// beneath a triangle reads as a boat hull, open strokes through it read as a
// fin breaking the surface.
const FIN = "M10.4 27.6C15.2 24.6 19.6 17.8 24.4 5.8c1.2 8.4 2.4 15 7 21.8z"
const SURFACE = "M2 27.6Q20 29.6 38 27.6"
const WAKE = "M7.5 32.2Q20 33.7 32.5 32.2"

const TONES = {
  brand: { mark: "#4D76A3", text: null },      // text: null => inherit
  light: { mark: "#B6C691", text: "#F2EDE6" },
}

export const FintankMark = ({ size = 32, color = "currentColor", ...rest }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 40 40"
    fill="none"
    role="img"
    aria-label="Fintank"
    style={{ color, flex: "none" }}
    {...rest}
  >
    <path d={FIN} fill="currentColor" />
    <path d={SURFACE} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d={WAKE} stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" opacity="0.38" />
  </svg>
)

const Logo = ({ size = 34, tone = "brand", wordmark = true, className, style }) => {
  const palette = TONES[tone] || TONES.brand
  return (
    <span
      className={className}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: Math.round(size * 0.26),
        lineHeight: 1,
        color: palette.text || "inherit",
        ...style,
      }}
    >
      <FintankMark size={size} color={palette.mark} aria-hidden={wordmark} />
      {wordmark && (
        <span
          style={{
            fontFamily: "'Playfair Display', Georgia, 'Times New Roman', serif",
            fontWeight: 700,
            fontSize: Math.round(size * 0.82),
            letterSpacing: "-0.015em",
          }}
        >
          Fintank
        </span>
      )}
    </span>
  )
}

export default Logo
