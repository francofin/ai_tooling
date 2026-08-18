import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_FINTANK_API_URL || 'http://localhost:8000/api';

export class StockApiError extends Error {
  constructor(message, { status, resource }) {
    super(message);
    this.name = 'StockApiError';
    this.status = status;
    this.resource = resource;
  }

  get isNotFound() {
    return this.status === 404;
  }
}

const request = async (path, resource) => {
  try {
    const res = await axios.get(`${API_URL}${path}`);
    return res.data;
  } catch (error) {
    const status = error.response?.status ?? null;
    const detail = error.response?.data?.detail || error.message;
    throw new StockApiError(`${resource} request failed: ${detail}`, { status, resource });
  }
};

export const fetchProfile = (symbol) =>
  request(`/stock-profile/${encodeURIComponent(symbol)}/`, 'profile');

// ETFs are absent from the long_profiles parquet that /stock-profile/ reads, so
// they resolve against the company-profiles blob instead. Same 404-on-unknown
// contract, different field set: no ceo/employees, but currency, ipo_date,
// last_dividend and last_range are populated.
export const fetchEtfProfile = (symbol) =>
  request(`/company-profiles/${encodeURIComponent(symbol)}/`, 'etf profile');

export const fetchPrices = (symbol) =>
  request(`/stock-prices/${encodeURIComponent(symbol)}/`, 'prices');

// Universe is resolved server-side, so callers only need the symbol.
export const fetchStatements = (symbol, statementType) =>
  request(`/financial-statements/${encodeURIComponent(symbol)}/${statementType}/`, 'statements');

export const fetchSectorNews = (category) =>
  request(`/get_articles/${encodeURIComponent(category)}/`, 'news');

export const STATEMENT_TYPES = [
  { key: 'income_statements', label: 'Income Statement' },
  { key: 'balance_sheet_statements', label: 'Balance Sheet' },
  { key: 'cash_flow_statements', label: 'Cash Flow' },
];

// The news feed is keyed by topic, not ticker, so a stock's sector picks the
// closest available category. Categories come from GetNewsArticles.file_names.
const SECTOR_NEWS_CATEGORIES = {
  'Technology': 'tech',
  'Healthcare': 'pharmaceuticals',
  'Financial Services': 'financials',
  'Energy': 'energy',
  'Basic Materials': 'basic_materials',
  'Industrials': 'industrials',
  'Utilities': 'utilities',
  'Real Estate': 'real_estate',
  'Communication Services': 'communications',
  'Consumer Cyclical': 'consumer_trends',
  'Consumer Defensive': 'consumer_trends',
};

export const sectorNewsCategory = (sector) => SECTOR_NEWS_CATEGORIES[sector] || 'stock';
