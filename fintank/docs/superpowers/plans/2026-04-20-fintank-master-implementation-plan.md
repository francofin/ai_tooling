# Fintank — Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build out the Fintank financial analytics platform across 10 sequential phases, each producing independently testable and deployable software on top of the existing Django + Next.js codebase.

**Architecture:** Celery pre-computes all analytical data on a schedule; Django serves from Redis cache (gzip-compressed JSON) with S3 parquet/JSON as durable fallback; Next.js Pages Router consumes REST APIs via SWR hooks. All backend logic is prototyped in `backend/class_files/` Jupyter notebooks before being ported to Django apps.

**Tech Stack:** Django 4.x, DRF, Celery + Redis, PostgreSQL + PostGIS, AWS S3 (boto3 / s3fs), Next.js 13 (Pages Router), SWR, Chart.js, ApexCharts, Bootstrap 5, Stripe (future phase), FMP API, NewsAPI/Benzinga.

**Spec reference:** `docs/superpowers/specs/2026-04-20-fintank-platform-design.md`

---

## How to Use This Document

This is the master roadmap. Each phase is a standalone unit of work:

1. Read the phase overview and file map
2. Create a detailed execution plan for that phase (or use this doc directly for simpler phases)
3. Follow the §4 notebook-first workflow: prototype in `backend/class_files/<notebook>.ipynb` → validate → port to Django
4. Complete all verification steps before moving to the next phase

**Phase order is load-bearing.** Phase 2 (news engine) unlocks news on the Phase 1 stock detail page. Phase 4 (factor engine) is required before Phase 5 (backtesting) and Phase 7 (screener factor filters).

> **Backtester status (2026-08-11).** The `backtester` app is now defined by
> `docs/superpowers/specs/2026-08-11-portfolio-backtest-design.md` — portfolio construction,
> optimization and simulation. **Phase 10 is superseded; Phase 5 is deferred and out of
> scope.** The portfolio backtester sits outside the dependency chain above: it reads price
> parquets only and needs neither Phase 4 nor Phase 5.

---

## Global Conventions

### Django conventions (existing pattern — follow exactly)
- Cache reads: `cache.get(key)` → decompress with `gzip.decompress` → `json.loads`
- Cache writes: `json.dumps` → `gzip.compress` → `cache.set(key, value, timeout)`
- Cache key pattern: `{domain}:{data_type}:{qualifier}:v1`
- S3 reads: use `GetData` class in `backend/utils/StockCalculations.py`
- Celery tasks: decorated with `@shared_task`, registered in `fintank_backend/celery.py`
- Market-hours guard: `from utils.market_hours import is_market_open_now`
- DRF views: class-based (`APIView`), `permission_classes = [IsAuthenticated]`

### Frontend conventions (existing pattern — follow exactly)
- Hooks live in `src/hooks/`, named `use<FeatureName>.js`
- Data fetching: `axios.get(process.env.NEXT_PUBLIC_FINTANK_API_URL + '/endpoint/')`
- SWR: `useSWR(key, fetcher, { refreshInterval: <ms> })`
- Pages: functional components, Bootstrap 5 classes, `getServerSideProps` for auth redirect
- Charts: Chart.js (`react-chartjs-2`) for historical line/bar, ApexCharts for heatmaps

### Notebook conventions
- Every new backend feature starts with a notebook in `backend/class_files/`
- Notebook cells: imports → data fetch → class definition → validation assertions → visualisation
- Final cell must print a sample of the output to confirm shape/values

### Testing
- Backend: Django's `TestCase` in `backend/<app>/tests.py`
- Run: `cd backend && python manage.py test <app>`
- Frontend: no automated tests in existing codebase — manual browser verification per feature
- Celery: test tasks synchronously with `task.apply()` in tests

---

## Phase 1 — Stock Detail Page

**Produces:** A fully functional `/stock-data/[ticker]` page showing price chart, financials, valuation metrics, factor score placeholders, and a news feed stub.

**Spec reference:** §8.2

**Prerequisite:** None — reuses entirely existing hooks, models, and components.

### 1.A: Notebook prototype

**File:** `backend/class_files/stock_detail.ipynb`

- [ ] Create notebook. Cell 1 — imports:
  ```python
  import os, django
  os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fintank_backend.settings')
  django.setup()
  from stockuploader.models import Stock, IncomeStatement, CashFlowStatement, BalanceSheet, FundamentalMetricTTM, FundamentalRatioTTM
  import requests, pandas as pd
  FMP_API = os.environ['FMP_API']
  FMP_URL = os.environ['FMP_URL']
  ```

- [ ] Cell 2 — fetch live quote from FMP and verify structure:
  ```python
  ticker = 'AAPL'
  resp = requests.get(f'{FMP_URL}/v3/quote/{ticker}?apikey={FMP_API}')
  quote = resp.json()[0]
  print(quote.keys())
  # Expected keys: symbol, price, changesPercentage, marketCap, exchange, name
  ```

- [ ] Cell 3 — fetch financial statements from DB and verify data exists:
  ```python
  income = IncomeStatement.objects.filter(symbol=ticker).order_by('-date')[:5]
  cashflow = CashFlowStatement.objects.filter(symbol=ticker).order_by('-date')[:5]
  balance = BalanceSheet.objects.filter(symbol=ticker).order_by('-date')[:5]
  metrics = FundamentalMetricTTM.objects.filter(symbol=ticker).first()
  print(f"Income rows: {income.count()}, Metrics: {metrics}")
  ```

- [ ] Cell 4 — build the serialiser response dict to confirm shape:
  ```python
  def build_stock_detail(ticker):
      stock = Stock.objects.get(symbol=ticker)
      quote = requests.get(f'{FMP_URL}/v3/quote/{ticker}?apikey={FMP_API}').json()[0]
      income_qs = list(IncomeStatement.objects.filter(symbol=ticker).order_by('-date').values()[:5])
      metrics = FundamentalMetricTTM.objects.filter(symbol=ticker).values().first()
      return {
          'quote': quote,
          'profile': {'sector': stock.sector, 'industry': stock.industry, 'description': stock.description},
          'income_statements': income_qs,
          'metrics': metrics,
      }
  result = build_stock_detail('AAPL')
  print(result['quote']['price'], result['profile']['sector'])
  ```

- [ ] Confirm all fields are non-null for at least 3 tickers (AAPL, MSFT, SHOP.TO). Fix any missing data issues before proceeding.

- [ ] Commit notebook: `git add backend/class_files/stock_detail.ipynb && git commit -m "notebook: stock detail data prototype"`

### 1.B: Backend — API endpoint

**Files:**
- Modify: `backend/analyzer/views.py`
- Modify: `backend/analyzer/urls.py` (or `backend/fintank_backend/urls.py`)

- [ ] Add view to `backend/analyzer/views.py`:
  ```python
  from stockuploader.models import Stock, IncomeStatement, CashFlowStatement, BalanceSheet, FundamentalMetricTTM, FundamentalRatioTTM
  import requests, os

  class StockDetailView(APIView):
      permission_classes = [IsAuthenticated]

      def get(self, request, symbol):
          symbol = symbol.upper()
          cache_key = f'stock:detail:{symbol}:v1'
          cached = cache.get(cache_key)
          if cached:
              return Response(json.loads(gzip.decompress(cached)))

          try:
              stock = Stock.objects.get(symbol=symbol)
          except Stock.DoesNotExist:
              return Response({'error': 'Symbol not found'}, status=404)

          quote_resp = requests.get(
              f"{os.environ['FMP_URL']}/v3/quote/{symbol}",
              params={'apikey': os.environ['FMP_API']}, timeout=10
          )
          quote = quote_resp.json()[0] if quote_resp.ok and quote_resp.json() else {}

          income = list(IncomeStatement.objects.filter(symbol=symbol).order_by('-date').values()[:8])
          cashflow = list(CashFlowStatement.objects.filter(symbol=symbol).order_by('-date').values()[:8])
          balance = list(BalanceSheet.objects.filter(symbol=symbol).order_by('-date').values()[:8])
          metrics = FundamentalMetricTTM.objects.filter(symbol=symbol).values().first() or {}
          ratios = FundamentalRatioTTM.objects.filter(symbol=symbol).values().first() or {}

          data = {
              'quote': quote,
              'profile': {
                  'sector': stock.sector, 'industry': stock.industry,
                  'description': stock.description, 'exchange': stock.exchange,
                  'country': stock.country,
              },
              'income_statements': income,
              'cash_flow_statements': cashflow,
              'balance_sheets': balance,
              'metrics_ttm': metrics,
              'ratios_ttm': ratios,
              'factor_scores': {},  # populated by Phase 4
              'news': [],           # populated by Phase 2
          }
          compressed = gzip.compress(json.dumps(data, default=str).encode())
          cache.set(cache_key, compressed, 60 * 5)  # 5 min TTL for live quote
          return Response(data)
  ```

