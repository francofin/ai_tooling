"""Earnings hub: the weekly calendar (FMP) and Claude-written notes (S3), both served via Redis."""
import json
import re
from datetime import date, timedelta

import requests
from django.core.cache import cache

from utils.fmp_stable import earnings_calendar
from .CorePerformanceTools import data_getter

BUCKET_URL = "s3://thetradingfloor/"
NOTES_TTL = 3600
CALENDAR_TTL = 21600
COVERED_TTL = 86400

_QUARTER_RE = re.compile(r"^\d{4}-Q[1-4]$")
_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,19}$")
_READ_ERRORS = (requests.RequestException, ValueError, OSError)


class NotesUnavailable(Exception):
    """FMP or S3 failed; nothing was cached."""


def monday_of(d):
    return d - timedelta(days=d.weekday())


def _read_json(key):
    """Parsed S3 object, or None when it does not exist."""
    try:
        with data_getter.fs.open(BUCKET_URL + key) as f:
            return json.loads(f.read())
    except FileNotFoundError:
        return None
    except _READ_ERRORS as exc:
        raise NotesUnavailable(key) from exc


def get_covered_symbols():
    key = "home:earnings:covered:v1"
    hit = cache.get(key)
    if hit is not None:
        return hit
    covered = {}
    try:
        # tsx first so a dual-listed symbol stays "ca".
        for index, region in (("tsx", "ca"), ("sp500", "us")):
            for row in data_getter.get_index_constituents(index):
                covered.setdefault(row["asset"], {"region": region, "name": row.get("name") or row["asset"]})
    except _READ_ERRORS as exc:
        raise NotesUnavailable("constituents") from exc
    cache.set(key, covered, timeout=COVERED_TTL)
    return covered


def get_earnings_calendar(week):
    start = monday_of(week)
    key = f"home:earnings:calendar:{start.isoformat()}:v1"
    hit = cache.get(key)
    if hit is not None:
        return hit
    covered = get_covered_symbols()
    try:
        fmp_rows = earnings_calendar(start, start + timedelta(days=4))
    except (requests.RequestException, ValueError) as exc:
        raise NotesUnavailable("earnings-calendar") from exc
    latest = _read_json("earnings_notes/latest.json") or {}
    rows = []
    for r in fmp_rows:
        info = covered.get(r.get("symbol"))
        if not info or not r.get("date"):
            continue
        try:
            if date.fromisoformat(r["date"][:10]).weekday() > 4:
                continue
        except ValueError:
            continue
        rows.append({
            "symbol": r["symbol"], "name": info["name"], "region": info["region"],
            "date": r["date"][:10],
            "eps_estimate": r.get("epsEstimated"), "eps_actual": r.get("epsActual"),
            "revenue_estimate": r.get("revenueEstimated"), "revenue_actual": r.get("revenueActual"),
            "note_quarter": latest.get(r["symbol"]),
        })
    rows.sort(key=lambda x: (x["date"], x["symbol"]))
    payload = {"week_start": start.isoformat(), "rows": rows}
    cache.set(key, payload, timeout=CALENDAR_TTL)
    return payload


def _norm(symbol):
    symbol = symbol.strip().upper()
    if not _SYMBOL_RE.match(symbol):
        raise KeyError(symbol)
    return symbol


def _live_quarters(symbol):
    """Non-withdrawn index entries, newest first."""
    index = _read_json(f"earnings_notes/{symbol}/index.json")
    entries = index.get("quarters", []) if isinstance(index, dict) else (index or [])
    live = [e for e in entries if not e.get("withdrawn")]
    live.sort(key=lambda e: (e["fiscal_year"], e["fiscal_quarter"]), reverse=True)
    return live


def _read_note(symbol, quarter):
    note = _read_json(f"earnings_notes/{symbol}/{quarter}.json")
    if note is None:
        raise KeyError(f"{symbol} {quarter}")
    return note


def get_note_index(symbol):
    symbol = _norm(symbol)
    key = f"home:earnings:notes:{symbol}:v1"
    hit = cache.get(key)
    if hit is not None:
        return hit
    quarters = _live_quarters(symbol)
    if not quarters:
        raise KeyError(symbol)
    payload = {"symbol": symbol, "quarters": quarters,
               "latest": _read_note(symbol, quarters[0]["quarter"])}
    cache.set(key, payload, timeout=NOTES_TTL)
    return payload


def get_note(symbol, quarter):
    symbol = _norm(symbol)
    if not _QUARTER_RE.match(quarter):
        raise KeyError(quarter)
    key = f"home:earnings:note:{symbol}:{quarter}:v1"
    hit = cache.get(key)
    if hit is not None:
        return hit
    if quarter not in {e["quarter"] for e in _live_quarters(symbol)}:
        raise KeyError(f"{symbol} {quarter}")
    note = _read_note(symbol, quarter)
    cache.set(key, note, timeout=NOTES_TTL)
    return note
