"""Orchestration behind GET /api/technicals/<symbol>/.

Owns everything technical_indicators.py refuses to: spec parsing and
validation, the S3 read, the back-adjustment, both cache layers, the
compute-then-trim rule, and payload assembly.

This replaces backend/utils/Technicals.py, which issued one billed FMP call per
indicator per symbol -- roughly 85 calls for a single render of this page. The
per-symbol daily parquet already carries full OHLCV, so the same page costs one
partial parquet read per symbol and no FMP calls at all.
"""
import gzip
import hashlib
import json
from datetime import date

import pandas as pd
from django.core.cache import cache

from utils.StockCalculations import GetData
from .CorePerformanceTools import json_safe, _load_cached_json
from .market_hours import get_effective_market_date
from . import technical_indicators as ti

data_getter = GetData()

# 'date' must be present: it is the parquet's index column, and omitting it
# makes to_pandas() return a RangeIndex with no 'date' column at all.
PRICE_COLUMNS = ['date', 'open', 'high', 'low', 'close', 'adjClose', 'volume']

WINDOW = 250            # trailing trading days returned, ~1 year
MAX_INDICATORS = 12
MIN_PERIOD = 2
MAX_PERIOD = 500
CACHE_TTL = 86400       # 24h; the date-keying below is what keeps it honest


def token_for(name, params):
    """('macd', (12, 26, 9)) -> 'macd:12:26:9'; ('adl', ()) -> 'adl'."""
    return ':'.join([name, *[str(p) for p in params]])


def parse_spec(raw):
    """'rsi:14,macd:12:26:9,adl' -> [('rsi', (14,)), ('macd', (12, 26, 9)), ('adl', ())]

    Raises ValueError naming the offending token; the view maps that to a 400.
    A missing parameter (None) is valid and yields [] -- the candle-only path a
    freshly added ticker needs before anything is toggled. A *present but
    malformed* parameter is still an error.

    Deduplication happens after normalisation and before the cap, so
    'sma:50,sma:50' counts once.
    """
    if raw is None:
        return []

    tokens = [token.strip() for token in raw.split(',') if token.strip()]
    if not tokens:
        raise ValueError(
            'indicators is empty - valid names: ' + ', '.join(sorted(ti.INDICATORS)))

    parsed = []
    for token in tokens:
        parts = token.split(':')
        name = parts[0].lower()
        spec = ti.INDICATORS.get(name)
        if spec is None:
            raise ValueError(f"unknown indicator '{name}'")

        raw_params = parts[1:]
        if len(raw_params) != spec.arity:
            raise ValueError(
                f"'{token}' takes {spec.arity} parameter(s), got {len(raw_params)}")

        params = []
        for value in raw_params:
            try:
                number = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"'{token}': period '{value}' is not an integer")
            if not MIN_PERIOD <= number <= MAX_PERIOD:
                raise ValueError(
                    f"'{token}': period {number} is outside {MIN_PERIOD}..{MAX_PERIOD}")
            params.append(number)

        if name == 'macd' and params[0] >= params[1]:
            raise ValueError(f"'{token}': fast period must be below the slow period")

        entry = (name, tuple(params))
        if entry not in parsed:
            parsed.append(entry)

    if len(parsed) > MAX_INDICATORS:
        raise ValueError(f'at most {MAX_INDICATORS} indicators per request')

    return parsed


def canonical_key(parsed):
    """Order-independent digest of a parsed spec.

    'rsi:14,sma:50' and 'sma:50,rsi:14' must hit the same cache entry, so the
    tokens are sorted before hashing. Sixty-four bits is ample for a small,
    non-adversarial parameter space.
    """
    canonical = ','.join(sorted(token_for(name, params) for name, params in parsed))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]