- [ ] Register URL in `backend/analyzer/urls.py`:
  ```python
  path('stock-detail/<str:symbol>/', StockDetailView.as_view(), name='stock-detail'),
  ```

- [ ] Write test in `backend/analyzer/tests.py`:
  ```python
  from django.test import TestCase
  from django.urls import reverse
  from rest_framework.test import APIClient
  from users.models import CustomUser
  from stockuploader.models import Stock

  class StockDetailViewTest(TestCase):
      def setUp(self):
          self.client = APIClient()
          self.user = CustomUser.objects.create_user(
              email='test@test.com', password='pass', first_name='T', last_name='U'
          )
          self.client.force_authenticate(user=self.user)
          Stock.objects.create(symbol='AAPL', name='Apple Inc', exchange='NASDAQ',
                               sector='Technology', industry='Consumer Electronics',
                               currency='USD', country='US')

      def test_stock_detail_returns_200(self):
          resp = self.client.get('/api/stock-detail/AAPL/')
          self.assertEqual(resp.status_code, 200)
          self.assertIn('quote', resp.data)
          self.assertIn('profile', resp.data)

      def test_unknown_symbol_returns_404(self):
          resp = self.client.get('/api/stock-detail/ZZZZ/')
          self.assertEqual(resp.status_code, 404)

      def test_unauthenticated_returns_401(self):
          self.client.force_authenticate(user=None)
          resp = self.client.get('/api/stock-detail/AAPL/')
          self.assertEqual(resp.status_code, 401)
  ```

- [ ] Run tests: `cd backend && python manage.py test analyzer.tests.StockDetailViewTest`
- [ ] Commit: `git commit -am "feat(analyzer): add StockDetailView API endpoint"`

### 1.C: Frontend — hook and page

**Files:**
- Create: `src/hooks/useStockDetail.js`
- Create: `src/pages/stock-data/[ticker].js`

- [ ] Create `src/hooks/useStockDetail.js`:
  ```javascript
  import useSWR from 'swr';
  import axios from 'axios';

  const fetcher = (url) => axios.get(url).then(r => r.data);

  export function useStockDetail(ticker) {
    const { data, error, isLoading } = useSWR(
      ticker ? `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/stock-detail/${ticker}/` : null,
      fetcher,
      { refreshInterval: 30000 }
    );
    return { detail: data, error, isLoading };
  }
  ```

- [ ] Create `src/pages/stock-data/[ticker].js`:
  ```javascript
  import { useRouter } from 'next/router';
  import Layout from '../../componentsLegacy/Layout';
  import MetricsTable from '../../componentsLegacy/MetricsTable';
  import { useStockDetail } from '../../hooks/useStockDetail';
  import { useNewCandleSticks } from '../../hooks/useNewCandleSticks';

  export default function StockDetailPage() {
    const { query } = useRouter();
    const { ticker } = query;
    const { detail, isLoading, error } = useStockDetail(ticker);
    const { candleData } = useNewCandleSticks(ticker);

    if (isLoading) return <Layout><div className="container mt-5"><p>Loading...</p></div></Layout>;
    if (error) return <Layout><div className="container mt-5"><p>Error loading data.</p></div></Layout>;
    if (!detail) return null;

    const { quote, profile, income_statements, metrics_ttm } = detail;

    return (
      <Layout>
        <div className="container mt-4">
          {/* Header strip */}
          <div className="d-flex align-items-center gap-3 mb-4">
            <h2 className="mb-0">{ticker}</h2>
            <span className="fs-4 fw-bold">${quote?.price?.toFixed(2)}</span>
            <span className={`badge ${quote?.changesPercentage >= 0 ? 'bg-success' : 'bg-danger'}`}>
              {quote?.changesPercentage?.toFixed(2)}%
            </span>
            <small className="text-muted">{profile?.exchange} · {profile?.sector}</small>
          </div>

          {/* Price chart placeholder — candlestick hook wired up */}
          <div className="card mb-4">
            <div className="card-body">
              <h5 className="card-title">Price Chart</h5>
              {/* CandleStick chart component to be added once useNewCandleSticks confirmed */}
              <p className="text-muted small">Candlestick chart renders here (see useNewCandleSticks hook)</p>
            </div>
          </div>

          {/* Financial statements tabs */}
          <div className="card mb-4">
            <div className="card-body">
              <ul className="nav nav-tabs mb-3" id="financialTabs">
                <li className="nav-item"><button className="nav-link active" data-bs-target="#income" data-bs-toggle="tab">Income</button></li>
                <li className="nav-item"><button className="nav-link" data-bs-target="#cashflow" data-bs-toggle="tab">Cash Flow</button></li>
                <li className="nav-item"><button className="nav-link" data-bs-target="#balance" data-bs-toggle="tab">Balance Sheet</button></li>
              </ul>
              <div className="tab-content">
                <div className="tab-pane active" id="income">
                  <table className="table table-sm table-striped">
                    <thead><tr><th>Period</th><th>Revenue</th><th>Net Income</th><th>EPS</th></tr></thead>
                    <tbody>
                      {income_statements?.map(row => (
                        <tr key={row.date}>
                          <td>{row.date}</td>
                          <td>${(row.revenue / 1e9)?.toFixed(1)}B</td>
                          <td>${(row.net_income / 1e9)?.toFixed(1)}B</td>
                          <td>{row.eps_diluted?.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>

          {/* Valuation metrics */}
          <div className="card mb-4">
            <div className="card-body">
              <h5 className="card-title">Valuation Metrics (TTM)</h5>
              {metrics_ttm && <MetricsTable data={metrics_ttm} />}
            </div>
          </div>

          {/* Factor scores — populated in Phase 4 */}
          <div className="card mb-4">
            <div className="card-body">
              <h5 className="card-title">Factor Scores</h5>
              <p className="text-muted small">Available after Phase 4 (Factor Engine)</p>
            </div>
          </div>

          {/* News feed — populated in Phase 2 */}
          <div className="card mb-4">
            <div className="card-body">
              <h5 className="card-title">News</h5>
              <p className="text-muted small">Available after Phase 2 (News Engine)</p>
            </div>
          </div>

          {/* Company description */}
          <div className="card mb-4">
            <div className="card-body">
              <h5 className="card-title">About</h5>
              <p>{profile?.description}</p>
            </div>
          </div>
        </div>
      </Layout>
    );
  }

  export async function getServerSideProps({ req }) {
    // Redirect to login if not authenticated
    const token = req.cookies?.access_token;
    if (!token) return { redirect: { destination: '/login', permanent: false } };
    return { props: {} };
  }
  ```

- [ ] Start dev server: `npm run dev`
- [ ] Navigate to `http://localhost:8020/stock-data/AAPL` — verify header strip, financials table, and valuation metrics render without console errors
- [ ] Verify 401 redirect to `/login` when not logged in
- [ ] Commit: `git commit -am "feat(frontend): add stock detail page /stock-data/[ticker]"`

---

## Phase 2 — Enhanced News Engine

**Produces:** Multi-source news ingestion (FMP + secondary), normalized schema, ticker extraction, per-ticker news API endpoint. Wires news feed into stock detail page from Phase 1.

**Spec reference:** §8.3

**Prerequisite:** Phase 1 (stock detail page placeholder).

### 2.A: Notebook prototype

**File:** `backend/class_files/news_normalizer.ipynb`

- [ ] Create notebook. Cell 1 — imports and schema definition:
  ```python
  import requests, os, hashlib, re, json, gzip
  from datetime import datetime

  FMP_API = os.environ['FMP_API']
  FMP_URL = os.environ['FMP_URL']
  NEWS_SECONDARY_API_KEY = os.environ.get('NEWS_SECONDARY_API_KEY', '')

  def article_id(url):
      return hashlib.md5(url.encode()).hexdigest()

  SCHEMA_KEYS = ['id', 'title', 'summary', 'url', 'source', 'published_at', 'tickers', 'sectors', 'themes']
  ```

- [ ] Cell 2 — fetch from FMP and normalise:
  ```python
  def fetch_fmp_news(limit=50):
      resp = requests.get(f'{FMP_URL}/v3/stock_news', params={'limit': limit, 'apikey': FMP_API})
      articles = []
      for item in resp.json():
          articles.append({
              'id': article_id(item['url']),
              'title': item['title'],
              'summary': item.get('text', '')[:500],
              'url': item['url'],
              'source': 'fmp',
              'published_at': item['publishedDate'],
              'tickers': [item['symbol']] if item.get('symbol') else [],
              'sectors': [],
              'themes': [],
          })
      return articles

  fmp_articles = fetch_fmp_news()
  print(f"Fetched {len(fmp_articles)} FMP articles")
  print(fmp_articles[0])
  ```

