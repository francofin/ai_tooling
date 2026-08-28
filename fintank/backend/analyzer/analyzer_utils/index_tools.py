"""Index detail page data.

Serves /indexes/<slug> from the v2 pipeline output instead of the pickle packs
the old project used. Where that version stored one precomputed pickle per
(index, peer) pair in S3 -- and needed five endpoints to load ten of them -- the
metric parquets already carry every rolling window, so a pair is an inner join
of two files and a subtraction. One endpoint replaces the five packs.

Data sources, all written by stock_data_getter_v2.ipynb:
  index_data/index_prices_v2/{daily,monthly}/{key}_prices.parquet
  index_data/contr_to_var/{universe}_contr_to_var.parquet
  index_data/constituents/{key}_constituents.json

Four slugs map to a true index parquet. The other three are indexes we hold
constituents for but no index price file (Russell Microcap, S&P/TSX SmallCap,
MSCI EAFE), so they chart their proxy ETF, which the pipeline writes with the
identical 51-column schema. `msci_sm` is deliberately absent: WSML only lists
from 2025-04-03 and is missing the 3-year columns.
"""
from datetime import datetime
import gzip
import json

import numpy as np
import pandas as pd
import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from utils.IndexFileMappers import IndexFileMappers
from utils.StockCalculations import GetData
from .market_hours import is_market_open_now

data_getter = GetData()
fmp_api = settings.FMP_API
index_mappers = IndexFileMappers().getIndexFileMapper()

CACHE_TTL = 86400  # 24h, matching the rest of the S3-backed endpoints

# slug -> where its price series lives and which constituent list belongs to it.
#   price_source 'index' -> index_data/index_prices_v2/{price_key}
#   price_source 'etf'   -> stock_data/stock_prices/daily/{price_key}
# constituent_key indexes GetData.constituent_maps; risk_key names the
# contr_to_var file. They disagree for NASDAQ ('nasdaq' vs 'nas'), which is why
# both are spelled out rather than derived.
INDEX_PAGES = {
    'sp500': {
        'title': 'S&P 500 Index',
        'price_key': 'sp500', 'price_source': 'index',
        'constituent_key': 'sp500', 'risk_key': 'sp500',
        'peers': ['nas_comp', 'dji', 'russell_2000', 'sp_mid_cap', 'sp_equal',
                  'tsx', 'ftse_100', 'nikkei_225', 'hang_seng', 'euro_stoxx_50', 'vix'],
    },
    'nasdaq': {
        'title': 'NASDAQ Composite Index',
        'price_key': 'nas_comp', 'price_source': 'index',
        'constituent_key': 'nasdaq', 'risk_key': 'nas',
        'peers': ['sp500', 'dji', 'nas_100', 'nas_biotech', 'dj_semiconductors',
                  'russell_2000', 'tsx', 'ftse_100', 'nikkei_225', 'vix'],
    },
    'r2000': {
        'title': 'Russell 2000 Index',
        'price_key': 'russell_2000', 'price_source': 'index',
        'constituent_key': 'r2000', 'risk_key': 'r2000',
        'peers': ['sp500', 'russell_1000', 'russell_3000', 'russell_mid_tr',
                  'sp_mid_cap', 'nas_comp', 'tsx_venture', 'ftse_250',
                  'vix_small_cap', 'vix'],
    },
    'tsx': {
        'title': 'S&P/TSX Composite Index',
        'price_key': 'tsx', 'price_source': 'index',
        'constituent_key': 'tsx', 'risk_key': 'tsx',
        'peers': ['sp500', 'tsx_60', 'tsx_banks', 'tsx_mining', 'tsx_venture',
                  'nas_comp', 'ftse_100', 'hang_seng', 'euro_stoxx_50', 'vix'],
    },
    'rmicro': {
        'title': 'Russell Microcap Index',
        'price_key': 'IWC', 'price_source': 'etf',
        'constituent_key': 'rmicro', 'risk_key': 'rmicro',
        'peers': ['russell_2000', 'sp500', 'russell_3000', 'sp_mid_cap',
                  'nas_comp', 'tsx_venture', 'vix_small_cap', 'vix'],
    },
    'tsx_small_cap': {
        'title': 'S&P/TSX SmallCap Index',
        'price_key': 'XCS.TO', 'price_source': 'etf',
        'constituent_key': 'tsx_small_cap', 'risk_key': 'tsx_small_cap',
        'peers': ['tsx', 'tsx_60', 'tsx_venture', 'russell_2000', 'sp500',
                  'sp_mid_cap', 'vix_small_cap', 'vix'],
    },
    'msci_eafe': {
        'title': 'MSCI EAFE Index',
        'price_key': 'IEFA', 'price_source': 'etf',
        'constituent_key': 'msci_eafe', 'risk_key': 'msci_eafe',
        'peers': ['msci_world', 'msci_eafe_growth', 'msci_eafe_value', 'ftse_100',
                  'nikkei_225', 'hang_seng', 'euro_stoxx_50', 'sp500', 'vix'],
    },
}

