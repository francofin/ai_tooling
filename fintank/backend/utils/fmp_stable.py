"""Shared client for the FMP `stable` API (the retired `api/v3` routes return 403)."""

import requests
from django.conf import settings

STABLE_BASE = "https://financialmodelingprep.com/stable/"


def split_symbols(raw):
    """Split a comma separated string (or list of such) into clean symbols, keeping order."""
    parts = [raw] if isinstance(raw, str) else list(raw)
    out = []
    for part in parts:
        for sym in str(part).split(","):
            sym = sym.strip()
            if sym:
                out.append(sym)
    return out


def _get_list(path, params, timeout):
    params = {**params, "apikey": settings.FMP_API}
    resp = requests.get(STABLE_BASE + path, params=params, timeout=timeout)
    resp.raise_for_status()
    body = resp.json()
    if not isinstance(body, list):
        raise ValueError(f"FMP {path} returned a non-list body")
    return body


def to_v3_quote(row):
    out = dict(row)
    out["changesPercentage"] = row.get("changePercentage")
    return out


def batch_quotes(symbols, *, timeout=15):
    rows = _get_list("batch-quote", {"symbols": ",".join(symbols)}, timeout)
    return [to_v3_quote(r) for r in rows]


def _oldest_first(rows):
    return sorted((r for r in rows if r.get("date")), key=lambda r: r["date"])


def index_history(symbol, *, timeout=15):
    rows = _get_list("historical-price-eod/full", {"symbol": symbol}, timeout)
    out = []
    for r in _oldest_first(rows):
        r = dict(r)
        if "adjClose" not in r:
            r["adjClose"] = r.get("close")
        out.append(r)
    return out


def adjusted_history(symbol, *, from_date="1990-01-01", timeout=20):
    # Without `from`, stable returns only 5 years; with it, up to 5000 rows (~20y).
    rows = _get_list(
        "historical-price-eod/dividend-adjusted",
        {"symbol": symbol, "from": from_date},
        timeout,
    )
    return _oldest_first(rows)


def _first_row(path, params, timeout):
    rows = _get_list(path, params, timeout)
    return rows[0] if rows else None


def analyst_estimates(symbol, period, *, limit, timeout=15):
    # period: "annual" or "quarter"
    return _get_list(
        "analyst-estimates",
        {"symbol": symbol, "period": period, "limit": limit},
        timeout,
    )


def grades_consensus(symbol, *, timeout=15):
    return _first_row("grades-consensus", {"symbol": symbol}, timeout)


def price_target_consensus(symbol, *, timeout=15):
    return _first_row("price-target-consensus", {"symbol": symbol}, timeout)


def price_target_summary(symbol, *, timeout=15):
    return _first_row("price-target-summary", {"symbol": symbol}, timeout)


def exchange_variants(symbol, *, timeout=15):
    return _get_list("search-exchange-variants", {"symbol": symbol}, timeout)


def reported_currency(symbol, *, timeout=15):
    row = _first_row("income-statement", {"symbol": symbol, "limit": 1}, timeout)
    return row.get("reportedCurrency") if row else None


def fx_rate(pair="USDCAD", *, timeout=15):
    row = _first_row("quote", {"symbol": pair}, timeout)
    return float(row["price"]) if row and row.get("price") is not None else None