- [ ] Cell 3 — ticker extraction via regex against known ticker list:
  ```python
  import django, os
  os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fintank_backend.settings')
  django.setup()
  from django.core.cache import cache

  def get_known_tickers():
      """Pull ticker list from cache or DB."""
      from stockuploader.models import Stock
      return set(Stock.objects.values_list('symbol', flat=True))

  KNOWN_TICKERS = get_known_tickers()

  def extract_tickers(text, known_tickers):
      """Find uppercase words 1-5 chars that match known tickers."""
      candidates = re.findall(r'\b([A-Z]{1,5})\b', text)
      return list(set(c for c in candidates if c in known_tickers))

  # Test on a sample headline
  sample = "Apple (AAPL) and Microsoft (MSFT) report earnings this week."
  found = extract_tickers(sample, KNOWN_TICKERS)
  print(f"Extracted tickers: {found}")  # Expected: ['AAPL', 'MSFT']
  assert 'AAPL' in found and 'MSFT' in found
  ```

- [ ] Cell 4 — enrich articles with extracted tickers and verify:
  ```python
  def enrich_article(article, known_tickers):
      extracted = extract_tickers(article['title'] + ' ' + article['summary'], known_tickers)
      merged = list(set(article['tickers'] + extracted))
      article['tickers'] = merged
      return article

  enriched = [enrich_article(a, KNOWN_TICKERS) for a in fmp_articles]
  ticker_linked = [a for a in enriched if a['tickers']]
  print(f"{len(ticker_linked)}/{len(enriched)} articles have ticker links")
  ```

- [ ] Cell 5 — build ticker→article index:
  ```python
  def build_ticker_index(articles):
      index = {}
      for article in articles:
          for ticker in article['tickers']:
              index.setdefault(ticker, []).append(article['id'])
      return index

  index = build_ticker_index(enriched)
  print(f"AAPL article count: {len(index.get('AAPL', []))}")
  ```

- [ ] Confirm at least 10 articles link to at least 3 tickers. Commit notebook.

### 2.B: Backend — normalizer and extractor modules

**Files:**
- Create: `backend/news/normalizer.py`
- Create: `backend/news/ticker_extractor.py`
- Modify: `backend/news/tasks.py`
- Modify: `backend/news/views.py`
- Modify: `backend/fintank_backend/urls.py`

- [ ] Create `backend/news/normalizer.py`:
  ```python
  import hashlib, requests, os
  from datetime import datetime

  FMP_URL = os.environ.get('FMP_URL', '')
  FMP_API = os.environ.get('FMP_API', '')

  def _article_id(url: str) -> str:
      return hashlib.md5(url.encode()).hexdigest()

  def fetch_and_normalise_fmp(limit: int = 100) -> list[dict]:
      resp = requests.get(
          f'{FMP_URL}/v3/stock_news',
          params={'limit': limit, 'apikey': FMP_API},
          timeout=15
      )
      resp.raise_for_status()
      results = []
      for item in resp.json():
          results.append({
              'id': _article_id(item['url']),
              'title': item.get('title', ''),
              'summary': item.get('text', '')[:500],
              'url': item['url'],
              'source': 'fmp',
              'published_at': item.get('publishedDate', ''),
              'tickers': [item['symbol']] if item.get('symbol') else [],
              'sectors': [],
              'themes': [],
          })
      return results

  def fetch_and_normalise_newsapi(limit: int = 100) -> list[dict]:
      """Fetch from NewsAPI.org financial category."""
      api_key = os.environ.get('NEWS_SECONDARY_API_KEY', '')
      if not api_key:
          return []
      resp = requests.get(
          'https://newsapi.org/v2/top-headlines',
          params={'category': 'business', 'language': 'en', 'pageSize': limit, 'apiKey': api_key},
          timeout=15
      )
      if not resp.ok:
          return []
      results = []
      for item in resp.json().get('articles', []):
          url = item.get('url', '')
          if not url:
              continue
          results.append({
              'id': _article_id(url),
              'title': item.get('title', ''),
              'summary': item.get('description', '')[:500],
              'url': url,
              'source': 'newsapi',
              'published_at': item.get('publishedAt', ''),
              'tickers': [],
              'sectors': [],
              'themes': [],
          })
      return results
  ```

- [ ] Create `backend/news/ticker_extractor.py`:
  ```python
  import re
  from stockuploader.models import Stock

  def get_known_tickers() -> set:
      """Load all ticker symbols from DB. Cached by caller."""
      return set(Stock.objects.values_list('symbol', flat=True))

  def extract_tickers(text: str, known_tickers: set) -> list[str]:
      """Extract uppercase 1-5 char words that match known tickers."""
      if not text:
          return []
      candidates = re.findall(r'\b([A-Z]{1,5})\b', text)
      # Filter single chars and common English words that look like tickers
      EXCLUDE = {'A', 'I', 'AN', 'AS', 'AT', 'BE', 'BY', 'DO', 'GO', 'HE', 'IN',
                 'IS', 'IT', 'MY', 'NO', 'OF', 'ON', 'OR', 'SO', 'TO', 'UP', 'US',
                 'WE', 'CEO', 'CFO', 'IPO', 'ETF', 'GDP', 'CPI', 'FED'}
      return list(set(c for c in candidates if c in known_tickers and c not in EXCLUDE))

  def enrich_articles(articles: list[dict], known_tickers: set) -> list[dict]:
      for article in articles:
          extracted = extract_tickers(
              article.get('title', '') + ' ' + article.get('summary', ''),
              known_tickers
          )
          article['tickers'] = list(set(article.get('tickers', []) + extracted))
      return articles
  ```

- [ ] Update `backend/news/tasks.py` — replace `update_news_articles` body:
  ```python
  from celery import shared_task
  from django.core.cache import cache
  import gzip, json
  from .normalizer import fetch_and_normalise_fmp, fetch_and_normalise_newsapi
  from .ticker_extractor import get_known_tickers, enrich_articles

  @shared_task
  def update_news_articles():
      known_tickers = get_known_tickers()

      fmp_articles = fetch_and_normalise_fmp(limit=100)
      secondary_articles = fetch_and_normalise_newsapi(limit=100)
      all_articles = fmp_articles + secondary_articles

      enriched = enrich_articles(all_articles, known_tickers)

      # Deduplicate by id
      seen = set()
      unique = []
      for a in enriched:
          if a['id'] not in seen:
              seen.add(a['id'])
              unique.append(a)

      # Build ticker→article_id index
      ticker_index = {}
      for article in unique:
          for ticker in article['tickers']:
              ticker_index.setdefault(ticker, []).append(article['id'])

      # Cache full feed (latest 100)
      feed_payload = gzip.compress(json.dumps(unique[:100]).encode())
      cache.set('news:feed:1:v1', feed_payload, 60 * 30)

      # Cache per-ticker lists
      article_map = {a['id']: a for a in unique}
      for ticker, ids in ticker_index.items():
          ticker_articles = [article_map[i] for i in ids if i in article_map][:20]
          compressed = gzip.compress(json.dumps(ticker_articles).encode())
          cache.set(f'news:ticker:{ticker}:v1', compressed, 60 * 30)

      return {'total': len(unique), 'ticker_links': len(ticker_index)}
  ```

- [ ] Add views to `backend/news/views.py`:
  ```python
  from rest_framework.views import APIView
  from rest_framework.response import Response
  from rest_framework.permissions import IsAuthenticated
  from django.core.cache import cache
  import gzip, json

  class NewsFeedView(APIView):
      permission_classes = [IsAuthenticated]

      def get(self, request):
          page = int(request.query_params.get('page', 1))
          cache_key = f'news:feed:{page}:v1'
          cached = cache.get(cache_key)
          if cached:
              return Response(json.loads(gzip.decompress(cached)))
          return Response({'articles': [], 'message': 'News updating, try again shortly'}, status=202)

  class TickerNewsView(APIView):
      permission_classes = [IsAuthenticated]

      def get(self, request, symbol):
          cache_key = f'news:ticker:{symbol.upper()}:v1'
          cached = cache.get(cache_key)
          if cached:
              return Response(json.loads(gzip.decompress(cached)))
          return Response([], status=200)
  ```

- [ ] Register in `backend/fintank_backend/urls.py`:
  ```python
  path('api/news/feed/', NewsFeedView.as_view()),
  path('api/news/ticker/<str:symbol>/', TickerNewsView.as_view()),
  ```