# Metric key -> parquet column. The keys are the contract with the frontend and
# never change; the old hooks switched on display strings like "60 Day Return
# Spread", which is how the 60-day branch ended up serving the 30-day series.
MA_COLUMNS = {
    'ma_10': '10_day_ma', 'ma_20': '20_day_ma', 'ma_50': '50_day_ma',
    'ma_120': '120_day_ma', 'ma_200': '200_day_ma',
}
RETURN_COLUMNS = {
    'ret_30': '30_day_returns', 'ret_60': '60_day_returns', 'ret_90': '90_day_returns',
    'ret_120': '120_day_returns', 'ret_1y': '1_yr_returns', 'ret_3y': '3_yr_returns',
}
VOLATILITY_COLUMNS = {
    'vol_30': '30_day_volatility', 'vol_60': '60_day_volatility',
    'vol_90': '90_day_volatility', 'vol_120': '120_day_volatility',
    'vol_1y': '1_yr_volatility', 'vol_3y': '3_yr_volatility',
}
RETURN_TO_RISK_COLUMNS = {
    'rr_30': '30_day_return_to_risk', 'rr_60': '60_day_return_to_risk',
    'rr_90': '90_day_return_to_risk', 'rr_120': '120_day_return_to_risk',
    'rr_1y': '1_yr_return_to_risk', 'rr_3y': '3_yr_return_to_risk',
}
# Rolling beta is the one metric the parquets do not carry, so it is computed
# from the two daily return columns. 252 trading days stands in for a year.
BETA_WINDOWS = {'beta_30': 30, 'beta_60': 60, 'beta_90': 90, 'beta_120': 120, 'beta_1y': 252}

PRICE_COLUMNS = ['adjClose', 'volume']
TRADING_DAYS_PER_YEAR = 252
DEFAULT_YEARS = 5
MAX_YEARS = 30
DECIMALS = 6


def _comparison_columns():
    """Columns a comparison needs from each side. Pushed into the parquet read."""
    return (['date', 'returns', 'adjClose']
            + list(MA_COLUMNS.values())
            + list(RETURN_COLUMNS.values())
            + list(VOLATILITY_COLUMNS.values())
            + list(RETURN_TO_RISK_COLUMNS.values()))


def _series_to_json(column):
    """Numeric column -> JSON-safe list, NaN -> None.

    Same reasoning as CorePerformanceTools._series_to_json: pandas coerces None
    back to NaN on a float column, and DRF rejects NaN at render time.
    """
    rounded = column.astype(float).round(DECIMALS)
    return [None if v != v else v for v in rounded.astype(object).tolist()]


def _load_price_frame(price_key, price_source, frequency='daily', columns=None):
    """Read one side of a chart, from either the index or the per-stock tree.

    Both trees carry the same schema, so everything downstream is agnostic about
    which one a slug came from.
    """
    if price_source == 'etf':
        if frequency != 'daily':
            return data_getter.load_stock_prices_monthly(price_key)
        return data_getter.load_stock_prices(price_key)
    return data_getter.load_index_parquet(price_key, frequency=frequency, columns=columns)


def _available(df, mapping):
    """Metric key -> column, dropped where the parquet lacks the column.

    Shorter-history series (a recently listed proxy ETF) are missing the longer
    windows outright, so the payload advertises what exists rather than shipping
    a column of nulls.
    """
    return {key: col for key, col in mapping.items() if col in df.columns}


def _trim_to_years(df, years):
    """Keep the last `years` of rows, by date rather than row count.

    Trimming happens after the rolling maths so a window that reaches back
    before the cutoff is still correct at the first visible date.
    """
    if df.empty:
        return df
    cutoff = pd.to_datetime(df['date'].iloc[-1]) - pd.DateOffset(years=years)
    return df[pd.to_datetime(df['date']) >= cutoff].reset_index(drop=True)


# Trailing windows for the header ribbon, in trading days.
PERFORMANCE_PERIODS = {'1D': 1, '5D': 5, '1M': 21, '3M': 63, '6M': 126, '1Y': 252}


