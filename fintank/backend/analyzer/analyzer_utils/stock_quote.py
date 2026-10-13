"""Single-symbol quote for the stock page, cached so viewers share one FMP call.

The quote is fetched when someone opens a stock page and the cached copy has
expired; everyone else reads Redis. While the market is open a quote lives for
15 minutes. Once it has closed nothing changes until the next open, so the
quote is held until then -- nights and weekends cost no calls at all.

stable /quote takes exactly one symbol. Given a comma-separated list it returns
`[]` with a 200 rather than an error, so it must never be used for batches
(that is /stable/batch-quote, which returns the same fields).
"""
from datetime import timedelta
import gzip
import json
import logging
import time

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .CorePerformanceTools import _load_cached_json, json_safe
from .market_hours import NY_TZ, NYSE

logger = logging.getLogger(__name__)

QUOTE_URL = "https://financialmodelingprep.com/stable/quote"

QUOTE_FIELDS = [
    'symbol', 'name', 'price', 'changePercentage', 'change', 'volume',
    'dayLow', 'dayHigh', 'yearLow', 'yearHigh', 'marketCap',
    'priceAvg50', 'priceAvg200', 'exchange', 'open', 'previousClose',
    'timestamp',
]

OPEN_TTL = 15 * 60
# The closing print can land a little after the bell, so the first half hour
# after close keeps the short TTL before the quote is held until the next open.
AFTER_CLOSE_GRACE = timedelta(minutes=30)
MIN_TTL = 60
# Cap on the closed-market TTL: a long weekend plus a holiday fits inside it.
MAX_CLOSED_TTL = 4 * 24 * 60 * 60

# A copy kept well past the fresh TTL, served when FMP errors or while another
# request is already fetching, so a blip shows a slightly old quote, not an error.
LAST_GOOD_TTL = 7 * 24 * 60 * 60
NOT_FOUND_TTL = 60 * 60
# While FMP is failing and there is no last good copy, at most one request per
# symbol per minute tries again -- client retries must not each cost a call.
FAILED_TTL = 60
LOCK_TTL = 30
LOCK_WAIT_SECONDS = 2.0
LOCK_POLL_SECONDS = 0.2


class QuoteUnavailable(Exception):
    """FMP could not supply a quote (bad key, rate limit, outage, bad body)."""


def _keys(symbol):
    return {
        'fresh': f"stock:quote:{symbol}:v1",
        'last': f"stock:quote:last:{symbol}:v1",
        'missing': f"stock:quote:missing:{symbol}:v1",
        'failed': f"stock:quote:failed:{symbol}:v1",
        'lock': f"stock:quote:lock:{symbol}:v1",
    }


def _quote_ttl(now=None):
    """Seconds the quote stays fresh: 15 min while trading, else until the open."""
    now = (now or timezone.now()).astimezone(NY_TZ)
    try:
        schedule = NYSE.schedule(start_date=(now - timedelta(days=7)).date(),
                                 end_date=(now + timedelta(days=10)).date())
    except Exception as exc:
        # Not a warning: without the calendar every quote refreshes every 15
        # minutes around the clock, roughly triple the intended FMP spend.
        logger.error("Quote TTL: NYSE calendar unavailable: %r", exc)
        return OPEN_TTL

    sessions = [(row.market_open.tz_convert(NY_TZ), row.market_close.tz_convert(NY_TZ))
                for row in schedule.itertuples()]
    for market_open, market_close in sessions:
        # Trading, or within the grace window after the bell.
        if market_open <= now < market_close + AFTER_CLOSE_GRACE:
            return OPEN_TTL

    upcoming = [market_open for market_open, _ in sessions if market_open > now]
    if not upcoming:
        return OPEN_TTL
    seconds = int((upcoming[0] - now).total_seconds())
    return max(MIN_TTL, min(seconds, MAX_CLOSED_TTL))


