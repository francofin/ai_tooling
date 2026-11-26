import React from 'react'
import { Col, Form, Row } from 'react-bootstrap'
import TickerPicker from '@componentsLegacy/Comparison/TickerPicker'
import { MAX_PER_LIST } from '@utils/fundFinder/query.mjs'

const FundFinderForm = ({ state, onListed, onInclude, onExclude, onLeveraged }) => (
  <Form onSubmit={(event) => event.preventDefault()}>
    <Row className="mb-4">
      <Col md={4}>
        <Form.Label htmlFor="fund-listed">Funds listed in</Form.Label>
        <Form.Select id="fund-listed" value={state.listed || ''} onChange={(event) => onListed(event.target.value)}>
          <option value="" disabled>
            Choose…
          </option>
          <option value="ca">Canada</option>
          <option value="us">United States</option>
          <option value="both">Both</option>
        </Form.Select>
      </Col>
      <Col md="auto" className="d-flex align-items-end">
        <Form.Check
          type="checkbox"
          id="fund-leveraged"
          label="Include leveraged funds"
          checked={Boolean(state.leveraged)}
          onChange={(event) => onLeveraged(event.target.checked)}
        />
      </Col>
    </Row>
    <Row>
      <Col md={6} className="mb-4">
        <TickerPicker
          symbols={state.include}
          onChange={onInclude}
          max={MAX_PER_LIST}
          label="Exposure to"
          id="fund-include"
        />
      </Col>
      <Col md={6} className="mb-4">
        <TickerPicker
          symbols={state.exclude}
          onChange={onExclude}
          max={MAX_PER_LIST}
          label="But not"
          id="fund-exclude"
        />
      </Col>
    </Row>
  </Form>
)

export default FundFinderForm