def _period_performance(dates, closes):
    """Percent change over each trailing window, plus year to date.

    Derived from the price series the page already loads rather than fetched:
    the old ribbon called FMP from the browser with NEXT_PUBLIC_FMP_API, which
    put the key in the client bundle (and the var was never set, so the ribbon
    rendered nothing). These are end-of-day figures -- the header states the
    as-of date so a stale parquet is visible rather than implied to be live.
    """
    if len(closes) < 2:
        return {}

    latest = closes[-1]
    performance = {}
    for label, window in PERFORMANCE_PERIODS.items():
        if len(closes) > window:
            previous = closes[-1 - window]
            if previous:
                performance[label] = round((latest / previous - 1) * 100, DECIMALS)

    # YTD needs the last close of the previous calendar year, not a fixed
    # offset, so it stays right regardless of where in the year we are.
    current_year = dates[-1][:4]
    prior_year_closes = [c for d, c in zip(dates, closes) if d[:4] < current_year]
    base = prior_year_closes[-1] if prior_year_closes else closes[0]
    if base:
        performance['YTD'] = round((latest / base - 1) * 100, DECIMALS)

    return performance


def get_index_page_config(slug):
    """Page config for a slug, or raise KeyError so the view can 404."""
    try:
        return INDEX_PAGES[slug]
    except KeyError:
        raise KeyError(f"Unknown index slug '{slug}'.")


def get_index_peers(slug):
    """Curated peer list, filtered to keys that actually have a parquet.

    The old page hardcoded peers per index in five arrays, and half of them
    (Euronext 100, IBEX 35, Sensex...) had no data behind them. Resolving
    against IndexFileMappers means a dead key drops out here instead of
    rendering an empty chart.
    """
    config = get_index_page_config(slug)
    peers = []
    for key in config['peers']:
        mapper = index_mappers.get(key)
        if not mapper:
            continue
        peers.append({
            'key': key,
            'label': mapper['full_name'],
            'ticker': mapper.get('ticker'),
        })
    return peers


def get_index_series(slug, frequency='daily', years=DEFAULT_YEARS):
    """Price series plus moving averages for the headline chart."""
    config = get_index_page_config(slug)
    if frequency not in ('daily', 'monthly'):
        raise ValueError(f"Unknown frequency '{frequency}'.")
    years = max(1, min(int(years), MAX_YEARS))

    cache_key = f"index:series:{slug}:{frequency}:{years}:v1"
    compressed = cache.get(cache_key)
    if compressed:
        return json.loads(gzip.decompress(compressed))

    wanted = ['date'] + PRICE_COLUMNS + list(MA_COLUMNS.values())
    df = _load_price_frame(
        config['price_key'], config['price_source'], frequency=frequency, columns=wanted,
    )
    # Ribbon first: a 1-year change needs rows the requested window may not span.
    performance = _period_performance(df['date'].tolist(), df['adjClose'].tolist())
    df = _trim_to_years(df, years)

    series_cols = [c for c in PRICE_COLUMNS if c in df.columns]
    series = {col: _series_to_json(df[col]) for col in series_cols}
    for metric_key, column in _available(df, MA_COLUMNS).items():
        series[metric_key] = _series_to_json(df[column])

    payload = {
        'slug': slug,
        'title': config['title'],
        'price_key': config['price_key'],
        'price_source': config['price_source'],
        'universe': config['constituent_key'],
        'frequency': frequency,
        'years': years,
        'dates': df['date'].tolist(),
        'series': series,
        'performance': performance,
        'as_of': df['date'].iloc[-1] if not df.empty else None,
        'peers': get_index_peers(slug),
        'last_updated': timezone.now().isoformat(),
    }
    cache.set(cache_key, gzip.compress(json.dumps(payload).encode('utf-8')), timeout=CACHE_TTL)
    return payload


def _rolling_beta(base_returns, peer_returns, window):
    """Beta of the page's index against the comparison index.

    cov(base, peer) / var(peer) over a rolling window -- the peer is the market
    proxy, which is the direction the page's copy describes ("measured relative
    to the selected comparison Index"). Windows shorter than the requested span
    return NaN, which serialises to null.
    """
    covariance = base_returns.rolling(window).cov(peer_returns)
    variance = peer_returns.rolling(window).var()
    beta = covariance / variance.replace(0, np.nan)
    return beta.replace([np.inf, -np.inf], np.nan)


