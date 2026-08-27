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


def _market_date():
    """The trading day the caches are keyed to.

    Both cache layers carry this, and that is load-bearing. A flat 24h TTL with
    no date component lets an entry filled shortly before the daily pipeline's
    parquet write stay stale for a further 24h; worse, the two layers are not
    synchronised to a shared epoch, so a warm payload can keep serving
    yesterday's window after the OHLCV layer has already refreshed. A new
    trading day yields new keys at every layer at once.

    Mirrors the fallback at views.py:513.
    """
    try:
        return str(get_effective_market_date())
    except Exception:
        return str(date.today())


def _adjust(df):
    """Sort, deduplicate, coerce and back-adjust a raw price frame.

    Split out from _load_adjusted_frame so tests can feed a frame through the
    same transform the loader applies.
    """
    if df is None or len(df) == 0:
        raise KeyError('empty price frame')

    df = df.dropna(subset=['date']).copy()
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')

    # load_stock_prices neither sorts nor deduplicates -- it just reset_index()es
    # a DatetimeIndex. Every rolling and ewm call below is positional, not
    # date-aware, so an out-of-order or repeated row corrupts every indicator
    # without raising anything. prices.py:_series_from_frame defends the same
    # loader the same way, on one column rather than the whole frame.
    df = (df.sort_values('date')
            .drop_duplicates(subset='date', keep='last')
            .reset_index(drop=True))

    for column in ('open', 'high', 'low', 'close', 'adjClose', 'volume'):
        df[column] = pd.to_numeric(df[column], errors='coerce')

    if int(df['close'].notna().sum()) == 0:
        raise KeyError('no usable close prices')

    # Full back-adjustment. Computing on raw close puts a split-sized
    # discontinuity into every recursive indicator, which then decays forward
    # for weeks; computing on adjClose alone fixes the indicators but leaves
    # overlays floating off raw candle bodies. Adjusting all four columns makes
    # them consistent by construction, which is what mainstream platforms do.
    # volume stays raw: ADL reads it as a magnitude and the average_volume
    # reference line should reflect actual shares traded.
    ratio = df['adjClose'] / df['close']
    for column in ('open', 'high', 'low'):
        df[column] = df[column] * ratio
    df['close'] = df['adjClose']

    return df[['date', 'open', 'high', 'low', 'close', 'volume']]


def _load_adjusted_frame(symbol):
    """The single I/O seam. One column-projected parquet read from S3.

    pyarrow + s3fs surfaces a missing key inconsistently in this stack --
    prices.py:113 catches all three around this exact call -- so everything is
    re-raised as one KeyError carrying the symbol, which is the exception the
    view's 404 branch keys on.
    """
    try:
        df = data_getter.load_stock_prices(symbol, columns=PRICE_COLUMNS)
    except (FileNotFoundError, OSError, KeyError):
        raise KeyError(f"No price history for '{symbol}'")

    try:
        return _adjust(df)
    except KeyError:
        raise KeyError(f"No price history for '{symbol}'")


def _ohlcv_cached(symbol):
    """The shared layer: every indicator request for this symbol reuses it, so
    adding an indicator or changing a period never re-reads S3."""
    key = f'stock:ohlcv:{symbol}:{_market_date()}:v1'
    blob = cache.get(key)
    if blob:
        try:
            columns = _load_cached_json(blob)
            frame = pd.DataFrame(columns)
            for column in ('open', 'high', 'low', 'close', 'volume'):
                frame[column] = pd.to_numeric(frame[column], errors='coerce')
            return frame
        except Exception:
            # A corrupt or stale-format entry is not worth failing a render over.
            cache.delete(key)

    frame = _load_adjusted_frame(symbol)
    # .tolist() converts numpy scalars to Python natives; json.dumps cannot
    # serialise np.float64.
    payload = json_safe({column: frame[column].tolist() for column in frame.columns})
    cache.set(key, gzip.compress(json.dumps(payload).encode('utf-8')), CACHE_TTL)
    return frame


def get_technicals(symbol, raw_spec=None):
    """Candles, volume and indicator series for one symbol.

    Raises ValueError for a malformed spec and KeyError for a symbol with no
    usable price history; the view maps those to 400 and 404.
    """
    parsed = parse_spec(raw_spec)
    symbol = symbol.upper()
    spec_hash = canonical_key(parsed) if parsed else 'none'

    payload_key = f'stock:technicals:{symbol}:{_market_date()}:{spec_hash}:v1'
    blob = cache.get(payload_key)
    if blob:
        return _load_cached_json(blob)

    frame = _ohlcv_cached(symbol)
    rows = len(frame)
    volume_usable = bool(frame['volume'].notna().any())

    warnings = []
    computed = {}
    for name, params in parsed:
        spec = ti.INDICATORS[name]
        token = token_for(name, params)

        # This check is the only thing enforcing "insufficient history degrades,
        # never 500s". ewm defaults to min_periods=0 and emits numbers from row
        # zero, so six of the eleven indicators would otherwise return garbage
        # computed from two data points rather than being suppressed.
        needed = spec.min_rows(params)
        if rows < needed:
            warnings.append(
                f'{token} skipped - needs {needed} rows, symbol has {rows}')
            continue
        if name == 'adl' and not volume_usable:
            warnings.append(f'{token} skipped - no volume data')
            continue

        # Computed over the FULL history; trimmed below. The reverse order
        # would leave sma:200 with 199 leading nulls inside a 250-row window.
        computed[token] = (spec, spec.fn(frame, *params))

    tail = frame.tail(WINDOW)
    dates = tail['date'].tolist()

    indicators = {}
    for token, (spec, result) in computed.items():
        entry = {'kind': spec.kind}
        for plot in spec.plots:
            entry[plot] = result[plot].tail(WINDOW).tolist()
        if spec.bands:
            entry['bands'] = list(spec.bands)
        indicators[token] = entry

    opens, highs = tail['open'].tolist(), tail['high'].tolist()
    lows, closes = tail['low'].tolist(), tail['close'].tolist()
    volumes = tail['volume'].tolist()

    payload = json_safe({
        'symbol': symbol,
        'dates': dates,
        'candle': [{'x': d, 'y': [o, h, l, c]}
                   for d, o, h, l, c in zip(dates, opens, highs, lows, closes)],
        'volume': [{'x': d, 'y': v} for d, v in zip(dates, volumes)],
        # Mean of the *trimmed* window, so the reference line matches the bars
        # drawn beneath it.
        'average_volume': float(tail['volume'].mean()),
        'indicators': indicators,
        'warnings': warnings,
    })

    cache.set(payload_key, gzip.compress(json.dumps(payload).encode('utf-8')), CACHE_TTL)
    return payload