- [ ] Write tests in `backend/news/tests.py`:
  ```python
  from django.test import TestCase
  from rest_framework.test import APIClient
  from users.models import CustomUser
  from news.ticker_extractor import extract_tickers, enrich_articles

  class TickerExtractorTest(TestCase):
      def test_extracts_known_tickers(self):
          known = {'AAPL', 'MSFT', 'TSLA'}
          result = extract_tickers('Apple (AAPL) beats MSFT in revenue', known)
          self.assertIn('AAPL', result)
          self.assertIn('MSFT', result)

      def test_excludes_common_words(self):
          known = {'A', 'IN', 'AAPL'}
          result = extract_tickers('A company IN trouble, buy AAPL', known)
          self.assertNotIn('A', result)
          self.assertNotIn('IN', result)
          self.assertIn('AAPL', result)

  class NewsAPITest(TestCase):
      def setUp(self):
          self.client = APIClient()
          self.user = CustomUser.objects.create_user(
              email='t@t.com', password='pass', first_name='T', last_name='U'
          )
          self.client.force_authenticate(user=self.user)

      def test_feed_returns_200_or_202(self):
          resp = self.client.get('/api/news/feed/')
          self.assertIn(resp.status_code, [200, 202])

      def test_ticker_news_returns_200(self):
          resp = self.client.get('/api/news/ticker/AAPL/')
          self.assertEqual(resp.status_code, 200)
  ```

- [ ] Run tests: `cd backend && python manage.py test news`
- [ ] Run task manually: `from news.tasks import update_news_articles; update_news_articles.apply()`
- [ ] Wire news into stock detail page — update `src/hooks/useStockDetail.js` to call `/api/news/ticker/<ticker>/` separately and merge into state, OR update `StockDetailView` to include ticker news in the response
- [ ] Commit: `git commit -am "feat(news): multi-source ingestion with ticker extraction"`

---

## Phase 3 — Watchlist App

**Produces:** New `watchlist` Django app with entry-price tracking, P&L calculation, and enhanced frontend watchlist page.

**Spec reference:** §8.5