def _load(compressed):
    # Re-sanitised on read like the other cached payloads, so a non-finite
    # value that slipped into a stored copy cannot 500 the renderer.
    return _load_cached_json(compressed)


def _store(key, payload, timeout):
    cache.set(key, gzip.compress(json.dumps(payload).encode('utf-8')), timeout=timeout)


def fetch_quote(symbol):
    """One call to FMP. Raises KeyError for an unknown symbol."""
    try:
        response = requests.get(QUOTE_URL, params={'symbol': symbol, 'apikey': settings.FMP_API},
                                timeout=10)
    except requests.RequestException as exc:
        raise QuoteUnavailable(f"Quote request failed: {exc.__class__.__name__}") from exc

    # Errors arrive in several shapes: a 401 with {"Error Message": ...}, a 400
    # whose body is plain text, and documented 402/403/429s. None of their
    # bodies are echoed back -- they can quote the request, key included.
    if response.status_code != 200:
        raise QuoteUnavailable(f"Quote provider returned HTTP {response.status_code}.")
    try:
        body = response.json()
    except ValueError as exc:
        raise QuoteUnavailable("Quote provider returned a non-JSON body.") from exc
    if isinstance(body, dict):
        raise QuoteUnavailable("Quote provider returned an error.")
    if not isinstance(body, list):
        raise QuoteUnavailable("Quote provider returned an unexpected body.")
    if not body:
        raise KeyError(f"No quote for '{symbol}'.")

    row = body[0]
    return json_safe({field: row.get(field) for field in QUOTE_FIELDS})


def get_stock_quote(symbol):
    """Cached quote payload: {'quote': {...}, 'fetched_at': iso, 'stale_cache': bool}."""
    symbol = symbol.strip().upper()
    keys = _keys(symbol)

    compressed = cache.get(keys['fresh'])
    if compressed:
        return _load(compressed)
    if cache.get(keys['missing']):
        raise KeyError(f"No quote for '{symbol}'.")

    def last_good():
        last = cache.get(keys['last'])
        return dict(_load(last), stale_cache=True) if last else None

    if cache.get(keys['failed']):
        fallback = last_good()
        if fallback:
            return fallback
        raise QuoteUnavailable("Quote provider failed recently; retrying shortly.")

    # Only the request holding the lock calls FMP. The rest serve the last good
    # copy, or -- for a symbol with none -- wait briefly for the holder and then
    # give up rather than fetch: an unlocked fetch would let every waiter call
    # FMP whenever it is slow, which is exactly when it is most costly.
    locked = cache.add(keys['lock'], 1, timeout=LOCK_TTL)
    if not locked:
        fallback = last_good()
        if fallback:
            return fallback
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while time.monotonic() < deadline:
            time.sleep(LOCK_POLL_SECONDS)
            compressed = cache.get(keys['fresh'])
            if compressed:
                return _load(compressed)
        raise QuoteUnavailable("Quote is still being fetched; retry shortly.")

    try:
        quote = fetch_quote(symbol)
    except KeyError:
        # FMP answers an unknown symbol with `[]`, but so might a hiccup. A
        # symbol that has quoted before keeps its last copy rather than turning
        # into an hour-long 404 on the strength of one empty body.
        fallback = last_good()
        if fallback:
            logger.warning("Quote: %s returned no rows; serving last good copy", symbol)
            return fallback
        cache.set(keys['missing'], 1, timeout=NOT_FOUND_TTL)
        raise
    except QuoteUnavailable as exc:
        logger.warning("Quote: %s unavailable: %s", symbol, exc)
        cache.set(keys['failed'], 1, timeout=FAILED_TTL)
        fallback = last_good()
        if fallback:
            return fallback
        raise
    finally:
        cache.delete(keys['lock'])

    payload = {'quote': quote, 'fetched_at': timezone.now().isoformat(), 'stale_cache': False}
    _store(keys['fresh'], payload, _quote_ttl())
    _store(keys['last'], payload, LAST_GOOD_TTL)
    return payload
