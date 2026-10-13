import React, { useState } from 'react';
import { Nav, Table, Spinner, Alert, Button } from 'react-bootstrap';
import { useFinancialStatements } from '@hooks/useFinancialStatements';
import { STATEMENT_TYPES } from '@utils/stockApi';
import { SECTIONS, formatValue, humanise } from '@utils/statementFields';
import StatementsChart from './StatementsChart';

// Filing details shown on every statement, ahead of the figures.
const FILING_ROWS = [
  ['reported_currency', 'Reported Currency'],
  ['filing_date', 'Filing Date'],
  ['calendar_year', 'Calendar Year'],
];

// Rendered as headers or above, never as rows of their own.
const HEADER_KEYS = new Set(['symbol', 'date', 'period']);

const PERIODS_SHOWN = 12;

// The explicit sections, plus any column the parquet gains later so the table
// keeps showing every field without a code change.
const buildSections = (type, rows) => {
  const sections = [['Filing', FILING_ROWS], ...(SECTIONS[type] || [])];
  const known = new Set(sections.flatMap(([, fields]) => fields.map(([key]) => key)));
  const extra = new Set();
  rows.forEach((row) =>
    Object.keys(row).forEach((key) => {
      // `__index_level_0__` and friends are parquet bookkeeping, not data.
      if (!known.has(key) && !HEADER_KEYS.has(key) && !key.startsWith('__')) extra.add(key);
    })
  );
  if (extra.size) {
    sections.push(['Other', [...extra].sort().map((key) => [key, humanise(key)])]);
  }
  return sections;
};

const stickyCell = { position: 'sticky', left: 0, zIndex: 1, background: 'var(--bs-body-bg, #fff)' };

const StatementsSection = ({ symbol }) => {
  const [opened, setOpened] = useState(false);
  const [activeType, setActiveType] = useState(STATEMENT_TYPES[0].key);
  const { rows, universe, error, isLoading } = useFinancialStatements(symbol, activeType, opened);

  if (!opened) {
    return (
      <div className="text-block">
        <h4 className="mb-3">Financial Statements</h4>
        <Button variant="outline-primary" onClick={() => setOpened(true)}>
          Load financial statements
        </Button>
      </div>
    );
  }

  const periods = rows ? rows.slice(0, PERIODS_SHOWN) : [];
  const sections = buildSections(activeType, periods);
  const currency = periods.find((row) => row.reported_currency)?.reported_currency;

  return (
    <div className="text-block">
      <h4 className="mb-3">
        Financial Statements
        {universe && <small className="text-muted fw-light ms-2">({universe})</small>}
      </h4>
      {currency && periods.length > 0 && (
        <p className="text-muted text-sm mb-2">
          Figures in {currency}. Margins are percentages; EPS is per share; share counts are units.
        </p>
      )}

      <Nav variant="tabs" activeKey={activeType} className="mb-3">
        {STATEMENT_TYPES.map((type) => (
          <Nav.Item key={type.key}>
            <Nav.Link eventKey={type.key} onClick={() => setActiveType(type.key)}>
              {type.label}
            </Nav.Link>
          </Nav.Item>
        ))}
      </Nav>

      {isLoading && <Spinner animation="border" size="sm" />}

      {error && (
        <Alert variant="light" className="text-muted">
          {error.isNotFound
            ? `No ${activeType.replace(/_/g, ' ')} available for ${symbol}.`
            : `Could not load statements: ${error.message}`}
        </Alert>
      )}

      {!isLoading && !error && periods.length > 0 && (
        <div className="table-responsive">
          <Table hover size="sm" className="align-middle">
            <thead>
              <tr>
                <th style={stickyCell}>Metric</th>
                {periods.map((row) => (
                  <th key={`${row.date}-${row.period}`} className="text-end text-nowrap">
                    {row.date}
                    {row.period && <div className="text-muted fw-light">{row.period}</div>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sections.map(([title, fields]) => (
                <React.Fragment key={title}>
                  <tr className="table-light">
                    <th colSpan={periods.length + 1} className="text-uppercase text-xs" style={stickyCell}>
                      {title}
                    </th>
                  </tr>
                  {fields.map(([key, label]) => (
                    <tr key={key}>
                      <td className="text-nowrap" style={stickyCell}>{label}</td>
                      {periods.map((row) => (
                        <td key={`${key}-${row.date}-${row.period}`} className="text-end text-nowrap">
                          {formatValue(row[key], key)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </React.Fragment>
              ))}
            </tbody>
          </Table>
        </div>
      )}

      {!isLoading && !error && periods.length === 0 && (
        <p className="text-muted">No statement data returned for {symbol}.</p>
      )}

      <StatementsChart symbol={symbol} />
    </div>
  );
};

export default StatementsSection;