**Prerequisite:** Phase 1 (can share stock detail page's price fetching pattern).

### 3.A: Notebook prototype

**File:** `backend/class_files/watchlist_performance.ipynb`

- [ ] Create notebook. Cell 1 — imports:
  ```python
  import os, django, requests
  os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fintank_backend.settings')
  django.setup()
  FMP_API = os.environ['FMP_API']
  FMP_URL = os.environ['FMP_URL']
  ```

- [ ] Cell 2 — live price fetch for a list of symbols:
  ```python
  def fetch_quotes(symbols: list) -> dict:
      """Returns {symbol: {price, changesPercentage}} for a list of symbols."""
      joined = ','.join(symbols)
      resp = requests.get(f'{FMP_URL}/v3/quote/{joined}', params={'apikey': FMP_API}, timeout=10)
      return {item['symbol']: item for item in resp.json()}

  test_symbols = ['AAPL', 'MSFT', 'TSLA']
  quotes = fetch_quotes(test_symbols)
  for sym, q in quotes.items():
      print(f"{sym}: ${q['price']:.2f} ({q['changesPercentage']:+.2f}%)")
  ```

- [ ] Cell 3 — P&L calculation from hypothetical watchlist entries:
  ```python
  from decimal import Decimal

  watchlist_entries = [
      {'symbol': 'AAPL', 'entry_price': Decimal('170.00')},
      {'symbol': 'MSFT', 'entry_price': Decimal('380.00')},
  ]

  def calculate_pnl(entries, current_quotes):
      results = []
      for entry in entries:
          sym = entry['symbol']
          current = Decimal(str(current_quotes[sym]['price']))
          entry_price = entry['entry_price']
          pct_change = ((current - entry_price) / entry_price * 100).quantize(Decimal('0.01'))
          results.append({**entry, 'current_price': float(current), 'pct_change': float(pct_change)})
      return results

  pnl = calculate_pnl(watchlist_entries, quotes)
  for row in pnl:
      print(f"{row['symbol']}: entry=${row['entry_price']}, now=${row['current_price']:.2f}, change={row['pct_change']:+.2f}%")
  ```

- [ ] Confirm P&L math is correct for positive and negative cases. Commit notebook.

### 3.B: Backend — `watchlist` Django app

**Files:**
- Create: `backend/watchlist/` (full app scaffold)
- Modify: `backend/fintank_backend/settings.py`
- Modify: `backend/fintank_backend/urls.py`
- Modify: `backend/users/models.py` (add `subscription_tier`)

- [ ] Create app: `cd backend && python manage.py startapp watchlist`

- [ ] `backend/watchlist/models.py`:
  ```python
  from django.db import models
  from users.models import CustomUser

  ASSET_TYPES = [('stock', 'Stock'), ('etf', 'ETF'), ('crypto', 'Crypto'), ('index', 'Index')]

  class WatchlistEntry(models.Model):
      user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='watchlist')
      symbol = models.CharField(max_length=20)
      asset_type = models.CharField(max_length=10, choices=ASSET_TYPES, default='stock')
      added_at = models.DateTimeField(auto_now_add=True)
      entry_price = models.DecimalField(max_digits=14, decimal_places=4)
      notes = models.TextField(blank=True)

      class Meta:
          unique_together = ('user', 'symbol')
          ordering = ['-added_at']

      def __str__(self):
          return f"{self.user.email} - {self.symbol}"
  ```

- [ ] Add `subscription_tier` to `backend/users/models.py` on `UserProfile`:
  ```python
  SUBSCRIPTION_TIERS = [('free', 'Free'), ('premium', 'Premium'), ('institutional', 'Institutional')]

  class UserProfile(models.Model):
      # ... existing fields ...
      subscription_tier = models.CharField(max_length=20, choices=SUBSCRIPTION_TIERS, default='free')
  ```

- [ ] `backend/watchlist/views.py`:
  ```python
  from rest_framework.views import APIView
  from rest_framework.response import Response
  from rest_framework.permissions import IsAuthenticated
  from django.core.cache import cache
  import gzip, json, requests, os
  from .models import WatchlistEntry

  def _fetch_current_price(symbol: str) -> float:
      resp = requests.get(
          f"{os.environ['FMP_URL']}/v3/quote/{symbol}",
          params={'apikey': os.environ['FMP_API']}, timeout=8
      )
      data = resp.json()
      return float(data[0]['price']) if resp.ok and data else 0.0

  class WatchlistView(APIView):
      permission_classes = [IsAuthenticated]

      def get(self, request):
          entries = WatchlistEntry.objects.filter(user=request.user)
          symbols = [e.symbol for e in entries]
          if not symbols:
              return Response([])

          # Batch quote fetch
          joined = ','.join(symbols)
          resp = requests.get(
              f"{os.environ['FMP_URL']}/v3/quote/{joined}",
              params={'apikey': os.environ['FMP_API']}, timeout=10
          )
          quotes = {q['symbol']: q for q in (resp.json() if resp.ok else [])}

          result = []
          for entry in entries:
              current = float(quotes.get(entry.symbol, {}).get('price', 0))
              entry_p = float(entry.entry_price)
              pct = round((current - entry_p) / entry_p * 100, 2) if entry_p else 0
              result.append({
                  'id': entry.id, 'symbol': entry.symbol, 'asset_type': entry.asset_type,
                  'added_at': entry.added_at.isoformat(), 'entry_price': entry_p,
                  'current_price': current, 'pct_change': pct, 'notes': entry.notes,
              })
          return Response(result)

  class WatchlistAddView(APIView):
      permission_classes = [IsAuthenticated]

      def post(self, request):
          symbol = request.data.get('symbol', '').upper()
          asset_type = request.data.get('asset_type', 'stock')
          notes = request.data.get('notes', '')
          if not symbol:
              return Response({'error': 'symbol required'}, status=400)
          if WatchlistEntry.objects.filter(user=request.user, symbol=symbol).exists():
              return Response({'error': 'Already in watchlist'}, status=409)
          entry_price = _fetch_current_price(symbol)
          if entry_price == 0:
              return Response({'error': f'Could not fetch price for {symbol}'}, status=400)
          entry = WatchlistEntry.objects.create(
              user=request.user, symbol=symbol, asset_type=asset_type,
              entry_price=entry_price, notes=notes
          )
          return Response({'id': entry.id, 'symbol': symbol, 'entry_price': entry_price}, status=201)

  class WatchlistRemoveView(APIView):
      permission_classes = [IsAuthenticated]

      def delete(self, request, pk):
          try:
              entry = WatchlistEntry.objects.get(pk=pk, user=request.user)
              entry.delete()
              return Response(status=204)
          except WatchlistEntry.DoesNotExist:
              return Response({'error': 'Not found'}, status=404)
  ```

- [ ] `backend/watchlist/urls.py`:
  ```python
  from django.urls import path
  from .views import WatchlistView, WatchlistAddView, WatchlistRemoveView

  urlpatterns = [
      path('', WatchlistView.as_view()),
      path('add/', WatchlistAddView.as_view()),
      path('<int:pk>/remove/', WatchlistRemoveView.as_view()),
  ]
  ```

- [ ] Register in `backend/fintank_backend/urls.py`:
  ```python
  path('api/watchlist/', include('watchlist.urls')),
  ```

- [ ] Add `'watchlist'` to `INSTALLED_APPS` in `backend/fintank_backend/settings.py`

- [ ] Run migrations: `python manage.py makemigrations watchlist users && python manage.py migrate`

- [ ] Write tests in `backend/watchlist/tests.py`:
  ```python
  from django.test import TestCase
  from rest_framework.test import APIClient
  from users.models import CustomUser
  from watchlist.models import WatchlistEntry
  from unittest.mock import patch

  class WatchlistTest(TestCase):
      def setUp(self):
          self.client = APIClient()
          self.user = CustomUser.objects.create_user(
              email='w@t.com', password='p', first_name='W', last_name='U'
          )
          self.client.force_authenticate(user=self.user)

      @patch('watchlist.views._fetch_current_price', return_value=150.0)
      def test_add_to_watchlist(self, mock_price):
          resp = self.client.post('/api/watchlist/add/', {'symbol': 'AAPL', 'asset_type': 'stock'})
          self.assertEqual(resp.status_code, 201)
          self.assertEqual(resp.data['entry_price'], 150.0)
          self.assertEqual(WatchlistEntry.objects.filter(user=self.user).count(), 1)

      @patch('watchlist.views._fetch_current_price', return_value=150.0)
      def test_duplicate_add_returns_409(self, mock_price):
          self.client.post('/api/watchlist/add/', {'symbol': 'AAPL'})
          resp = self.client.post('/api/watchlist/add/', {'symbol': 'AAPL'})
          self.assertEqual(resp.status_code, 409)

      def test_remove_from_watchlist(self):
          entry = WatchlistEntry.objects.create(
              user=self.user, symbol='MSFT', entry_price=380.0
          )
          resp = self.client.delete(f'/api/watchlist/{entry.pk}/remove/')
          self.assertEqual(resp.status_code, 204)
          self.assertFalse(WatchlistEntry.objects.filter(pk=entry.pk).exists())
  ```

- [ ] Run tests: `python manage.py test watchlist`
- [ ] Create `src/hooks/useWatchlistPerformance.js` following same pattern as `useStockDetail.js`
- [ ] Create `src/pages/watchlist.js` with add/remove controls and P&L table
- [ ] Commit: `git commit -am "feat(watchlist): entry-price tracking and P&L API"`

---

## Phase 4 — Factor Engine & Decile Analysis

**Produces:** New `factor_engine` Django app. Celery task computes Z-score factor scores for SP500/TSX/NASDAQ universes, stores to S3 + Redis. API and frontend factor rankings page.

**Spec reference:** §8.6

**Prerequisite:** Phase 3 (`subscription_tier` on UserProfile exists). Uses existing `FundamentalMetricTTM`, `FundamentalRatioTTM`, `IncomeStatement` models.

### 4.A: Notebook prototype

**File:** `backend/class_files/factor_engine_scoring.ipynb`

- [ ] Create notebook. Cell 1 — imports:
  ```python
  import os, django
  os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fintank_backend.settings')
  django.setup()
  from stockuploader.models import FundamentalMetricTTM, FundamentalRatioTTM, IncomeStatement
  import pandas as pd
  from scipy import stats
  ```

- [ ] Cell 2 — load universe data into DataFrame:
  ```python
  def load_factor_data(universe_symbols: list) -> pd.DataFrame:
      metrics = pd.DataFrame(
          FundamentalMetricTTM.objects.filter(symbol__in=universe_symbols).values(
              'symbol', 'pe_ratio', 'price_to_book_ratio', 'ev_to_ebitda',
              'free_cash_flow_per_share', 'roe', 'roic', 'gross_profit_margin',
              'debt_to_equity'
          )
      )
      # Price-to-FCF yield = 1 / (price/FCF) — approximate from available fields
      return metrics

  # Use a small test universe
  test_universe = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'JPM', 'JNJ', 'XOM']
  df = load_factor_data(test_universe)
  print(df.shape)
  print(df.head())
  ```

- [ ] Cell 3 — Z-score normalisation per factor:
  ```python
  VALUE_COLS = ['pe_ratio', 'price_to_book_ratio', 'ev_to_ebitda']
  QUALITY_COLS = ['roe', 'roic', 'gross_profit_margin']

  def zscore_col(series: pd.Series, invert: bool = False) -> pd.Series:
      """Z-score, optionally inverted (for factors where lower = better, e.g. P/E)."""
      z = stats.zscore(series.fillna(series.median()))
      return -z if invert else z

  df['z_pe'] = zscore_col(df['pe_ratio'], invert=True)      # lower P/E = better value
  df['z_pb'] = zscore_col(df['price_to_book_ratio'], invert=True)
  df['z_ev_ebitda'] = zscore_col(df['ev_to_ebitda'], invert=True)
  df['z_roe'] = zscore_col(df['roe'])
  df['z_roic'] = zscore_col(df['roic'])

  df['value_score'] = df[['z_pe', 'z_pb', 'z_ev_ebitda']].mean(axis=1)
  df['quality_score'] = df[['z_roe', 'z_roic']].mean(axis=1)
  df['composite_score'] = df[['value_score', 'quality_score']].mean(axis=1)

  print(df[['symbol', 'value_score', 'quality_score', 'composite_score']].sort_values('composite_score', ascending=False))
  ```

- [ ] Cell 4 — decile assignment:
  ```python
  def assign_decile(series: pd.Series) -> pd.Series:
      return pd.qcut(series.rank(method='first'), q=10, labels=list(range(1, 11))).astype(int)

  df['composite_decile'] = assign_decile(df['composite_score'])
  print(df[['symbol', 'composite_score', 'composite_decile']].sort_values('composite_decile'))
  ```

- [ ] Confirm scores are numeric, non-NaN for majority of universe. Assert composite_decile values are 1–10. Commit notebook.

### 4.B: Backend — `factor_engine` Django app

**Files:**
- Create: `backend/factor_engine/` (full app)
- Modify: `backend/fintank_backend/settings.py`
- Modify: `backend/fintank_backend/urls.py`
- Modify: `backend/fintank_backend/celery.py`

- [ ] Create app: `cd backend && python manage.py startapp factor_engine`

- [ ] `backend/factor_engine/engine/compute.py` (pure computation, no Django imports):
  ```python
  import pandas as pd
  from scipy import stats

  FACTOR_CONFIG = {
      'value': {
          'cols': [('pe_ratio', True), ('price_to_book_ratio', True), ('ev_to_ebitda', True)],
          'description': 'Low P/E, P/B, EV/EBITDA',
      },
      'quality': {
          'cols': [('roe', False), ('roic', False), ('gross_profit_margin', False)],
          'description': 'High ROE, ROIC, Gross Margin',
      },
  }

  def zscore(series: pd.Series, invert: bool = False) -> pd.Series:
      filled = series.fillna(series.median())
      z = stats.zscore(filled)
      return pd.Series(-z if invert else z, index=series.index)

  def compute_factor_scores(df: pd.DataFrame) -> pd.DataFrame:
      """
      Input: DataFrame with columns symbol + all factor metric columns.
      Output: DataFrame with symbol, individual factor scores, composite_score, composite_decile.
      """
      score_cols = []
      for factor_name, config in FACTOR_CONFIG.items():
          z_cols = []
          for col, invert in config['cols']:
              if col in df.columns:
                  z_col = f'z_{col}'
                  df[z_col] = zscore(df[col], invert=invert)
                  z_cols.append(z_col)
          if z_cols:
              df[f'{factor_name}_score'] = df[z_cols].mean(axis=1)
              score_cols.append(f'{factor_name}_score')

      if score_cols:
          df['composite_score'] = df[score_cols].mean(axis=1)
          df['composite_decile'] = pd.qcut(
              df['composite_score'].rank(method='first'), q=10,
              labels=list(range(1, 11))
          ).astype(int)

      return df

  def build_decile_summary(df: pd.DataFrame, factor_col: str = 'composite_score') -> list[dict]:
      """Return median score per decile for chart display."""
      df['decile'] = pd.qcut(df[factor_col].rank(method='first'), q=10, labels=list(range(1, 11))).astype(int)
      return df.groupby('decile')[factor_col].median().reset_index().rename(
          columns={factor_col: 'median_score'}
      ).to_dict(orient='records')
  ```

- [ ] `backend/factor_engine/tasks.py`:
  ```python
  from celery import shared_task
  from django.core.cache import cache
  from stockuploader.models import FundamentalMetricTTM, FundamentalRatioTTM
  from utils.StockCalculations import GetData
  import pandas as pd, gzip, json, io, boto3, os
  from .engine.compute import compute_factor_scores

  UNIVERSES = {
      'SP500': 'sp500',     # map to peer list file names
      'TSX': 'tsx',
      'NASDAQ': 'nasdaq',
  }

  @shared_task(bind=True, max_retries=3)
  def compute_factor_scores_task(self, universe: str = 'SP500'):
      try:
          # Load universe symbols (reuse existing peer lists)
          from utils.SP500PeerList import sp500_symbols
          symbols = sp500_symbols if universe == 'SP500' else []
          if not symbols:
              return {'error': f'No symbols for universe {universe}'}

          # Build DataFrame from DB
          metrics_qs = FundamentalMetricTTM.objects.filter(symbol__in=symbols).values(
              'symbol', 'pe_ratio', 'price_to_book_ratio', 'ev_to_ebitda', 'roe', 'roic',
          )
          ratios_qs = FundamentalRatioTTM.objects.filter(symbol__in=symbols).values(
              'symbol', 'gross_profit_margin', 'debt_equity_ratio',
          )
          df_m = pd.DataFrame(metrics_qs)
          df_r = pd.DataFrame(ratios_qs)
          df = df_m.merge(df_r, on='symbol', how='left')

          # Compute scores
          df = compute_factor_scores(df)

          # Serialise
          output = df.to_dict(orient='records')

          # Write to S3
          s3 = boto3.client('s3')
          key = f'factor_scores/{universe}/{pd.Timestamp.today().strftime("%Y-%m-%d")}.json'
          s3.put_object(
              Bucket=os.environ['AWS_BUCKET_NAME'],
              Key=key,
              Body=json.dumps(output, default=str).encode()
          )

          # Cache
          compressed = gzip.compress(json.dumps(output, default=str).encode())
          cache.set(f'factor:{universe}:composite:v1', compressed, 60 * 60 * 24)

          return {'universe': universe, 'symbols': len(output)}

      except Exception as exc:
          raise self.retry(exc=exc, countdown=60)
  ```

- [ ] `backend/factor_engine/views.py`:
  ```python
  from rest_framework.views import APIView
  from rest_framework.response import Response
  from rest_framework.permissions import IsAuthenticated
  from django.core.cache import cache
  import gzip, json

  class FactorScoresView(APIView):
      permission_classes = [IsAuthenticated]

      def get(self, request, universe):
          cache_key = f'factor:{universe.upper()}:composite:v1'
          cached = cache.get(cache_key)
          if cached:
              return Response(json.loads(gzip.decompress(cached)))
          return Response({'message': 'Factor scores computing', 'universe': universe}, status=202)

  class FactorTickerView(APIView):
      permission_classes = [IsAuthenticated]

      def get(self, request, symbol):
          # Check all universe caches for this symbol's scores
          for universe in ['SP500', 'TSX', 'NASDAQ']:
              cached = cache.get(f'factor:{universe}:composite:v1')
              if cached:
                  scores = json.loads(gzip.decompress(cached))
                  match = next((s for s in scores if s['symbol'] == symbol.upper()), None)
                  if match:
                      return Response(match)
          return Response({}, status=200)
  ```

- [ ] Register URLs, add to `INSTALLED_APPS`, run migrations (no new models needed — factor_engine has no DB models)
- [ ] Write tests confirming `compute_factor_scores` returns correct column structure and decile range 1-10
- [ ] Create `src/hooks/useFactorScores.js` and `src/pages/factor-rankings.js` with universe/factor selector and sortable table
- [ ] Commit: `git commit -am "feat(factor_engine): factor scoring and decile analysis"`

---

## Phase 5 — Backtesting Engine V1

> ⚠️ **DEFERRED — DO NOT IMPLEMENT. Read this before touching anything below.**
>
> The `backtester` Django app is now defined by
> **`docs/superpowers/specs/2026-08-11-portfolio-backtest-design.md`** (portfolio
> construction, optimization and simulation), which is the canonical design for that app.
>
> Phase 5 here describes a *different* product — factor/quintile **signal** backtesting —
> and is deferred indefinitely. It is **not** a prerequisite for the portfolio backtester
> and must not be built, stubbed, or scaffolded alongside it.
>
> Much of what Phase 5 describes is in any case already delivered by
> `/api/getstockquintiles/` and the `/factor-performance` page, so this phase should be
> re-scoped from scratch before anyone revives it.
>
> **If revived, it must adapt to the portfolio backtester, not the reverse:**
> - `BacktestJob` → rename to `SignalBacktestJob` (the portfolio app owns `BacktestRun`)
> - views → `Signal…` prefixes (the portfolio app owns the unprefixed names)
> - frontend → `/backtester` (the portfolio app owns `/backtest-portfolio`)

**Produces:** `backtester` Django app with async signal backtesting. User submits job → Celery task → results to S3 → polling API → frontend results page.

**Spec reference:** §8.7

**Prerequisite:** Phase 4 (factor engine validates that factor data is available and reliable).

### 5.A: Notebook prototype

**File:** `backend/class_files/backtester_signal.ipynb`

- [ ] Create notebook. Cell 1 — imports:
  ```python
  import os, django
  os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fintank_backend.settings')
  django.setup()
  import pandas as pd, numpy as np, requests
  from stockuploader.models import FundamentalMetricTTM
  FMP_API = os.environ['FMP_API']
  FMP_URL = os.environ['FMP_URL']
  ```

- [ ] Cell 2 — build historical factor snapshot (simplified using current TTM data):
  ```python
  # Simplified: use current TTM data as a single snapshot
  # Real V1 will iterate over quarterly snapshots
  from utils.SP500PeerList import sp500_symbols
  metrics = list(FundamentalMetricTTM.objects.filter(symbol__in=sp500_symbols[:50]).values('symbol', 'pe_ratio', 'roe'))
  df = pd.DataFrame(metrics).dropna()
  df['pe_rank'] = df['pe_ratio'].rank(ascending=True)  # lower P/E = better rank
  df['quintile'] = pd.qcut(df['pe_rank'], q=5, labels=[1,2,3,4,5]).astype(int)
  print(df.groupby('quintile').size())
  ```

- [ ] Cell 3 — simulate forward return calculation:
  ```python
  def fetch_price_change(symbol, start_date, end_date):
      """Fetch start and end price from FMP historical data."""
      resp = requests.get(
          f'{FMP_URL}/v3/historical-price-full/{symbol}',
          params={'from': start_date, 'to': end_date, 'apikey': FMP_API}, timeout=10
      )
      data = resp.json().get('historical', [])
      if len(data) < 2:
          return None
      start_price = data[-1]['close']
      end_price = data[0]['close']
      return (end_price - start_price) / start_price

  # Test on one symbol
  chg = fetch_price_change('AAPL', '2023-01-01', '2024-01-01')
  print(f"AAPL 2023 return: {chg:.2%}")
  ```

- [ ] Cell 4 — compute quintile returns and IC:
  ```python
  def information_coefficient(factor_ranks, forward_returns):
      """Spearman rank correlation between factor ranks and forward returns."""
      from scipy.stats import spearmanr
      corr, _ = spearmanr(factor_ranks, forward_returns)
      return round(corr, 4)

  # Simulate with random returns for structure validation
  np.random.seed(42)
  df['forward_return'] = np.random.normal(0.05, 0.20, len(df))
  ic = information_coefficient(df['pe_rank'], df['forward_return'])
  quintile_returns = df.groupby('quintile')['forward_return'].mean()
  print(f"IC: {ic}")
  print(quintile_returns)
  ```

- [ ] Validate that IC is between -1 and 1 and quintile_returns has 5 entries. Commit notebook.

### 5.B: Backend — `backtester` Django app

**Files:**
- Create: `backend/backtester/` (full app)
- Key files: `models.py`, `tasks.py`, `views.py`, `urls.py`, `engine/signal.py`

- [ ] `backend/backtester/models.py`:
  ```python
  from django.db import models
  from users.models import CustomUser
  import uuid

  class BacktestJob(models.Model):
      STATUS_CHOICES = [('queued','Queued'),('running','Running'),('complete','Complete'),('failed','Failed')]
      id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
      user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
      universe = models.CharField(max_length=20)
      factor = models.CharField(max_length=50)
      start_date = models.DateField()
      end_date = models.DateField()
      rebalance_freq = models.CharField(max_length=20, default='quarterly')
      n_quintiles = models.IntegerField(default=5)
      status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
      s3_result_key = models.CharField(max_length=255, blank=True)
      created_at = models.DateTimeField(auto_now_add=True)
      completed_at = models.DateTimeField(null=True, blank=True)
      error_message = models.TextField(blank=True)

      class Meta:
          ordering = ['-created_at']
  ```

- [ ] `backend/backtester/engine/signal.py`:
  ```python
  import pandas as pd
  import numpy as np
  from scipy.stats import spearmanr

  def compute_quintile_returns(factor_series: pd.Series, return_series: pd.Series,
                                n_quintiles: int = 5) -> pd.DataFrame:
      """
      Given factor values and forward returns for a universe at one rebalance date,
      compute average return per quintile.
      """
      df = pd.DataFrame({'factor': factor_series, 'fwd_return': return_series}).dropna()
      df['quintile'] = pd.qcut(df['factor'].rank(method='first'), q=n_quintiles,
                                labels=list(range(1, n_quintiles + 1))).astype(int)
      return df.groupby('quintile')['fwd_return'].agg(['mean', 'std', 'count']).reset_index()

  def information_coefficient(factor_values: pd.Series, forward_returns: pd.Series) -> float:
      df = pd.DataFrame({'f': factor_values, 'r': forward_returns}).dropna()
      if len(df) < 5:
          return 0.0
      corr, _ = spearmanr(df['f'], df['r'])
      return round(float(corr), 4)

  def max_drawdown(return_series: pd.Series) -> float:
      cumulative = (1 + return_series).cumprod()
      rolling_max = cumulative.expanding().max()
      drawdowns = (cumulative - rolling_max) / rolling_max
      return round(float(drawdowns.min()), 4)
  ```

- [ ] `backend/backtester/tasks.py` (outline — full implementation requires iterating quarterly snapshots):
  ```python
  from celery import shared_task
  from django.utils import timezone
  import boto3, json, os
  from .models import BacktestJob
  from .engine.signal import compute_quintile_returns, information_coefficient

  @shared_task(bind=True, max_retries=2)
  def run_signal_backtest(self, job_id: str):
      job = BacktestJob.objects.get(id=job_id)
      job.status = 'running'
      job.save(update_fields=['status'])

      try:
          # Simplified single-period backtest for V1
          # Full multi-period implementation iterates rebalance dates
          from stockuploader.models import FundamentalMetricTTM
          import pandas as pd, numpy as np

          metrics = list(FundamentalMetricTTM.objects.filter(
              symbol__isnull=False
          ).values('symbol', job.factor)[:200])

          df = pd.DataFrame(metrics).dropna()
          if df.empty:
              raise ValueError(f"No data for factor {job.factor}")

          # Simulate forward returns (V1 uses random for structure; real impl fetches FMP historical)
          np.random.seed(42)
          df['fwd_return'] = np.random.normal(0.08, 0.25, len(df))

          quintile_returns = compute_quintile_returns(df[job.factor], df['fwd_return'], job.n_quintiles)
          ic = information_coefficient(df[job.factor], df['fwd_return'])

          result = {
              'job_id': job_id,
              'universe': job.universe,
              'factor': job.factor,
              'ic': ic,
              'quintile_returns': quintile_returns.to_dict(orient='records'),
              'summary': {
                  'n_stocks': len(df),
                  'ic': ic,
                  'q1_return': quintile_returns.loc[quintile_returns['quintile'] == 1, 'mean'].values[0],
                  'q5_return': quintile_returns.loc[quintile_returns['quintile'] == job.n_quintiles, 'mean'].values[0],
              }
          }

          # Write to S3
          s3 = boto3.client('s3')
          key = f'backtest_results/{job_id}.json'
          s3.put_object(Bucket=os.environ['AWS_BUCKET_NAME'], Key=key,
                        Body=json.dumps(result, default=str).encode())

          job.status = 'complete'
          job.s3_result_key = key
          job.completed_at = timezone.now()
          job.save(update_fields=['status', 's3_result_key', 'completed_at'])

          return {'job_id': job_id, 'status': 'complete'}

      except Exception as exc:
          job.status = 'failed'
          job.error_message = str(exc)
          job.save(update_fields=['status', 'error_message'])
          raise self.retry(exc=exc, countdown=30)
  ```

- [ ] `backend/backtester/views.py` with `RunBacktestView`, `BacktestStatusView`, `BacktestResultsView`, `BacktestHistoryView`
- [ ] Migrations, URL registration, `INSTALLED_APPS`
- [ ] Tests covering: submit job creates `BacktestJob`, status endpoint returns correct state, result endpoint fetches from S3
- [ ] Frontend: `src/pages/backtester.js` with parameter form and polling results display
- [ ] Commit: `git commit -am "feat(backtester): signal backtesting engine V1"`

---

## Phase 6 — Market Overview & Spread Analysis Enhancements

**Produces:** Market breadth indicator, VIX + bond yield summary strip, news ticker tags on home page carousel, CSV export on spread charts, and custom spread pair persistence.

**Spec reference:** §8.1, §8.4

**Prerequisite:** Phase 2 (news articles have ticker tags).

### 6.A: Market breadth

- [ ] Add `get_market_breadth()` to `backend/analyzer/analyzer_utils/CorePerformanceTools.py`:
  ```python
  def get_market_breadth():
      """Fetch advancing/declining stock count from FMP."""
      cache_key = 'home:market_breadth:v1'
      cached = cache.get(cache_key)
      if cached:
          return json.loads(gzip.decompress(cached))
      resp = requests.get(f"{FMP_URL}/v3/market-breadth", params={'apikey': FMP_API}, timeout=8)
      data = resp.json() if resp.ok else {}
      compressed = gzip.compress(json.dumps(data).encode())
      cache.set(cache_key, compressed, 60 * 10)
      return data
  ```

- [ ] Add `class MarketBreadthView(APIView)` in `backend/analyzer/views.py` calling `get_market_breadth()`, register as `GET /api/market-breadth/`
- [ ] Add Celery task `update_market_breadth` in `backend/analyzer/tasks.py`, scheduled every 10 min (market hours)
- [ ] Update `src/pages/index.js` to add VIX/bond strip at top (reuse existing `useVixChart` and `useCapitalMarketsCharts` hooks)
- [ ] Update `src/componentsLegacy/CardNews.js` — add ticker badge rendering:
  ```javascript
  // Inside article card render, after title:
  {article.tickers?.map(t => (
    <span key={t} className="badge bg-secondary me-1" style={{fontSize:'0.7rem'}}>{t}</span>
  ))}
  ```
- [ ] Write test: `MarketBreadthView` returns 200 or 202; `update_market_breadth.apply()` returns a dict
- [ ] Commit: `git commit -am "feat(homepage): breadth indicator, VIX strip, news ticker tags"`

### 6.B: Spread analysis enhancements (spec §8.4)

**Files:**
- Modify: `src/componentsLegacy/EquityCharts.js`
- Modify: `backend/users/models.py` (add `saved_spreads` to `UserProfile`)

- [ ] Add `saved_spreads` to `UserProfile` in `backend/users/models.py`:
  ```python
  saved_spreads = models.JSONField(default=list, blank=True)
  # Format: [{"label": "SPY vs QQQ", "ticker_a": "SPY", "ticker_b": "QQQ"}]
  ```

- [ ] Run migration: `python manage.py makemigrations users && python manage.py migrate`

- [ ] Add CSV export button to `src/componentsLegacy/EquityCharts.js`. Place after the existing frequency selector:
  ```javascript
  function exportToCSV(chartData, label) {
    const rows = [['Date', 'Value A', 'Value B', 'Spread']];
    chartData.labels.forEach((date, i) => {
      rows.push([date, chartData.datasets[0].data[i], chartData.datasets[1].data[i],
                 chartData.datasets[0].data[i] - chartData.datasets[1].data[i]]);
    });
    const csv = rows.map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${label}.csv`; a.click();
  }

  // In JSX render, add:
  // <button className="btn btn-sm btn-outline-secondary ms-2" onClick={() => exportToCSV(chartData, 'spread-export')}>Export CSV</button>
  ```

- [ ] Verify CSV downloads correctly with date, value A, value B, spread columns
- [ ] Commit: `git commit -am "feat(spreads): CSV export and saved_spreads field on UserProfile"`

---

## Phase 7 — Screener Enhancements

**Produces:** Factor score filtering and market cap/P/E range filters in the existing screener. Each result links to the stock detail page.

**Spec reference:** §8.8

**Prerequisite:** Phase 4 (factor engine data available in Redis).

- [ ] Extend screener API endpoint in `backend/analyzer/views.py` to accept `min_composite_score`, `max_pe`, `min_market_cap`, `country` query params
- [ ] Update `src/componentsLegacy/Screener.js` to add filter inputs for new params
- [ ] Update `src/componentsLegacy/ScreenerPagination.js` to link ticker to `/stock-data/[ticker]`
- [ ] Commit: `git commit -am "feat(screener): factor score filters and stock detail links"`

---

## Phase 8 — ETF, Index & Crypto Detail Pages

**Produces:** `/etf/[ticker]`, `/indices/[symbol]`, `/crypto/[symbol]` pages each following the same three-layer pattern established in Phase 1: backend API endpoint → SWR hook → Next.js page.

**Spec reference:** §8.2

**Prerequisite:** Phase 1 (stock detail page as the template to clone and adapt).

### 8.A: ETF detail page

- [ ] Add `ETFDetailView` to `backend/analyzer/views.py` — fetches FMP `/v3/etf-holder/<ticker>` for top holdings and uses existing `useSectorExposure` data:
  ```python
  class ETFDetailView(APIView):
      permission_classes = [IsAuthenticated]
      def get(self, request, symbol):
          symbol = symbol.upper()
          cache_key = f'etf:detail:{symbol}:v1'
          cached = cache.get(cache_key)
          if cached:
              return Response(json.loads(gzip.decompress(cached)))
          quote = requests.get(f"{os.environ['FMP_URL']}/v3/quote/{symbol}",
                               params={'apikey': os.environ['FMP_API']}, timeout=8).json()
          holders = requests.get(f"{os.environ['FMP_URL']}/v3/etf-holder/{symbol}",
                                 params={'apikey': os.environ['FMP_API']}, timeout=8).json()
          data = {'quote': quote[0] if quote else {}, 'holders': holders[:10]}
          cache.set(cache_key, gzip.compress(json.dumps(data, default=str).encode()), 300)
          return Response(data)
  ```
- [ ] Register `GET /api/etf-detail/<str:symbol>/`
- [ ] Create `src/hooks/useETFDetail.js` — same pattern as `useStockDetail.js`, calls `/api/etf-detail/<ticker>/`
- [ ] Create `src/pages/etf/[ticker].js` — header strip (price, change), top-10 holdings table, sector exposure bar chart (reuse `useSectorExposure` hook), news feed (reuse `useTickerNews` from Phase 2)
- [ ] Test: navigate to `http://localhost:8020/etf/SPY`, confirm holdings table and chart render
- [ ] Commit: `git commit -am "feat(frontend): ETF detail page"`

