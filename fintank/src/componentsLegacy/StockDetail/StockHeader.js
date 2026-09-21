import React from 'react';
import { Row, Col, Badge } from 'react-bootstrap';
import WatchlistButton from './WatchlistButton';

const formatNumber = (value) => (value ? Intl.NumberFormat().format(value) : null);

const formatMarketCap = (value) => {
  if (!value) return null;
  const units = [
    [1e12, 'T'],
    [1e9, 'B'],
    [1e6, 'M'],
  ];
  for (const [size, suffix] of units) {
    if (value >= size) return `$${(value / size).toFixed(1)}${suffix}`;
  }
  return `$${Intl.NumberFormat().format(value)}`;
};

const StockHeader = ({ profile, asOfDate }) => {
  const employees = formatNumber(profile.no_of_employees);
  const marketCap = formatMarketCap(profile.market_cap);

  return (
    <div className="text-block">
      <Row className="align-items-start">
        <Col lg="9">
          <div className="d-flex flex-wrap align-items-center gap-3 mb-1">
            <h1 className="mb-0">
              {profile.name || profile.symbol}: {profile.symbol}
            </h1>
            <WatchlistButton symbol={profile.symbol} />
          </div>
          <div className="text-muted text-uppercase mb-3">
            {[profile.exchange_short_name, profile.country].filter(Boolean).join(' · ')}
          </div>
        </Col>
        <Col lg="3" className="text-lg-end">
          {asOfDate && (
            <Badge bg="light" text="dark" className="fw-normal">
              Data as of {asOfDate}
            </Badge>
          )}
        </Col>
      </Row>

      <ul className="list-inline text-sm mb-4">
        {profile.sector && <li className="list-inline-item me-3">Sector: {profile.sector}</li>}
        {marketCap && <li className="list-inline-item me-3">Market Cap: {marketCap}</li>}
        {employees && <li className="list-inline-item me-3">Employees: {employees}</li>}
        {profile.beta != null && (
          <li className="list-inline-item me-3">Beta: {Number(profile.beta).toFixed(2)}</li>
        )}
      </ul>

      {profile.description && (
        <>
          <h6 className="mb-3">Company Profile</h6>
          <p className="text-muted fw-light">{profile.description}</p>
        </>
      )}

      {profile.website && (
        <a href={profile.website} target="_blank" rel="noreferrer" className="text-sm">
          {profile.website}
        </a>
      )}
    </div>
  );
};

export default StockHeader;
