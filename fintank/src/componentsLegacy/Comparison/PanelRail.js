import React, { useCallback, useEffect, useRef, useState } from 'react'
import SymbolPanel from './SymbolPanel'

/**
 * Panels sit on one horizontal axis and the user pans across them. This
 * honours "side by side" literally at all five tickers, where a wrapping grid
 * would break the row at exactly the count the 5-cap exists to serve.
 *
 * A horizontal scroller is invisible until discovered and this one is the
 * primary navigation for the whole feature, so the scrollbar is always
 * visible, the edges fade, and arrow keys work -- native scroll containers get
 * no arrow-key handling when the focused element is inside a child.
 */
const PanelRail = ({ symbols, spec, onRemove }) => {
  const rail = useRef(null)
  const [edges, setEdges] = useState({ left: false, right: false })

  const measure = useCallback(() => {
    const node = rail.current
    if (!node) return
    setEdges({
      left: node.scrollLeft > 8,
      right: node.scrollLeft + node.clientWidth < node.scrollWidth - 8,
    })
  }, [])

  useEffect(() => {
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [measure, symbols.length])

  const step = (direction) => {
    const node = rail.current
    if (!node) return
    const panel = node.querySelector('.symbol-panel')
    const width = panel ? panel.getBoundingClientRect().width : node.clientWidth
    node.scrollBy({ left: direction * width, behavior: 'smooth' })
  }

  const onKeyDown = (event) => {
    const node = rail.current
    if (!node) return
    if (event.key === 'ArrowRight') {
      event.preventDefault()
      step(1)
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault()
      step(-1)
    } else if (event.key === 'Home') {
      event.preventDefault()
      node.scrollTo({ left: 0, behavior: 'smooth' })
    } else if (event.key === 'End') {
      event.preventDefault()
      node.scrollTo({ left: node.scrollWidth, behavior: 'smooth' })
    }
  }

  return (
    <div className={`panel-rail-wrap${edges.left ? ' has-left' : ''}${edges.right ? ' has-right' : ''}`}>
      <div
        ref={rail}
        className="panel-rail"
        role="region"
        aria-label="Ticker comparison panels. Use the left and right arrow keys to move between tickers."
        tabIndex={0}
        onScroll={measure}
        onKeyDown={onKeyDown}
      >
        {symbols.map((symbol) => (
          <SymbolPanel key={symbol} symbol={symbol} spec={spec} onRemove={onRemove} root={rail} />
        ))}
      </div>
    </div>
  )
}

export default PanelRail