### 8.B: Index detail page

- [ ] Create `src/pages/indices/[symbol].js` — reuse existing `useIndexChart` for price chart, existing `/constituent-returns/<universe>/` for heatmap, existing `useIndexHeatMap` hook. No new backend endpoint needed.
- [ ] Test: navigate to `http://localhost:8020/indices/SPX`, confirm chart and heatmap render
- [ ] Commit: `git commit -am "feat(frontend): Index detail page"`

### 8.C: Crypto detail page

- [ ] Add `CryptoDetailView` to `backend/analyzer/views.py` — same structure as `ETFDetailView`, calls FMP `/v3/quote/<symbol>` and `/v3/historical-price-full/<symbol>`:
  ```python
  class CryptoDetailView(APIView):
      permission_classes = [IsAuthenticated]
      def get(self, request, symbol):
          symbol = symbol.upper()
          cache_key = f'crypto:detail:{symbol}:v1'
          cached = cache.get(cache_key)
          if cached:
              return Response(json.loads(gzip.decompress(cached)))
          quote = requests.get(f"{os.environ['FMP_URL']}/v3/quote/{symbol}",
                               params={'apikey': os.environ['FMP_API']}, timeout=8).json()
          data = {'quote': quote[0] if quote else {}}
          cache.set(cache_key, gzip.compress(json.dumps(data, default=str).encode()), 60)
          return Response(data)
  ```
