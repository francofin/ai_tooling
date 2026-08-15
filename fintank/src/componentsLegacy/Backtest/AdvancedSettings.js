import React, { useState } from 'react'
import { Button, Card, Collapse, Col, Form, InputGroup, Row } from 'react-bootstrap'

import { BACKTEST_MODE_OPTIONS, COVARIANCE_OPTIONS, INCEPTION_OPTIONS } from './backtestDefaults'

/**
 * Everything a novice should not have to see. Collapsed by default — the point
 * of progressive disclosure is that the defaults are already right.
 */
const AdvancedSettings = ({ settings, onChange }) => {
  const [open, setOpen] = useState(false)

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <Button variant="link" className="p-0 text-decoration-none" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? '▾' : '▸'} Advanced settings
        </Button>

        <Collapse in={open}>
          <div className="pt-3">
            <Row className="g-3">
              <Col md={12}>
                <Form.Label className="fw-bold fs-13px">When should the weights be chosen?</Form.Label>
                {BACKTEST_MODE_OPTIONS.map((option) => (
                  <Form.Check
                    key={option.value}
                    type="radio"
                    id={`mode-${option.value}`}
                    name="backtestMode"
                    checked={settings.backtestMode === option.value}
                    onChange={() => onChange({ backtestMode: option.value })}
                    label={
                      <span>
                        {option.label}
                        <span className="text-muted ms-2 fs-13px">{option.hint}</span>
                      </span>
                    }
                  />
                ))}
              </Col>

              <Col md={12}>
                <Form.Label className="fw-bold fs-13px">When holdings have different start dates</Form.Label>
                {INCEPTION_OPTIONS.map((option) => (
                  <Form.Check
                    key={option.value}
                    type="radio"
                    id={`inception-${option.value}`}
                    name="inceptionPolicy"
                    checked={settings.inceptionPolicy === option.value}
                    onChange={() => onChange({ inceptionPolicy: option.value })}
                    label={
                      <span>
                        {option.label}
                        <span className="text-muted ms-2 fs-13px">{option.hint}</span>
                      </span>
                    }
                  />
                ))}
                <Form.Check
                  type="checkbox"
                  id="enterImmediately"
                  className="mt-2"
                  checked={settings.enterImmediately}
                  onChange={(event) => onChange({ enterImmediately: event.target.checked })}
                  label={
                    <span>
                      Buy a new holding the day it becomes available
                      <span className="text-muted ms-2 fs-13px">
                        Otherwise it waits for the next rebalance, which is what a real investor would do.
                      </span>
                    </span>
                  }
                />
              </Col>

              <Col md={6}>
                <Form.Label className="fw-bold fs-13px">Risk estimate</Form.Label>
                <Form.Select
                  value={settings.covarianceMethod}
                  onChange={(event) => onChange({ covarianceMethod: event.target.value })}
                >
                  {COVARIANCE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Form.Select>
              </Col>

              <Col md={3}>
                <Form.Label className="fw-bold fs-13px">Lookback (days)</Form.Label>
                <Form.Control
                  type="number"
                  min="2"
                  step="21"
                  value={settings.lookbackDays}
                  onChange={(event) => onChange({ lookbackDays: event.target.value })}
                />
              </Col>
              <Col md={3}>
                <Form.Label className="fw-bold fs-13px">Decision gap (days)</Form.Label>
                <Form.Control
                  type="number"
                  min="0"
                  max="10"
                  value={settings.gapDays}
                  onChange={(event) => onChange({ gapDays: event.target.value })}
                />
                <Form.Text>Days between the last data used and the trade.</Form.Text>
              </Col>

              <Col md={4}>
                <Form.Label className="fw-bold fs-13px">Trading cost</Form.Label>
                <InputGroup>
                  <Form.Control
                    type="number"
                    min="0"
                    step="1"
                    value={settings.transactionCostBps}
                    onChange={(event) => onChange({ transactionCostBps: event.target.value })}
                  />
                  <InputGroup.Text>bps</InputGroup.Text>
                </InputGroup>
              </Col>
              <Col md={4}>
                <Form.Label className="fw-bold fs-13px">Max per holding</Form.Label>
                <Form.Control
                  type="number"
                  min="0"
                  max="1"
                  step="0.05"
                  placeholder="no limit"
                  value={settings.maxWeight}
                  onChange={(event) => onChange({ maxWeight: event.target.value })}
                />
                <Form.Text>As a fraction, e.g. 0.3 for 30%.</Form.Text>
              </Col>
              <Col md={4}>
                <Form.Label className="fw-bold fs-13px">Min per holding</Form.Label>
                <Form.Control
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  placeholder="none"
                  value={settings.minWeight}
                  onChange={(event) => onChange({ minWeight: event.target.value })}
                />
              </Col>

              <Col md={6}>
                <Form.Label className="fw-bold fs-13px">Risk-free rate</Form.Label>
                <Form.Control
                  type="number"
                  min="0"
                  max="0.2"
                  step="0.005"
                  value={settings.riskFreeRate}
                  onChange={(event) => onChange({ riskFreeRate: event.target.value })}
                />
                <Form.Text>Annual, as a fraction. 0.04 is 4%.</Form.Text>
              </Col>
              <Col md={6} className="d-flex align-items-end">
                <Form.Check
                  type="checkbox"
                  id="longOnly"
                  checked={settings.longOnly}
                  onChange={(event) => onChange({ longOnly: event.target.checked })}
                  label={
                    <span>
                      Long only
                      <span className="text-muted ms-2 fs-13px">
                        Turning this off allows short positions, whose borrow costs this simulation does not model.
                      </span>
                    </span>
                  }
                />
              </Col>
            </Row>
          </div>
        </Collapse>
      </Card.Body>
    </Card>
  )
}

export default AdvancedSettings