def get_index_comparison(slug, peer_key, years=DEFAULT_YEARS):
    """One index against one peer: MA levels, three spreads, and rolling beta.

    Replaces getcomparisondatapackone..five. Spreads are index minus peer, as
    the page copy states.
    """
    config = get_index_page_config(slug)
    if peer_key not in index_mappers:
        raise KeyError(f"Unknown comparison index '{peer_key}'.")
    years = max(1, min(int(years), MAX_YEARS))

    cache_key = f"index:comparison:{slug}:{peer_key}:{years}:v1"
    compressed = cache.get(cache_key)
    if compressed:
        return json.loads(gzip.decompress(compressed))

    columns = _comparison_columns()
    base = _load_price_frame(config['price_key'], config['price_source'], columns=columns)
    peer = data_getter.load_index_parquet(peer_key, columns=columns)

    # Inner join: a Canadian index and a US one keep different holidays, so
    # aligning on date is what makes a spread meaningful.
    merged = base.merge(peer, on='date', how='inner', suffixes=('_base', '_peer'))
    if merged.empty:
        raise KeyError(f"No overlapping dates between '{slug}' and '{peer_key}'.")

    metrics = {'price': {}, 'moving_average': {}, 'return_spread': {},
               'volatility_spread': {}, 'return_to_risk_spread': {}, 'beta': {}}

    # Both raw levels, for the index-versus-VIX chart. Two indexes on different
    # scales share a date axis and get their own y-axis on the frontend.
    if 'adjClose_base' in merged.columns and 'adjClose_peer' in merged.columns:
        metrics['price']['adjClose'] = {
            'base': _series_to_json(merged['adjClose_base']),
            'peer': _series_to_json(merged['adjClose_peer']),
        }

    for metric_key, column in MA_COLUMNS.items():
        base_col, peer_col = f'{column}_base', f'{column}_peer'
        if base_col in merged.columns and peer_col in merged.columns:
            metrics['moving_average'][metric_key] = {
                'base': _series_to_json(merged[base_col]),
                'peer': _series_to_json(merged[peer_col]),
            }

    spread_families = (
        ('return_spread', RETURN_COLUMNS),
        ('volatility_spread', VOLATILITY_COLUMNS),
        ('return_to_risk_spread', RETURN_TO_RISK_COLUMNS),
    )
    for family, mapping in spread_families:
        for metric_key, column in mapping.items():
            base_col, peer_col = f'{column}_base', f'{column}_peer'
            if base_col in merged.columns and peer_col in merged.columns:
                metrics[family][metric_key] = _series_to_json(merged[base_col] - merged[peer_col])

    if 'returns_base' in merged.columns and 'returns_peer' in merged.columns:
        base_returns = merged['returns_base'].astype(float)
        peer_returns = merged['returns_peer'].astype(float)
        for metric_key, window in BETA_WINDOWS.items():
            if len(merged) >= window:
                metrics['beta'][metric_key] = _series_to_json(
                    _rolling_beta(base_returns, peer_returns, window)
                )

    # Rolling maths first, trim second: a 200-day MA or a 1-year beta at the
    # first visible date depends on rows before the window opens.
    trimmed = _trim_to_years(merged[['date']], years)
    keep = len(trimmed)
    for series_map in metrics.values():
        for metric_key, values in series_map.items():
            # Two-sided families (price, moving averages) carry {base, peer};
            # spreads and beta are a single list.
            if isinstance(values, dict):
                series_map[metric_key] = {side: side_values[-keep:]
                                          for side, side_values in values.items()}
            else:
                series_map[metric_key] = values[-keep:]

    peer_mapper = index_mappers[peer_key]
    payload = {
        'base': {
            'slug': slug,
            'title': config['title'],
            'price_key': config['price_key'],
            'price_source': config['price_source'],
        },
        'peer': {
            'key': peer_key,
            'title': peer_mapper['full_name'],
            'ticker': peer_mapper.get('ticker'),
        },
        'years': years,
        'dates': trimmed['date'].tolist(),
        'metrics': metrics,
        'last_updated': timezone.now().isoformat(),
    }
    cache.set(cache_key, gzip.compress(json.dumps(payload).encode('utf-8')), timeout=CACHE_TTL)
    return payload


RISK_VOL_FIELDS = ['symbol', 'weight', 'annualized_vol', 'contr_to_vol', 'pct_contr_to_vol']
RISK_RETURN_FIELDS = ['symbol', 'weight', 'period_return', 'contr_to_return']


def _risk_records(df, fields):
    records = []
    for _, row in df.iterrows():
        records.append({
            field: (None if (isinstance(row[field], float) and row[field] != row[field])
                    else row[field])
            for field in fields if field in df.columns
        })
    return json.loads(json.dumps(records, default=str))


