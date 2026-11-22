"""FMP stable endpoints for the earnings hub: who reported, which fiscal
quarter, and the transcript. `get` has http_get_json's signature so tests pass
a fake. The API key never appears in an exception."""
from __future__ import annotations

import datetime as dt
import time

import requests

from pipelines.results import redact

FMP_STABLE = "https://financialmodelingprep.com/stable"
CONSTITUENT_FILES = (
    ("ca", "index_data/constituents/tsx_const_constituents.json"),
    ("us", "index_data/constituents/sp500_const_constituents.json"),
)


def http_get_json(url, params=None, timeout=30, retries=1):
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as e:
            if attempt == retries:
                if isinstance(e, requests.RequestException):
                    raise RuntimeError(redact(str(e))) from None
                raise
            time.sleep(2)


def covered_symbols(read_live_json) -> dict:
    """symbol -> {region, name}. TSX first so a dual-listed symbol stays 'ca'."""
    covered = {}
    for region, key in CONSTITUENT_FILES:
        for row in read_live_json(key) or []:
            asset = row.get("asset")
            if asset:
                covered.setdefault(asset, {"region": region, "name": row.get("name") or asset})
    return covered


def fetch_calendar(api_key, start: dt.date, end: dt.date, get=http_get_json) -> list:
    rows = get(f"{FMP_STABLE}/earnings-calendar",
               params={"from": start.isoformat(), "to": end.isoformat(), "apikey": api_key})
    if not isinstance(rows, list):
        raise ValueError(f"unexpected FMP calendar payload: {str(rows)[:200]}")
    return rows


def transcript_dates(api_key, symbol, get=http_get_json) -> list:
    """[(fiscal_year, quarter, date)] newest first. Labels come from here only."""
    rows = get(f"{FMP_STABLE}/earning-call-transcript-dates",
               params={"symbol": symbol, "apikey": api_key})
    if not isinstance(rows, list):
        raise ValueError(f"unexpected FMP transcript-dates payload: {str(rows)[:200]}")
    out = [(int(r["fiscalYear"]), int(r["quarter"]), r.get("date") or "")
           for r in rows if r.get("fiscalYear") is not None and r.get("quarter") is not None]
    return sorted(out, key=lambda t: (t[0], t[1]), reverse=True)


def fetch_transcript(api_key, symbol, fiscal_year, quarter, get=http_get_json):
    """(content, call_date). LookupError when FMP has no text for it."""
    rows = get(f"{FMP_STABLE}/earning-call-transcript",
               params={"symbol": symbol, "year": fiscal_year, "quarter": quarter,
                       "apikey": api_key})
    row = rows[0] if isinstance(rows, list) and rows else None
    content = ((row or {}).get("content") or "").strip()
    if not content:
        raise LookupError(f"no transcript for {symbol} FY{fiscal_year} Q{quarter}")
    return content, row.get("date") or ""


def fetch_estimates(api_key, symbol, call_date, get=http_get_json, slack_days=2):
    """(report_date, estimates) for the report a call discussed, from FMP's
    per-symbol earnings history: the latest report dated on or up to
    `slack_days` before the call. None when no report falls in that window."""
    rows = get(f"{FMP_STABLE}/earnings",
               params={"symbol": symbol, "limit": 12, "apikey": api_key})
    if not isinstance(rows, list):
        raise ValueError(f"unexpected FMP earnings payload: {str(rows)[:200]}")
    call = dt.date.fromisoformat(str(call_date)[:10])
    best = None
    for row in rows:
        try:
            date = dt.date.fromisoformat(str(row.get("date"))[:10])
        except ValueError:
            continue
        if 0 <= (call - date).days <= slack_days and (best is None or date > best[0]):
            best = (date, row)
    if best is None:
        return None
    date, row = best
    return date.isoformat(), {"eps_estimate": row.get("epsEstimated"),
                              "eps_actual": row.get("epsActual"),
                              "revenue_estimate": row.get("revenueEstimated"),
                              "revenue_actual": row.get("revenueActual")}
