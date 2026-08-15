import React, { useState } from 'react'
import { Badge, Button, Card, Form, ListGroup, Table } from 'react-bootstrap'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faXmark } from '@fortawesome/free-solid-svg-icons'

import useSymbolSearch from '@hooks/useSymbolSearch'
import { WEIGHTING_OPTIONS } from './backtestDefaults'

/**
 * Ticker typeahead, holding chips and — when the user picks custom weights —
 * a percentage column that shows its own running total.
 */
const PortfolioBuilder = ({ holdings, settings, onHoldingsChange, onSettingsChange }) => {
  const { query, setQuery, results, searching } = useSymbolSearch()
  const [notice, setNotice] = useState('')

  const addHolding = (row) => {
    if (holdings.some((holding) => holding.symbol === row.symbol)) {
      setNotice(`${row.symbol} is already in the portfolio.`)
      return
    }
    const evenSplit = Number((100 / (holdings.length + 1)).toFixed(2))
    onHoldingsChange([
      ...holdings.map((holding) => ({ ...holding, weight: evenSplit })),
      { symbol: row.symbol, name: row.name, kind: row.kind, weight: evenSplit },
    ])
    setQuery('')
    setNotice('')
  }

  const removeHolding = (symbol) => {
    onHoldingsChange(holdings.filter((holding) => holding.symbol !== symbol))
  }

  const setWeight = (symbol, weight) => {
    onHoldingsChange(holdings.map((holding) => (holding.symbol === symbol ? { ...holding, weight } : holding)))
  }

  const total = holdings.reduce((sum, holding) => sum + Number(holding.weight || 0), 0)
  const custom = settings.weightingScheme === 'custom'

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <h5 className="mb-3">Build your portfolio</h5>

        <Form.Group className="mb-2 position-relative">
          <Form.Label className="fw-bold fs-13px">Add a stock or ETF</Form.Label>
          <Form.Control
            type="text"
            value={query}
            placeholder="Search by ticker or company name…"
            onChange={(event) => setQuery(event.target.value)}
            autoComplete="off"
          />
          {results.length > 0 && (
            <ListGroup
              className="position-absolute w-100 shadow"
              style={{ zIndex: 20, maxHeight: 260, overflowY: 'auto' }}
            >
              {results.map((row) => (
                <ListGroup.Item
                  key={row.symbol}
                  action
                  onClick={() => addHolding(row)}
                  className="d-flex justify-content-between align-items-center"
                >
                  <span>
                    <strong>{row.symbol}</strong>
                    <span className="text-muted ms-2 fs-13px">{row.name}</span>
                  </span>
                  <Badge bg={row.kind === 'etf' ? 'info' : 'secondary'}>{row.kind}</Badge>
                </ListGroup.Item>
              ))}
            </ListGroup>
          )}
          {searching && <Form.Text>Searching…</Form.Text>}
          {notice && <Form.Text className="text-warning d-block">{notice}</Form.Text>}
        </Form.Group>

        {holdings.length === 0 ? (
          <p className="text-muted fs-13px mb-0">Add two or more holdings to run a backtest.</p>
        ) : (
          <Table size="sm" className="align-middle mb-3">
            <thead>
              <tr>
                <th>Holding</th>
                {custom && <th style={{ width: 140 }}>Weight %</th>}
                <th style={{ width: 40 }} />
              </tr>
            </thead>
            <tbody>
              {holdings.map((holding) => (
                <tr key={holding.symbol}>
                  <td>
                    <strong>{holding.symbol}</strong>
                    <span className="text-muted ms-2 fs-13px">{holding.name}</span>
                  </td>
                  {custom && (
                    <td>
                      <Form.Control
                        type="number"
                        min="0"
                        max="100"
                        step="0.5"
                        size="sm"
                        value={holding.weight}
                        onChange={(event) => setWeight(holding.symbol, event.target.value)}
                      />
                    </td>
                  )}
                  <td className="text-end">
                    <Button
                      variant="link"
                      className="text-danger p-0"
                      onClick={() => removeHolding(holding.symbol)}
                      aria-label={`Remove ${holding.symbol}`}
                    >
                      <FontAwesomeIcon icon={faXmark} />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
            {custom && (
              <tfoot>
                <tr>
                  <td className="fw-bold">Total</td>
                  <td className={Math.abs(total - 100) < 0.01 ? 'fw-bold text-success' : 'fw-bold text-warning'}>
                    {total.toFixed(1)}%
                  </td>
                  <td />
                </tr>
              </tfoot>
            )}
          </Table>
        )}

        {custom && Math.abs(total - 100) > 0.01 && holdings.length > 0 && (
          <p className="fs-13px text-muted">These will be scaled to add up to 100% before the backtest runs.</p>
        )}

        <Form.Group>
          <Form.Label className="fw-bold fs-13px">How should the money be split?</Form.Label>
          {WEIGHTING_OPTIONS.map((option) => (
            <Form.Check
              key={option.value}
              type="radio"
              id={`weighting-${option.value}`}
              name="weightingScheme"
              checked={settings.weightingScheme === option.value}
              onChange={() => onSettingsChange({ weightingScheme: option.value })}
              label={
                <span>
                  {option.label}
                  <span className="text-muted ms-2 fs-13px">{option.hint}</span>
                </span>
              }
            />
          ))}
        </Form.Group>
      </Card.Body>
    </Card>
  )
}

export default PortfolioBuilder