def get_index_risk(slug, limit=20):
    """Top contributors to index volatility and to period return.

    Reads the contr_to_var snapshot, which had no backend consumer until now.
    The old page derived the same two bar charts from a `covar` blob bundled
    into comparison pack one.
    """
    config = get_index_page_config(slug)
    limit = max(1, min(int(limit), 100))

    cache_key = f"index:risk:{config['risk_key']}:{limit}:v1"
    compressed = cache.get(cache_key)
    if compressed:
        return json.loads(gzip.decompress(compressed))

    df = data_getter.load_contr_to_var(config['risk_key'])
    if df.empty:
        raise KeyError(f"No risk decomposition for '{slug}'.")

    by_vol = df.sort_values('pct_contr_to_vol', ascending=False).head(limit)
    by_return = df.sort_values('period_return', ascending=False).head(limit)

    payload = {
        'slug': slug,
        'universe': config['risk_key'],
        'as_of': str(df['as_of'].iloc[0]) if 'as_of' in df.columns else None,
        'window_days': int(df['window_days'].iloc[0]) if 'window_days' in df.columns else None,
        'constituent_count': int(len(df)),
        'contribution_to_volatility': _risk_records(by_vol, RISK_VOL_FIELDS),
        'period_return': _risk_records(by_return, RISK_RETURN_FIELDS),
        'last_updated': timezone.now().isoformat(),
    }
    cache.set(cache_key, gzip.compress(json.dumps(payload).encode('utf-8')), timeout=CACHE_TTL)
    return payload


QUOTE_FIELDS = ['symbol', 'name', 'pe', 'eps', 'changesPercentage', 'price', 'marketCap']
MOVERS_LIMIT = 20


def _batch_symbols(symbols, max_length=1800):
    """Comma-joined batches under the URL length FMP accepts.

    Mirrors GetData.get_heat_map_data's batching -- an index universe is up to
    ~1,700 symbols, which is far past what one query string holds.
    """
    batches, current, length = [], [], 0
    for symbol in symbols:
        projected = length + len(symbol) + (1 if current else 0)
        if projected > max_length:
            batches.append(','.join(current))
            current, length = [symbol], len(symbol)
        else:
            current.append(symbol)
            length = projected
    if current:
        batches.append(','.join(current))
    return batches


def get_index_quotes(slug):
    """Constituent quotes: movers panel and valuation table from one payload.

    v3 /quote/ rather than stable /batch-quote/: stable drops `pe` and `eps`
    (verified against the live key) and renames changesPercentage, and the
    valuation table is a PE ranking. One cached call per universe per day feeds
    both sections.
    """
    config = get_index_page_config(slug)

    cache_key = f"index:quotes:{config['constituent_key']}:v1"
    compressed = cache.get(cache_key)
    if compressed:
        return json.loads(gzip.decompress(compressed))

    constituents = data_getter.get_index_constituents(config['constituent_key'])
    symbols = [row['asset'] for row in constituents if row.get('asset')]
    if not symbols:
        raise KeyError(f"No constituents for '{slug}'.")

    quotes = []
    for batch in _batch_symbols(symbols):
        url = f"https://financialmodelingprep.com/api/v3/quote/{batch}?apikey={fmp_api}"
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            quotes.extend(response.json())
        except (requests.RequestException, ValueError) as error:
            # A dropped batch costs some constituents, not the whole section.
            print(f"index_quotes: batch failed for {slug}: {error}")
            continue

    if not quotes:
        raise KeyError(f"No quotes returned for '{slug}'.")

    records = [{field: quote.get(field) for field in QUOTE_FIELDS} for quote in quotes]
    by_change = sorted(
        (r for r in records if r['changesPercentage'] is not None),
        key=lambda r: r['changesPercentage'], reverse=True,
    )
    # Positive PE only. The old view filtered on `pe != None` and sorted
    # ascending, which put the deepest losses at the top of a "cheapest"
    # ranking -- CPX.TO at -5188 led the TSX table. A negative multiple means
    # no earnings, not a bargain.
    by_valuation = sorted(
        (r for r in records if r['pe'] is not None and r['pe'] > 0),
        key=lambda r: r['pe'],
    )

    payload = {
        'slug': slug,
        'universe': config['constituent_key'],
        'count': len(records),
        'top_performers': by_change[:MOVERS_LIMIT],
        'bottom_performers': by_change[-MOVERS_LIMIT:][::-1],
        'valuations': by_valuation,
        'market_open': is_market_open_now(),
        'last_updated': timezone.now().isoformat(),
    }
    cache.set(cache_key, gzip.compress(json.dumps(payload).encode('utf-8')), timeout=CACHE_TTL)
    return payload
