// Formatting for the stock detail page's quote card (StockDetail/QuoteCard).
// Distinct from quoteFormat.js, which serves the markets cards and heat map and
// assumes USD; this one is currency-aware. FMP's quote carries no currency, so
// the caller passes the profile's `currency` (e.g. 'USD', 'CAD', 'JPY', 'GBp').

export const EMPTY = '—';

// Currencies whose symbol reads as a bare `$`. The code is shown once in the
// card header, so prefixing these with `CA$`/`A$` would only be noise.
const DOLLAR_CURRENCIES = new Set(['USD', 'CAD', 'AUD', 'NZD', 'HKD', 'SGD', 'TWD', 'MXN']);

// London quotes in pence: 'GBp' from FMP, 'GBX' from some other feeds.
const isPence = (currency) => currency === 'GBp' || currency === 'GBX';

const isNum = (value) => typeof value === 'number' && Number.isFinite(value);

const twoDp = (value) =>
  value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// Intl throws RangeError on a malformed code, so this returns null instead and
// lets the caller fall back to a code suffix. Valid-but-unknown codes ('XYZ')
// don't throw; Intl just prints the code, which is fine.
const currencyFormatter = (code) => {
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: code,
      currencyDisplay: 'narrowSymbol',
    });
  } catch {
    return null;
  }
};

/**
 * Label for the card header: 'CAD', 'GBp' (pence), etc. Null when unknown.
 */
export const currencyLabel = (currency) => (currency ? String(currency) : null);

/**
 * A per-share price in the listing's currency.
 *   USD/CAD/... -> $12.34   GBp -> 1,234.50p   JPY -> ¥1,235   bad code -> 12.34 ZZ
 * Missing currency is treated as dollars.
 */
export const formatPrice = (value, currency) => {
  if (!isNum(value)) return EMPTY;
  if (isPence(currency)) return `${twoDp(value)}p`;

  const code = currency ? String(currency).toUpperCase() : 'USD';
  if (DOLLAR_CURRENCIES.has(code)) {
    return `${value < 0 ? '-' : ''}$${twoDp(Math.abs(value))}`;
  }
  const fmt = currencyFormatter(code);
  return fmt ? fmt.format(value) : `${twoDp(value)} ${currency}`;
};

/**
 * Signed price change: +$0.12 / -$1.05 / +3.20p.
 */
export const formatSignedPrice = (value, currency) => {
  if (!isNum(value)) return EMPTY;
  const body = formatPrice(Math.abs(value), currency);
  return `${value > 0 ? '+' : value < 0 ? '-' : ''}${body}`;
};

/**
 * changePercentage is already a percent (0.7128 -> +0.71%).
 */
export const formatSignedPercent = (value) => {
  if (!isNum(value)) return EMPTY;
  return `${value > 0 ? '+' : value < 0 ? '-' : ''}${Math.abs(value).toFixed(2)}%`;
};

/**
 * 'positive' | 'negative' | 'flat' | null -- drives text-success / text-danger.
 */
export const direction = (value) => {
  if (!isNum(value)) return null;
  if (value > 0) return 'positive';
  if (value < 0) return 'negative';
  return 'flat';
};

// T / B / M, with everything under a million still expressed in M (0.25M) so
// the column reads on one scale.
const scaled = (value) => {
  const abs = Math.abs(value);
  if (abs >= 1e12) return [value / 1e12, 'T'];
  if (abs >= 1e9) return [value / 1e9, 'B'];
  return [value / 1e6, 'M'];
};

/**
 * Market cap: $19.21B, $450.32M, $5.01T, $0.45M.
 * For pence listings FMP reports market cap in pounds, not pence (VOD.L:
 * price 116.7, marketCap 2.69e10), so GBp maps to £ here.
 */
export const formatMarketCap = (value, currency) => {
  if (!isNum(value)) return EMPTY;
  const [n, suffix] = scaled(value);
  const code = isPence(currency) ? 'GBP' : currency;
  return `${formatPrice(n, code)}${suffix}`;
};

/**
 * Share volume: 1.81M, 25.80M, 1.20B, 0.25M.
 */
export const formatVolume = (value) => {
  if (!isNum(value)) return EMPTY;
  const [n, suffix] = scaled(value);
  return `${twoDp(n)}${suffix}`;
};

const DATE_TIME = {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  timeZoneName: 'short',
};
const DATE_ONLY = { month: 'short', day: 'numeric', year: 'numeric' };

/**
 * FMP's quote timestamp is UNIX seconds. Returns a Date or null.
 */
export const quoteDate = (timestamp) => (isNum(timestamp) && timestamp > 0 ? new Date(timestamp * 1000) : null);

/**
 * 'Sep 4, 2026, 4:00 PM EDT' in the viewer's local zone.
 */
export const formatDateTime = (date) => (date ? new Intl.DateTimeFormat('en-US', DATE_TIME).format(date) : EMPTY);

/**
 * 'Sep 4, 2026'.
 */
export const formatDate = (date) => (date ? new Intl.DateTimeFormat('en-US', DATE_ONLY).format(date) : EMPTY);

export const STALE_AFTER_MS = 3 * 24 * 60 * 60 * 1000;

/**
 * True when the last trade is more than three days old -- long enough to clear
 * a normal weekend plus a holiday Monday.
 */
export const isStaleQuote = (date, now = Date.now()) => Boolean(date) && now - date.getTime() > STALE_AFTER_MS;
