"""Factor decile performance for /factor-performance.

Replaces backend/utils/Rankings.py, which read a pickle per index from the
bucket root and carried ~700 lines of four near-identical frequency methods.
Source is now stock_data/factor_metrics/{universe}_metrics_returns.parquet,
written by create_factor_metrics_dataframes() in stock_data_getter_v2.ipynb.

Three bugs from that version are fixed here:

  1. Every frequency method read `beta = self.get_pcf_metrics(...)`, so the
     page's beta chart rendered price-to-cash-flow data under a beta label.
  2. get_ranked_quintiles sliced a bucket before its increment logic decided
     to jump to the end, so a remainder tail (e.g. rows 200-204 of 205 at a
     20-row bucket size) landed in no bucket and vanished from both the
     returns and the holdings tables. It also divided by zero when a sparse
     column left fewer rows than buckets.
  3. Bucket return was prod(1 + w*r) - 1 -- the operation for compounding one
     asset across time, not for aggregating many assets within one period. It
     introduces cross-terms, largest exactly where decile buckets live: the
     tails of the sorted metric. It is a weighted sum here.

Interest coverage is deliberately absent: FMP reports it as 0 for a large
share of the universe including AAPL.

Units: the frequency columns are PERCENT, so bucket values divide by 100 and
the pack's `values` are then presented as round(v * 100, 2), unchanged from
the legacy contract the frontend reads.
"""
import gzip
import json

import numpy as np
import pandas as pd
from django.core.cache import cache
from django.utils import timezone

from utils.StockCalculations import GetData

data_getter = GetData()

CACHE_TTL = 86400  # 24h, matching the rest of the S3-backed endpoints

FACTOR_UNIVERSES = ('sp500', 'nas', 'tsx', 'tsx_small_cap', 'r2000',
                    'rmicro', 'msci_eafe', 'msci_sm')

FACTOR_FREQUENCIES = ("1M", "3M", "6M", "ytd")

# Response key (what the page reads) → parquet column. 'sectors' is grouped
# rather than bucketed and is handled separately.
FACTOR_COLUMNS = {
    'pe': 'pe',
    'ps': 'psales',
    'pb': 'pb',
    'pcf': 'pcf',
    'div': 'div_yield',
    'fcf': 'fcf',
    'roe': 'roe',
    'de': 'debt_equity',
    'cfd': 'cfd',
    'beta': 'beta',
    'stdevone': '1MSTD',
    'stdevthree': '3MSTD',
    'stdevsix': '6MSTD',
    'stdevytd': 'YTDSTD',
    'sectors': 'sector',
}

LARGE_UNIVERSE_ROWS = 100  # above this, deciles; at or below, quintiles


def _bucket_count(row_count):
    return 10 if row_count > LARGE_UNIVERSE_ROWS else 5


def _native(value):
    """numpy scalar → Python scalar. json.dumps (used by the cache write) has
    no encoder for np.float64, and the sector pack's metric is a string."""
    if isinstance(value, str):
        return value
    return None if pd.isna(value) else float(value)


def _holdings(frame, frequency, metric_column):
    """[{symbol, return, metric}] — one pass over the frame; the legacy
    version built this with a per-row .iloc lookup."""
    records = (frame[['symbol', frequency, metric_column]]
               .rename(columns={frequency: 'return', metric_column: 'metric'})
               .to_dict('records'))
    return [{'symbol': str(r['symbol']),
             'return': _native(r['return']),
             'metric': _native(r['metric'])} for r in records]


def _equal_weighted_return(returns):
    """Weighted sum of an equal-weighted bucket. Returns are percent."""
    if len(returns) == 0:
        return 0.0
    return float((returns / 100).sum() / len(returns))


def _empty_pack():
    return {'buckets': [], 'values': [], 'bucket_holdings': {}, 'bucket_keys': []}


def _metric_pack(df, frequency, metric_column, count):
    """Rank on the metric descending, split into even buckets, and give each
    bucket its equal-weighted return. `count` is decided once per universe
    (from the full frame's row count), not from this column's dropna count,
    so every chart on a page shares the same Q1..Qn scale."""
    ranked = (df[['symbol', frequency, metric_column]]
              .dropna()
              .sort_values(by=metric_column, ascending=False)
              .reset_index(drop=True))

    if len(ranked) < count:
        return _empty_pack()

    labels, values, holdings = [], [], {}
    for i, idx in enumerate(np.array_split(np.arange(len(ranked)), count), start=1):
        bucket = ranked.iloc[idx]
        label = f'Q{i}'
        labels.append(label)
        values.append(round(_equal_weighted_return(bucket[frequency]) * 100, 2))
        holdings[label] = _holdings(bucket, frequency, metric_column)

    return {'buckets': labels, 'values': values,
            'bucket_holdings': holdings, 'bucket_keys': labels}


def _sector_pack(df, frequency):
    """One bucket per sector, equal-weighted within the sector."""
    ranked = df[['symbol', frequency, 'sector']].dropna()
    if ranked.empty:
        return _empty_pack()

    labels, values, holdings = [], [], {}
    for sector, group in ranked.groupby('sector', sort=True):
        labels.append(sector)
        values.append(round(_equal_weighted_return(group[frequency]) * 100, 2))
        holdings[sector] = _holdings(group, frequency, 'sector')

    return {'buckets': labels, 'values': values,
            'bucket_holdings': holdings, 'bucket_keys': labels}


def get_factor_ranks(frequency, universe):
    """Decile packs for every factor at one frequency, for one index list.

    Nulls are dropped per metric, at point of use -- a stock with no P/E still
    appears in the ROE chart. The legacy producer dropped any row with a null
    in any of ~20 columns before the data ever got here.
    """
    if universe not in FACTOR_UNIVERSES:
        raise KeyError(f"Unknown universe '{universe}'.")
    if frequency not in FACTOR_FREQUENCIES:
        raise KeyError(f"Unknown frequency '{frequency}'.")

    cache_key = f'factor:ranks:{universe}:{frequency}:v1'
    compressed = cache.get(cache_key)
    if compressed:
        return json.loads(gzip.decompress(compressed))

    df = data_getter.load_factor_metrics(universe)
    if df.empty:
        raise KeyError(f"No factor metrics for '{universe}'.")

    count = _bucket_count(len(df))

    packs = {}
    for key, column in FACTOR_COLUMNS.items():
        if key == 'sectors':
            packs[key] = _sector_pack(df, frequency)
        else:
            packs[key] = _metric_pack(df, frequency, column, count)

    payload = {
        'universe': universe,
        'frequency': frequency,
        'as_of': str(df['as_of'].max()) if 'as_of' in df.columns else None,
        'constituent_count': int(len(df)),
        'data': packs,
        'last_updated': timezone.now().isoformat(),
    }
    cache.set(cache_key, gzip.compress(json.dumps(payload).encode()), CACHE_TTL)
    return payload
