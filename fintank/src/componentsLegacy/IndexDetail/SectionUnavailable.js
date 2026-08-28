import React from "react"

/**
 * Inline empty state for a single section.
 *
 * Each section degrades on its own: a universe with no constituent list (or a
 * failed fetch) loses that section and nothing else. The old page had no empty
 * state at all -- it unhid sections before their data arrived and rendered
 * blank canvases.
 */
const SectionUnavailable = ({ title, message }) => (
  <div className="text-block py-3">
    {title && <h6 className="mb-2">{title}</h6>}
    <p className="text-muted fw-light mb-0">{message}</p>
  </div>
)

export default SectionUnavailable
