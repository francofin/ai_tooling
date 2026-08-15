import React from 'react'
import { Card, Col, Form, InputGroup, Row } from 'react-bootstrap'

import { CONTRIBUTION_OPTIONS, PERIOD_OPTIONS, REBALANCE_OPTIONS } from './backtestDefaults'

/** Period, rebalance cadence, starting amount and deposits. */
const BacktestSettings = ({ settings, onChange }) => (
  <Card className="border-0 shadow-sm mb-4">
    <Card.Body>
      <h5 className="mb-3">Set up the simulation</h5>
      <Row className="g-3">
        <Col md={6}>
          <Form.Label className="fw-bold fs-13px">How far back?</Form.Label>
          <Form.Select
            value={settings.periodYears}
            onChange={(event) => onChange({ periodYears: Number(event.target.value) })}
          >
            {PERIOD_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Form.Select>
        </Col>
        <Col md={6}>
          <Form.Label className="fw-bold fs-13px">Rebalance</Form.Label>
          <Form.Select
            value={settings.rebalanceFrequency}
            onChange={(event) => onChange({ rebalanceFrequency: event.target.value })}
          >
            {REBALANCE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Form.Select>
        </Col>
        <Col md={4}>
          <Form.Label className="fw-bold fs-13px">Starting amount</Form.Label>
          <InputGroup>
            <InputGroup.Text>$</InputGroup.Text>
            <Form.Control
              type="number"
              min="1"
              step="500"
              value={settings.initialAmount}
              onChange={(event) => onChange({ initialAmount: event.target.value })}
            />
          </InputGroup>
        </Col>
        <Col md={4}>
          <Form.Label className="fw-bold fs-13px">Regular deposit</Form.Label>
          <InputGroup>
            <InputGroup.Text>$</InputGroup.Text>
            <Form.Control
              type="number"
              min="0"
              step="50"
              value={settings.periodicContribution}
              onChange={(event) => onChange({ periodicContribution: event.target.value })}
            />
          </InputGroup>
        </Col>
        <Col md={4}>
          <Form.Label className="fw-bold fs-13px">Deposit how often?</Form.Label>
          <Form.Select
            value={settings.contributionFrequency}
            onChange={(event) => onChange({ contributionFrequency: event.target.value })}
          >
            {CONTRIBUTION_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Form.Select>
        </Col>
        <Col md={6}>
          <Form.Label className="fw-bold fs-13px">Compare against</Form.Label>
          <Form.Control
            type="text"
            value={settings.benchmarkSymbol}
            onChange={(event) => onChange({ benchmarkSymbol: event.target.value.toUpperCase() })}
          />
          <Form.Text>A ticker such as SPY, VTI or AGG.</Form.Text>
        </Col>
      </Row>
    </Card.Body>
  </Card>
)

export default BacktestSettings