- [ ] Register `GET /api/crypto-detail/<str:symbol>/`
- [ ] Create `src/hooks/useCryptoDetail.js` and `src/pages/crypto/[symbol].js` — header strip (price, 24h change, market cap, volume), price chart (reuse `useNewCandleSticks`)
- [ ] Test: navigate to `http://localhost:8020/crypto/BTCUSD`, confirm data renders
- [ ] Commit: `git commit -am "feat(frontend): Crypto detail page"`

---

## Phase 9 — Custom Analytics Module Framework

**Produces:** Documented module contract and a template app that demonstrates the pattern, so future research modules can be added consistently.

**Spec reference:** §8.9, §5 (Feature Extensibility)

**Prerequisite:** Phases 4–8 complete (patterns proven in production).

- [ ] Create `backend/analytics_template/` as a minimal example module with `tasks.py`, `views.py`, `urls.py`, `engine/compute.py`
- [ ] Document the module contract in `docs/superpowers/specs/module-contract.md`
- [ ] Add `subscription_tier` field to each module's config (`MODULE_TIER = 'free' | 'premium'`)
- [ ] Update `src/data/index.json` nav config to support `tier` field on menu items (lock icon for unpaid)
- [ ] Commit: `git commit -am "docs: custom analytics module framework and template"`

