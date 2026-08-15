"""Typeahead index over the staged universe (§12).

Follows analyzer_utils/universe_lookup.build_symbol_universe_index: read the
constituent JSONs, cache a compact structure, and never hit S3 on a keystroke.
The ETF list is included because a portfolio is stocks *and* ETFs.
"""
import gzip
import json

from django.core.cache import cache

from utils.StockCalculations import GetData

data_getter = GetData()

CACHE_KEY = 'backtest:symbol_index:v1'
CACHE_TIMEOUT = 86_400

STOCK_CONSTITUENT_KEYS = ('sp500', 'nasdaq', 'r2000', 'rmicro',
                          'tsx', 'tsx_small_cap', 'msci_eafe', 'msci_sm')


def _entry_symbol(entry):
    if isinstance(entry, str):
        return entry
    return entry.get('asset') or entry.get('symbol')


def _entry_name(entry):
    if isinstance(entry, str):
        return ''
    for key in ('name', 'companyName', 'company_name'):
        if entry.get(key):
            return str(entry[key])
    return ''


def build_symbol_index() -> list:
    """One row per searchable symbol: {symbol, name, kind}."""
    rows = {}

    for constituent_key in STOCK_CONSTITUENT_KEYS:
        try:
            constituents = data_getter.get_index_constituents(constituent_key)
        except Exception:
            # A missing constituent file must not sink the whole typeahead --
            # the other universes are still usable.
            continue
        for entry in constituents:
            symbol = _entry_symbol(entry)
            if symbol:
                rows.setdefault(str(symbol).upper(),
                                {'symbol': str(symbol).upper(),
                                 'name': _entry_name(entry),
                                 'kind': 'stock'})

    try:
        for entry in data_getter.get_index_constituents('etfs'):
            symbol = _entry_symbol(entry)
            if symbol:
                rows[str(symbol).upper()] = {'symbol': str(symbol).upper(),
                                             'name': _entry_name(entry),
                                             'kind': 'etf'}
    except Exception:
        pass

    # Fill in the names the constituent lists leave blank.
    missing = [symbol for symbol, row in rows.items() if not row['name']]
    if missing:
        try:
            profiles = data_getter.load_long_profiles()
            name_column = next((c for c in ('companyName', 'company_name', 'name')
                                if c in profiles.columns), None)
            if name_column:
                lookup = dict(zip(profiles['symbol'].astype(str).str.upper(),
                                  profiles[name_column].astype(str)))
                for symbol in missing:
                    rows[symbol]['name'] = lookup.get(symbol, '')
        except Exception:
            pass

    return sorted(rows.values(), key=lambda row: row['symbol'])


def get_symbol_index() -> list:
    compressed = cache.get(CACHE_KEY)
    if compressed:
        try:
            return json.loads(gzip.decompress(compressed))
        except Exception:
            cache.delete(CACHE_KEY)

    index = build_symbol_index()
    cache.set(CACHE_KEY, gzip.compress(json.dumps(index).encode('utf-8')),
              timeout=CACHE_TIMEOUT)
    return index


def search(query: str, limit: int = 25) -> list:
    """Rank exact symbol match, then symbol prefix, then name substring."""
    query = (query or '').strip().upper()
    if len(query) < 1:
        return []

    exact, prefix, contains = [], [], []
    for row in get_symbol_index():
        symbol = row['symbol']
        if symbol == query:
            exact.append(row)
        elif symbol.startswith(query):
            prefix.append(row)
        elif query in symbol or query in row['name'].upper():
            contains.append(row)
        if len(exact) + len(prefix) + len(contains) >= limit * 4:
            break

    # Sort within each bucket rather than inheriting the index's own order.
    # build_symbol_index() happens to return rows sorted by symbol, but ranking
    # must not depend on an invariant maintained in a different function -- a
    # cached index built by an older version, or a test double, would otherwise
    # silently reorder the typeahead.
    by_symbol = lambda row: row['symbol']
    return (exact + sorted(prefix, key=by_symbol)
            + sorted(contains, key=by_symbol))[:limit]
