"""Fund finder: rank ETFs by the combined weight of the stocks a reader wants exposure to.

Reads the weekly pipeline output (fund_data/ in S3) through Redis. Exposure is
sharded into 64 buckets by company id, so a query loads only the shards it needs.
"""
import hashlib
import io
import json
import re
from collections import Counter

import pandas as pd
import requests
from django.core.cache import cache

from .CorePerformanceTools import data_getter

BUCKET_URL = "s3://thetradingfloor/"
TTL = 6 * 3600
BUCKETS = 64
MAX_PICKS = 10
DEFAULT_LIMIT = 100
HOLDING_LIMIT = 10
COLLAPSE_TOLERANCE = 0.01
LISTED = ("ca", "us", "both")

_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,19}$")
_READ_ERRORS = (requests.RequestException, ValueError, OSError)


class FundsUnavailable(Exception):
    """S3 failed; nothing was cached."""


class BadQuery(Exception):
    """The request is invalid; the message is safe to show the client."""


def bucket_of(company_id):
    return int(hashlib.md5(company_id.encode()).hexdigest(), 16) % BUCKETS


def _read_parquet(key):
    try:
        with data_getter.fs.open(BUCKET_URL + key) as f:
            return pd.read_parquet(io.BytesIO(f.read()))
    except _READ_ERRORS as exc:
        raise FundsUnavailable(key) from exc


def _symbols(raw):
    """Normalised, de-duplicated symbols in order; blanks dropped."""
    out = []
    for token in (raw or "").split(","):
        token = token.strip().upper()
        if token and token not in out:
            out.append(token)
    return out


def parse_query(params):
    listed = (params.get("listed") or "").strip().lower()
    if listed not in LISTED:
        raise BadQuery("listed is required (ca, us or both)")
    include = _symbols(params.get("include"))
    exclude = _symbols(params.get("exclude"))
    if not include:
        raise BadQuery("at least one stock to include")
    if len(include) > MAX_PICKS:
        raise BadQuery(f"at most {MAX_PICKS} stocks to include")
    if len(exclude) > MAX_PICKS:
        raise BadQuery(f"at most {MAX_PICKS} stocks to exclude")
    return include, exclude, listed


def _cached_frame(key, loader):
    hit = cache.get(key)
    if hit is not None:
        return hit
    frame = loader()
    cache.set(key, frame, timeout=TTL)
    return frame


def _meta():
    def load():
        return {
            "funds": _read_parquet("fund_data/funds.parquet"),
            "isin": _read_parquet("fund_data/isin_map.parquet"),
        }
    return _cached_frame("funds:meta:v1", load)


def _bucket(n):
    return _cached_frame(f"funds:bucket:{n:02d}:v1",
                         lambda: _read_parquet(f"fund_data/exposure/{n:02d}.parquet"))


def _resolve(symbols, by_symbol):
    """([(symbol, company_id)] de-duplicated by company, [unknown])."""
    picks, unknown, seen = [], [], set()
    for sym in symbols:
        cid = by_symbol.get(sym) if _SYMBOL_RE.match(sym) else None
        if cid is None:
            unknown.append(sym)
        elif cid not in seen:
            seen.add(cid)
            picks.append((sym, cid))
    return picks, unknown


def _num(value):
    return None if value is None or pd.isna(value) else round(float(value), 4)


def _collapse(rows):
    """Merge duplicate funds in one market: same issuer and every pick's weight within tolerance."""
    kept = []
    for row in sorted(rows, key=lambda r: -(r["aum"] or 0.0)):
        for winner in kept:
            if (winner["region"] == row["region"] and winner["issuer"] and row["issuer"]
                    and winner["issuer"] == row["issuer"]
                    and all(abs(winner["weights"][p]["weight"] - row["weights"][p]["weight"]) <= COLLAPSE_TOLERANCE
                            for p in winner["weights"])):
                winner["also"] |= row["also"] | {row["symbol"]}
                break
        else:
            kept.append(row)
    return kept


def _query(include, exclude, listed, limit):
    meta = _meta()
    isin = meta["isin"]
    by_symbol = dict(zip(isin["symbol"], isin["company_id"]))
    picks, unknown_in = _resolve(include, by_symbol)
    out, unknown_ex = _resolve(exclude, by_symbol)
    clash = {cid: sym for sym, cid in picks}
    for sym, cid in out:
        if cid in clash:
            raise BadQuery(f"{sym} is in both include and exclude")
    unknown = unknown_in + unknown_ex
    result = {"listed": listed, "include": [s for s, _ in picks], "exclude": [s for s, _ in out],
              "unknown": unknown, "fetched": None, "funds": []}
    if not picks:
        return result

    wanted = {cid for _, cid in picks} | {cid for _, cid in out}
    frames = []
    for n in sorted({bucket_of(c) for c in wanted}):
        frame = _bucket(n)
        frames.append(frame[frame["company_id"].isin(wanted)])
    exposure = pd.concat(frames) if frames else pd.DataFrame(columns=["company_id", "fund", "weight", "via"])

    excluded_cids = {cid for _, cid in out}
    dropped = set(exposure.loc[exposure["company_id"].isin(excluded_cids), "fund"])
    included_cids = {cid for _, cid in picks}
    held = exposure[exposure["company_id"].isin(included_cids) & ~exposure["fund"].isin(dropped)]

    funds = meta["funds"].set_index("symbol", drop=False)
    per_fund = {}
    for r in held.itertuples(index=False):
        slot = per_fund.setdefault(r.fund, {}).setdefault(r.company_id, [0.0, set()])
        slot[0] += float(r.weight)
        if r.via:
            slot[1].add(r.via)

    rows = []
    for fund_symbol, by_company in per_fund.items():
        if fund_symbol not in funds.index:
            continue
        info = funds.loc[fund_symbol]
        if listed != "both" and info["region"] != listed:
            continue
        weights = {}
        for sym, cid in picks:
            weight, via = by_company.get(cid, (0.0, set()))
            weights[sym] = {"weight": round(weight, 4), "via": sorted(via)}
        series = info["series"]
        rows.append({
            "symbol": fund_symbol, "name": info["name"], "exchange": info["exchange"],
            "region": info["region"], "currency": info["currency"],
            "combined": round(sum(w["weight"] for w in weights.values()), 4),
            "weights": weights, "mer": _num(info["mer"]), "aum": _num(info["aum"]),
            "fetched": info["fetched"], "issuer": info["issuer"] if isinstance(info["issuer"], str) else None,
            "also": {s for s in (list(series) if series is not None else []) if s != fund_symbol},
        })

    rows = _collapse(rows)
    rows.sort(key=lambda r: (-r["combined"], -(r["aum"] or 0.0), r["symbol"]))
    rows = rows[:limit]
    for r in rows:
        r["also"] = sorted(r["also"])
        del r["issuer"], r["region"]
    if rows:
        counts = Counter(r["fetched"] for r in rows)
        result["fetched"] = max(counts, key=lambda d: (counts[d], d))
    result["funds"] = rows
    return result


def find_funds(include, exclude, listed, limit=DEFAULT_LIMIT):
    include, exclude = _symbols(",".join(include)), _symbols(",".join(exclude))
    digest = hashlib.sha1(json.dumps([include, exclude, listed, limit]).encode()).hexdigest()
    key = f"funds:query:{digest}:v1"
    hit = cache.get(key)
    if hit is not None:
        return hit
    result = _query(include, exclude, listed, limit)
    cache.set(key, result, timeout=TTL)
    return result
