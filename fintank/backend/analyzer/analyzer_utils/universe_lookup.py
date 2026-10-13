"""Resolve a symbol to the universe(s) whose parquet files contain it.

`long_profiles` carries no universe column, and `exchange_short_name` cannot
stand in for one -- NASDAQ-listed symbols are spread across sp500, nas, r2000
and rmicro. The only authoritative source is the constituent lists themselves,
so this module builds a reverse index over them and caches it.
"""
import gzip
import json
import logging

from django.core.cache import cache

from utils.StockCalculations import GetData

logger = logging.getLogger(__name__)

data_getter = GetData()

CACHE_KEY = "stock:universe_index:v1"
CACHE_TIMEOUT = 86400

# A build that lost some constituent lists is cached briefly once, so a
# transient S3 error heals in minutes rather than standing for a day. If the
# retry is still partial the list is probably gone for good, so it falls back
# to the full TTL instead of rebuilding every few minutes indefinitely.
PARTIAL_TIMEOUT = 300
PARTIAL_RETRY_KEY = "stock:universe_index:partial_retry:v1"

# A build that lost every list is not cached at all -- an empty index would
# 404 every symbol as "not in any known universe". A short marker stops each
# request from re-hitting S3 while it is down.
UNAVAILABLE_TIMEOUT = 60
UNAVAILABLE_KEY = "stock:universe_index:unavailable:v1"


class UniverseIndexUnavailable(Exception):
    """No constituent list could be read, so no symbol can be resolved."""

# Constituent-list key -> universe key used by the financial statement paths.
# The lists call it 'nasdaq'; the statement parquets call it 'nas'.
CONSTITUENT_TO_UNIVERSE = {
    'sp500': 'sp500',
    'nasdaq': 'nas',
    'r2000': 'r2000',
    'rmicro': 'rmicro',
    'tsx': 'tsx',
    'tsx_small_cap': 'tsx_small_cap',
    'msci_eafe': 'msci_eafe',
    'msci_sm': 'msci_sm',
}

# Order candidates are tried in. Broad, well-populated universes first so the
# statement lookup hits the most likely parquet before falling back.
UNIVERSE_PRIORITY = [
    'sp500', 'nas', 'r2000', 'rmicro',
    'tsx', 'tsx_small_cap', 'msci_eafe', 'msci_sm',
]


def build_symbol_universe_index(failures=None):
    """Map every constituent symbol to the universes containing it.

    Constituent keys that could not be read are appended to `failures`.
    """
    index = {}
    for constituent_key, universe in CONSTITUENT_TO_UNIVERSE.items():
        try:
            constituents = data_getter.get_index_constituents(constituent_key)
        except Exception as exc:
            # A missing or unreadable constituent file should not sink the
            # whole index -- the other universes are still usable.
            logger.warning("Universe index: could not read %s constituents: %r",
                           constituent_key, exc)
            if failures is not None:
                failures.append(constituent_key)
            continue

        for entry in constituents:
            symbol = entry.get('asset') if isinstance(entry, dict) else entry
            if not symbol:
                continue
            index.setdefault(str(symbol).upper(), []).append(universe)

    return index


def get_symbol_universe_index():
    compressed = cache.get(CACHE_KEY)
    if compressed:
        return json.loads(gzip.decompress(compressed))

    if cache.get(UNAVAILABLE_KEY):
        raise UniverseIndexUnavailable("Universe index is temporarily unavailable.")

    failures = []
    index = build_symbol_universe_index(failures)

    if failures and not index:
        cache.set(UNAVAILABLE_KEY, 1, timeout=UNAVAILABLE_TIMEOUT)
        raise UniverseIndexUnavailable(
            f"Universe index is temporarily unavailable: could not read {failures}."
        )

    if not failures:
        timeout = CACHE_TIMEOUT
        cache.delete(PARTIAL_RETRY_KEY)
    elif cache.get(PARTIAL_RETRY_KEY):
        timeout = CACHE_TIMEOUT
    else:
        timeout = PARTIAL_TIMEOUT
        cache.set(PARTIAL_RETRY_KEY, 1, timeout=CACHE_TIMEOUT)

    cache.set(CACHE_KEY, gzip.compress(json.dumps(index).encode('utf-8')), timeout=timeout)
    return index


def resolve_universes(symbol):
    """Return candidate universes for `symbol`, most likely first.

    A list rather than a single value: symbols legitimately belong to several
    universes (AAPL is in both sp500 and nasdaq), and index membership does not
    guarantee the matching statement parquet actually carries the symbol. The
    caller walks the candidates until one yields data.
    """
    index = get_symbol_universe_index()
    universes = set(index.get(str(symbol).upper(), []))
    return [u for u in UNIVERSE_PRIORITY if u in universes]
