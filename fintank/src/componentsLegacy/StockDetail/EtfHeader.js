import React from 'react';
import { Row, Col, Badge } from 'react-bootstrap';
import WatchlistButton from './WatchlistButton';

const formatAum = (value) => {
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

const formatDate = (value) => {
  if (!value) return null;
  // `new Date('2020-09-18')` is parsed as UTC midnight, so rendering it in any
  // timezone behind UTC lands on the 17th. Build the date from its parts so it
  // stays the calendar day the API reported.
  const parts = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  const parsed = parts
    ? new Date(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3]))
    : new Date(value);
  if (Number.isNaN(parsed.valueOf())) return value;
  return parsed.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
};

/**
 * The ETF twin of StockHeader. A fund has no CEO, no employee count and no
 * meaningful "company profile", so reusing StockHeader here would render three
 * permanently empty fields. What a fund does have -- inception, distribution,
 * trading currency, 52-week range -- StockHeader has nowhere to put.
 */
const EtfHeader = ({ profile, asOfDate }) => {
  const facts = [
    profile.sector && { label: 'Sector', value: profile.sector },
    profile.industry && { label: 'Category', value: profile.industry },
    profile.market_cap && { label: 'AUM', value: formatAum(profile.market_cap) },
    profile.beta != null && { label: 'Beta', value: Number(profile.beta).toFixed(2) },
    profile.last_range && { label: '52w Range', value: profile.last_range },
    profile.last_dividend != null && {
      label: 'Last Distribution',
      value: Number(profile.last_dividend).toFixed(3),
    },
    profile.ipo_date && { label: 'Inception', value: formatDate(profile.ipo_date) },
    profile.volume_avg && {
      label: 'Avg Volume',
      value: Intl.NumberFormat().format(profile.volume_avg),
    },
  ].filter(Boolean);

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
            {[profile.exchange_short_name, profile.country, profile.currency]
              .filter(Boolean)
              .join(' · ')}
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
        {facts.map((fact) => (
          <li className="list-inline-item me-3" key={fact.label}>
            {fact.label}: {fact.value}
          </li>
        ))}
      </ul>

      {profile.description && (
        <>
          <h6 className="mb-3">Fund Objective</h6>
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

export default EtfHeader;
