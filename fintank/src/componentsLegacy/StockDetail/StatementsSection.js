import React, { useState } from 'react';
import { Nav, Table, Spinner, Alert, Button } from 'react-bootstrap';
import { useFinancialStatements } from '@hooks/useFinancialStatements';
import { STATEMENT_TYPES } from '@utils/stockApi';

// The parquets carry ~60 columns; these are the ones worth a headline table.
const COLUMNS = {
  income_statements: [
    ['revenue', 'Revenue'],
    ['gross_profit', 'Gross Profit'],
    ['operating_income', 'Operating Income'],
    ['net_income', 'Net Income'],
    ['eps_diluted', 'EPS (diluted)'],
  ],
  balance_sheet_statements: [
    ['total_assets', 'Total Assets'],
    ['total_liabilities', 'Total Liabilities'],
    ['total_stockholders_equity', 'Equity'],
    ['total_debt', 'Total Debt'],
    ['net_debt', 'Net Debt'],
  ],
  cash_flow_statements: [
    ['operating_cash_flow', 'Operating Cash Flow'],
    ['capital_expenditure', 'CapEx'],
    ['free_cash_flow', 'Free Cash Flow'],
    ['net_income', 'Net Income'],
  ],
};

const PERIODS_SHOWN = 12;

const formatValue = (value, key) => {
  if (value === null || value === undefined) return '—';
  if (key === 'eps_diluted') return Number(value).toFixed(2);
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  return Intl.NumberFormat().format(value);
};

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

  const columns = COLUMNS[activeType] || [];
  const periods = rows ? rows.slice(0, PERIODS_SHOWN) : [];

  return (
    <div className="text-block">
      <h4 className="mb-3">
        Financial Statements
        {universe && <small className="text-muted fw-light ms-2">({universe})</small>}
      </h4>

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
                <th>Metric</th>
                {periods.map((row) => (
                  <th key={`${row.date}-${row.period}`} className="text-end text-nowrap">
                    {row.date}
                    {row.period && <div className="text-muted fw-light">{row.period}</div>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {columns.map(([key, label]) => (
                <tr key={key}>
                  <td className="text-nowrap">{label}</td>
                  {periods.map((row) => (
                    <td key={`${key}-${row.date}`} className="text-end text-nowrap">
                      {formatValue(row[key], key)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      )}

      {!isLoading && !error && periods.length === 0 && (
        <p className="text-muted">No statement data returned for {symbol}.</p>
      )}
    </div>
  );
};

export default StatementsSection;
