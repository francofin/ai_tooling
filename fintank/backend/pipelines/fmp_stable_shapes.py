"""Reshape FMP `stable` responses into the v3 row shapes the pipeline expects.

Pure functions: no I/O, no pandas, no Django.
"""
from datetime import date

# Stable /historical-price-eod/full returns at most this many rows per call.
HISTORY_ROW_CAP = 5000

_OPTIONAL = ("change", "changePercent", "vwap")


def v3_label(d: str) -> str:
    """'2026-11-05' -> 'November 05, 26' (day zero-padded, as v3 did) (the v3 `label` field)."""
    return date.fromisoformat(d).strftime("%B %d, %y")


def _volume(v):
    return int(v) if v is not None else None


def _row(r: dict, adj_close) -> dict:
    out = {
        "date": r["date"],
        "open": r.get("open"),
        "high": r.get("high"),
        "low": r.get("low"),
        "close": r.get("close"),
        "adjClose": adj_close,
        "volume": _volume(r.get("volume")),
        "label": v3_label(r["date"]),
    }
    for k in _OPTIONAL:
        if k in r:
            out[k] = r[k]
    return out


def _newest_first(rows):
    return sorted(rows, key=lambda r: r["date"], reverse=True)


def price_payload(symbol: str, full_rows: list, adjusted_rows: list) -> dict:
    """v3-shaped {"symbol", "historical"}; adjClose joined from the
    dividend-adjusted rows by date (None where it has no matching date)."""
    adj = {r["date"]: r.get("adjClose") for r in adjusted_rows}
    return {"symbol": symbol,
            "historical": [_row(r, adj.get(r["date"]))
                           for r in _newest_first(full_rows)]}


def index_payload(symbol: str, full_rows: list) -> dict:
    """Same shape for indices, which have no adjusted series: adjClose = close."""
    return {"symbol": symbol,
            "historical": [_row(r, r.get("close"))
                           for r in _newest_first(full_rows)]}