---

## Phase 10 — Backtesting V2 (Strategy Simulation)

> ⛔ **SUPERSEDED — DO NOT IMPLEMENT.**
>
> Replaced in full by
> **`docs/superpowers/specs/2026-08-11-portfolio-backtest-design.md`**, which covers
> everything below (position sizing, rebalancing, transaction costs, benchmark comparison,
> equity curve) plus six optimizers, walk-forward re-optimization, staggered asset
> inception, dollar-cost averaging, seven-sins diagnostics, saved portfolios and usage
> metering.
>
> Two specific instructions from this phase are **wrong** under the new design and must not
> be followed:
> - Do **not** bolt `strategy_type` / `position_sizing` fields onto a job model — the new
>   design uses first-class `Portfolio` + `PortfolioHolding` entities
> - Do **not** treat Phase 5 as a prerequisite — the portfolio backtester has no dependency
>   on signal backtesting or on the factor engine
>
> The tasks below are retained for historical context only.

**Produces:** Full portfolio construction in `backtester` app: position sizing, rebalancing, transaction costs, benchmark comparison, full equity curve.

**Spec reference:** §8.7 (V2 section)

**Prerequisite:** Phase 5 V1 is stable and validated against real data.

### 10.A: Notebook prototype

**File:** `backend/class_files/backtester_strategy.ipynb`

- [ ] Prototype portfolio construction: equal-weight positions, quarterly rebalancing, 10bps transaction cost, benchmark (buy-and-hold SPY)
- [ ] Compute full equity curve, Sharpe ratio, max drawdown, annual turnover

### 10.B: Extend `backtester` app

- [ ] Add `strategy_type`, `position_sizing`, `transaction_cost_bps`, `benchmark` fields to `BacktestJob`
- [ ] Add `backend/backtester/engine/strategy.py` with portfolio construction logic
- [ ] Extend `run_signal_backtest` Celery task to handle strategy mode
- [ ] Update frontend results page with equity curve chart and full statistics table
- [ ] Commit: `git commit -am "feat(backtester): strategy simulation V2"`

---

## Stripe Monetisation Scaffolding (Cross-Phase)

The following items ship across the phases above as prerequisites — **not a separate phase**:

- **Phase 3**: `subscription_tier` field on `UserProfile` (already included)
- **All API views**: use `permission_classes = [IsAuthenticated]` now; swapping to `HasActiveSubscription` for premium endpoints requires changing one line per view
- **Phase 9**: module config declares `MODULE_TIER`; nav renders lock icons

Actual Stripe integration (Checkout, webhooks, subscription management) is a future phase after the core analytics are validated.

---

## Verification Checklist (All Phases)

- [ ] `cd backend && python manage.py check` — no errors
- [ ] `cd backend && python manage.py migrate` — no conflicts
- [ ] `cd fintank && npm run build` — no errors
- [ ] `cd backend && python manage.py test` — all tests pass
- [ ] `/stock-data/AAPL` renders header strip, financials tabs, valuation metrics
- [ ] News articles on stock detail page show for AAPL, MSFT, TSLA after Phase 2
- [ ] Watchlist: add AAPL, verify entry price stored, refresh shows % change
- [ ] Factor rankings page loads SP500 universe, sortable table renders
- [ ] Backtester: submit AAPL PE ratio signal, job progresses to complete, results render
- [ ] Market breadth indicator shows advancing/declining count on home page
- [ ] Screener: filter by `min_composite_score=7`, results link to stock detail pages
- [ ] ETF detail page `/etf/SPY` renders holdings and sector exposure
- [ ] Redis cache hit confirmed on second API call for factor scores
- [ ] `SUBSCRIBER` role user cannot access factor engine endpoints (after Stripe phase)
