import React from 'react';
import { Card, Badge, Spinner } from 'react-bootstrap';
import { useStockQuote } from '@hooks/useStockQuote';
import {
  EMPTY,
  currencyLabel,
  formatPrice,
  formatSignedPrice,
  formatSignedPercent,
  formatMarketCap,
  formatVolume,
  formatDateTime,
  formatDate,
  quoteDate,
  isStaleQuote,
  direction,
} from '@utils/stockQuoteFormat';

const TONE = { positive: 'text-success', negative: 'text-danger', flat: 'text-muted' };

const range = (low, high, currency) => {
  const lo = formatPrice(low, currency);
  const hi = formatPrice(high, currency);
  return lo === EMPTY && hi === EMPTY ? EMPTY : `${lo} – ${hi}`;
};

const Group = ({ title, rows, last = false }) => (
  <div className={last ? '' : 'mb-3'}>
    <div className="text-uppercase text-muted text-xs fw-bold mb-2" style={{ letterSpacing: '0.05em' }}>
      {title}
    </div>
    <dl className="row text-sm mb-0">
      {rows.map(([label, value]) => (
        <React.Fragment key={label}>
          {/* 5/7 split: at lg the sidebar is ~260px and ranges need the room. */}
          <dt className="col-5 fw-normal text-muted mb-1">{label}</dt>
          <dd className="col-7 text-end mb-1">{value}</dd>
        </React.Fragment>
      ))}
    </dl>
  </div>
);

const Shell = ({ currency, children }) => (
  <Card className="border-0 shadow-sm">
    <Card.Body>
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h6 className="mb-0">Quote{currency ? ` · ${currency}` : ''}</h6>
        <Badge bg="light" text="dark" className="fw-normal">
          Delayed
        </Badge>
      </div>
      {children}
    </Card.Body>
  </Card>
);

/**
 * Delayed quote panel for the stock detail page. Fetches client-side so the
 * page never waits on the provider, and degrades to a one-line message on
 * failure rather than taking the page with it.
 *
 * `currency` comes from the profile: FMP's quote carries none.
 */
const QuoteCard = ({ symbol, currency }) => {
  const { data, error, isLoading } = useStockQuote(symbol);
  const label = currencyLabel(currency);

  if (isLoading) {
    return (
      <Shell currency={label}>
        <div className="d-flex align-items-center text-muted text-sm py-4">
          <Spinner animation="border" size="sm" className="me-2" role="status" />
          Loading quote…
        </div>
      </Shell>
    );
  }

  // swr@1 keeps the last good `data` when a refresh fails, so only fall back
  // to the error message when there is nothing to show.
  const quote = data?.quote;
  if (!quote) {
    // Anything but a 404 (502 provider down, 500, network) may clear on retry.
    const message =
      error && error.status !== 404 ? 'Quote unavailable right now.' : `No quote available for ${symbol}.`;
    return (
      <Shell currency={label}>
        <p className="text-muted text-sm mb-0">{message}</p>
      </Shell>
    );
  }

  const tradedAt = quoteDate(quote.timestamp);
  const stale = isStaleQuote(tradedAt);
  const tone = TONE[direction(quote.change ?? quote.changePercentage)] || '';

  return (
    <Shell currency={label}>
      <div className="mb-3">
        <div className="fw-bold">{quote.name || symbol}</div>
        <div className="text-muted text-sm text-uppercase">
          {[quote.symbol || symbol, quote.exchange].filter(Boolean).join(' · ')}
        </div>
      </div>

      <div className="mb-3">
        <div className="h2 mb-1">{formatPrice(quote.price, currency)}</div>
        <div className={`fw-bold ${tone}`}>
          {formatSignedPrice(quote.change, currency)} ({formatSignedPercent(quote.changePercentage)})
        </div>
        <div className="text-muted text-sm mt-1">{formatDateTime(tradedAt)}</div>
        {stale && (
          <Badge bg="warning" text="dark" className="fw-normal mt-2">
            Stale · Last trade {formatDate(tradedAt)}
          </Badge>
        )}
        {data.stale_cache && (
          <p className="text-muted text-xs mb-0 mt-2">
            Live data is unavailable; showing the last available quote.
          </p>
        )}
      </div>

      <Group
        title="Today"
        rows={[
          ['Open', formatPrice(quote.open, currency)],
          ['Previous close', formatPrice(quote.previousClose, currency)],
          ['Day range', range(quote.dayLow, quote.dayHigh, currency)],
        ]}
      />
      <Group title="52-week" rows={[['Range', range(quote.yearLow, quote.yearHigh, currency)]]} />
      <Group
        title="Averages"
        rows={[
          ['50-day', formatPrice(quote.priceAvg50, currency)],
          ['200-day', formatPrice(quote.priceAvg200, currency)],
        ]}
      />
      <Group
        last
        title="Size"
        rows={[
          ['Market cap', formatMarketCap(quote.marketCap, currency)],
          ['Volume', formatVolume(quote.volume)],
        ]}
      />
    </Shell>
  );
};

export default QuoteCard;
