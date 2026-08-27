import React, { useMemo, useRef, useState } from 'react'
import { Badge, Button, Form, ListGroup } from 'react-bootstrap'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faXmark } from '@fortawesome/free-solid-svg-icons'
import { useStockNames } from '@hooks/useStockNames'
import { MAX_SYMBOLS } from '@utils/technicalSpec'

const MAX_SUGGESTIONS = 8

/**
 * Autocomplete plus chips, capped at MAX_SYMBOLS and deduplicated.
 *
 * Uses the public `useStockNames` (/all-stock-names/), not `useSymbolSearch`,
 * whose endpoint is IsAuthenticated -- this page is public.
 *
 * The page this replaces stored a whole suggestion *object* when the user
 * pressed Enter and `item['symbol']` when they clicked, so keyboard and mouse
 * produced different types; and it re-filtered the entire universe on every
 * keystroke with no memo and no cap. One selection path and a memo fix both.
 */
const TickerPicker = ({ symbols, onChange }) => {
  // /all-stock-names/ returns { stocks: [...] }, not a bare array -- reading
  // `data` directly would make every isArray check false and the autocomplete
  // would silently never suggest anything.
  const { data } = useStockNames()
  const universe = data?.stocks
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const inputRef = useRef(null)
  const full = symbols.length >= MAX_SYMBOLS

  const suggestions = useMemo(() => {
    const term = query.trim().toUpperCase()
    if (!term || !Array.isArray(universe)) return []
    return universe
      .filter((item) => {
        const symbol = (item.symbol ?? '').toUpperCase()
        const name = (item.name ?? '').toUpperCase()
        return !symbols.includes(symbol) && (symbol.startsWith(term) || name.includes(term))
      })
      .slice(0, MAX_SUGGESTIONS)
  }, [query, universe, symbols])

  const add = (item) => {
    const symbol = (item?.symbol ?? '').toUpperCase()
    if (!symbol || full || symbols.includes(symbol)) return
    onChange([...symbols, symbol])
    setQuery('')
    setActive(0)
  }

  const remove = (symbol) => onChange(symbols.filter((s) => s !== symbol))

  const onKeyDown = (event) => {
    if (!suggestions.length) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((i) => Math.min(i + 1, suggestions.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((i) => Math.max(i - 1, 0))
    } else if (event.key === 'Home') {
      event.preventDefault()
      setActive(0)
    } else if (event.key === 'End') {
      event.preventDefault()
      setActive(suggestions.length - 1)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      add(suggestions[active])
    } else if (event.key === 'Escape') {
      setQuery('')
      setActive(0)
    }
  }

  return (
    <div className="ticker-picker">
      <Form.Label htmlFor="ticker-search">Compare tickers</Form.Label>
      <Form.Control
        id="ticker-search"
        ref={inputRef}
        role="combobox"
        aria-expanded={suggestions.length > 0}
        aria-controls="ticker-suggestions"
        aria-activedescendant={suggestions.length ? `ticker-option-${active}` : undefined}
        aria-autocomplete="list"
        autoComplete="off"
        disabled={full}
        placeholder={full ? `Maximum ${MAX_SYMBOLS} tickers` : 'Search a ticker'}
        value={query}
        onChange={(event) => {
          setQuery(event.target.value)
          setActive(0)
        }}
        onKeyDown={onKeyDown}
      />

      {suggestions.length > 0 && (
        <ListGroup id="ticker-suggestions" role="listbox" className="mt-1 shadow-sm">
          {suggestions.map((item, index) => (
            <ListGroup.Item
              key={item.symbol}
              id={`ticker-option-${index}`}
              role="option"
              aria-selected={index === active}
              action
              active={index === active}
              onMouseEnter={() => setActive(index)}
              onClick={() => add(item)}
            >
              <strong>{item.symbol}</strong> <span className="text-muted small">{item.name}</span>
            </ListGroup.Item>
          ))}
        </ListGroup>
      )}

      <div className="d-flex flex-wrap gap-2 mt-3">
        {symbols.map((symbol) => (
          <Badge key={symbol} bg="light" text="dark" className="d-flex align-items-center gap-1">
            {symbol}
            <Button
              variant="link"
              size="sm"
              className="p-0 lh-1"
              aria-label={`Remove ${symbol}`}
              onClick={() => remove(symbol)}
            >
              <FontAwesomeIcon icon={faXmark} />
            </Button>
          </Badge>
        ))}
      </div>
    </div>
  )
}

export default TickerPicker
