"""Small builders for fixture data shaped like FMP payloads on disk."""
import json
import os

import pandas as pd


def write_constituents(p, key, symbols):
    path = p.constituents_path(key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump([{"asset": s, "weightPercentage": 100 / len(symbols)}
                   for s in symbols], f)


def price_rows(end, n=40, start_price=100.0):
    """FMP 'historical' rows, newest first, the last one on business day `end`."""
    days = pd.bdate_range(end=end, periods=n)
    rows = []
    for i, day in enumerate(days):
        price = start_price + i
        rows.append({"date": day.strftime("%Y-%m-%d"), "open": price,
                     "high": price, "low": price, "close": price,
                     "adjClose": price, "volume": 1000})
    return list(reversed(rows))


def write_price_json(p, sub, symbol, end, n=40):
    folder = p.json_dir("stock_prices", sub)
    os.makedirs(folder, exist_ok=True)
    with open(f"{folder}{symbol}_prices.json", "w") as f:
        json.dump({"symbol": symbol, "historical": price_rows(end, n)}, f)


def load_fixture(name, ext="json"):
    """Read a captured FMP stable response from tests/fixtures/fmp_stable/."""
    path = os.path.join(os.path.dirname(__file__), "fixtures", "fmp_stable",
                        f"{name}.{ext}")
    with open(path, newline="") as f:
        return f.read() if ext == "csv" else json.load(f)


def stable_history_get(by_symbol):
    """A fake `_get` for stable historical-price-eod/{full,dividend-adjusted}.

    by_symbol maps a symbol to its rows (newest first), an Exception to raise,
    or a callable (from, to, path) -> rows. Rows are filtered by the from/to
    query params and capped at HISTORY_ROW_CAP, newest first, as FMP does.
    Returns (get, calls) where calls is a list of (path, params) per request.
    Never touches the network."""
    from urllib.parse import parse_qs, urlparse

    from pipelines.fmp_stable_shapes import HISTORY_ROW_CAP

    calls = []

    def _get(url, timeout=30):
        parsed = urlparse(url)
        path = parsed.path.split("/stable/", 1)[1]
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        calls.append((path, params))
        assert path in ("historical-price-eod/full",
                        "historical-price-eod/dividend-adjusted"), url
        source = by_symbol[params["symbol"]]
        if isinstance(source, Exception):
            raise source
        lo, hi = params.get("from"), params.get("to")
        if callable(source):
            return source(lo, hi, path)
        rows = [r for r in source
                if (lo is None or r["date"] >= lo) and (hi is None or r["date"] <= hi)]
        return sorted(rows, key=lambda r: r["date"], reverse=True)[:HISTORY_ROW_CAP]
    return _get, calls
