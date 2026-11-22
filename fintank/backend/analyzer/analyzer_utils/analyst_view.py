"""Stock-page analyst view: pure shaping helpers first, then the cached FMP getters below."""
from datetime import date

import requests
from django.core.cache import cache
from django.utils import timezone

from utils.fmp_stable import (
    analyst_estimates, exchange_variants, fx_rate, grades_consensus,
    price_target_consensus, price_target_summary, reported_currency,
)

US_EXCHANGES = {"New York Stock Exchange": "NYSE"}
MIN_TARGET_COUNT = 3

_ESTIMATE_METRICS = ("revenue", "eps", "ebitda")
_TARGET_KEYS = (("consensus", "targetConsensus"), ("median", "targetMedian"),
                ("low", "targetLow"), ("high", "targetHigh"))


def _us_label(exchange):
    if not exchange:
        return None
    if exchange in US_EXCHANGES:
        return US_EXCHANGES[exchange]
    if exchange.startswith(("NASDAQ", "Nasdaq")):
        return "Nasdaq"
    return None


def pick_us_listing(symbol, variants):
    if not symbol.endswith(".TO"):
        return None
    for v in variants or []:
        label = _us_label(v.get("exchange"))
        if label:
            return {"symbol": v["symbol"], "exchange": label}
    return None


def shape_estimates(rows, period, today):
    n = 4 if period == "quarter" else 3
    iso = today.isoformat() if isinstance(today, date) else str(today)
    future = sorted((r for r in rows or [] if r.get("date") and r["date"] >= iso),
                    key=lambda r: r["date"])[:n]
    return [
        {"date": r["date"],
         **{m: {"low": r.get(m + "Low"), "avg": r.get(m + "Avg"), "high": r.get(m + "High")}
            for m in _ESTIMATE_METRICS}}
        for r in future
    ]


def shape_ratings(row):
    if not row:
        return None
    keys = ("strongBuy", "buy", "hold", "sell", "strongSell")
    counts = {k: row.get(k) or 0 for k in keys}
    total = sum(counts.values())
    if total == 0:
        return None
    return {**counts, "consensus": row.get("consensus"), "total": total}


def shape_target(consensus, summary, *, from_us, usdcad):
    count = (summary or {}).get("lastYearCount") or 0
    if consensus is None or count < MIN_TARGET_COUNT:
        return None
    vals = {out: consensus.get(src) for out, src in _TARGET_KEYS}
    cad = None
    if from_us and usdcad is not None:
        cad = {k: (v * usdcad if v is not None else None) for k, v in vals.items()}
    return {**vals, "count_last_year": count,
            "currency": "USD" if from_us else None, "cad": cad}


def build_payload(symbol, *, estimates_annual, ratings, target, source, reporting_currency):
    if not estimates_annual and ratings is None and target is None:
        raise KeyError(symbol)
    return {"symbol": symbol, "estimates": {"annual": estimates_annual},
            "ratings": ratings, "target": target, "source": source,
            "reporting_currency": reporting_currency}


# ---- cached layer ----------------------------------------------------------

PAYLOAD_TTL = 86400
LISTING_TTL = 2592000
FX_TTL = 86400

_FMP_ERRORS = (requests.RequestException, ValueError)


class AnalystUnavailable(Exception):
    """FMP failed; nothing was cached."""


def _norm(symbol):
    return symbol.strip().upper()


def _listing(symbol):
    key = f"stock:analyst:listing:{symbol}:v1"
    hit = cache.get(key)
    if hit is not None:
        return hit
    source = None
    if symbol.endswith(".TO"):
        source = pick_us_listing(symbol, exchange_variants(symbol))
    listing = {"source": source, "reporting_currency": reported_currency(symbol)}
    cache.set(key, listing, timeout=LISTING_TTL)
    return listing


def _usdcad():
    key = "fx:usdcad:v1"
    hit = cache.get(key)
    if hit is not None:
        return hit
    try:
        rate = fx_rate("USDCAD")
    except Exception:  # RequestException, ValueError, TypeError: degrade to USD only
        return None
    if rate is not None:
        cache.set(key, rate, timeout=FX_TTL)
    return rate


def get_analyst_view(symbol):
    symbol = _norm(symbol)
    key = f"stock:analyst:{symbol}:v1"
    missing_key = f"stock:analyst:missing:{symbol}:v1"
    hit = cache.get(key)
    if hit is not None:
        return hit
    if cache.get(missing_key):
        raise KeyError(symbol)
    try:
        listing = _listing(symbol)
        source = listing["source"]
        target_symbol = source["symbol"] if source else symbol
        rows = analyst_estimates(symbol, "annual", limit=10)
        ratings = shape_ratings(grades_consensus(target_symbol))
        consensus = price_target_consensus(target_symbol)
        summary = price_target_summary(target_symbol)
    except _FMP_ERRORS as exc:
        raise AnalystUnavailable(symbol) from exc
    usdcad = _usdcad() if source else None
    target = shape_target(consensus, summary, from_us=bool(source), usdcad=usdcad)
    try:
        payload = build_payload(
            symbol,
            estimates_annual=shape_estimates(rows, "annual", timezone.localdate()),
            ratings=ratings, target=target, source=source,
            reporting_currency=listing["reporting_currency"])
    except KeyError:
        cache.set(missing_key, True, timeout=PAYLOAD_TTL)
        raise
    cache.set(key, payload, timeout=PAYLOAD_TTL)
    return payload


def get_quarterly_estimates(symbol):
    symbol = _norm(symbol)
    key = f"stock:analyst:quarter:{symbol}:v1"
    hit = cache.get(key)
    if hit is not None:
        return hit
    try:
        rows = analyst_estimates(symbol, "quarter", limit=12)
    except _FMP_ERRORS as exc:
        raise AnalystUnavailable(symbol) from exc
    quarters = shape_estimates(rows, "quarter", timezone.localdate())
    if not quarters:
        raise KeyError(symbol)
    payload = {"symbol": symbol, "estimates": {"quarter": quarters}}
    cache.set(key, payload, timeout=PAYLOAD_TTL)
    return payload
