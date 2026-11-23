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
        raise FundsUnavailable(UNAVAILABLE) from exc


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


FUNDS_COLUMNS = ["symbol", "name", "exchange", "region", "currency", "aum", "mer", "issuer", "fetched", "series"]
UNAVAILABLE = "Fund data is unavailable right now."


def _meta():
    """Slim, plain-Python meta: symbol -> company id, and fund rows as dicts."""
    hit = cache.get("funds:meta:v1")
    if hit is not None:
        return hit
    isin = _read_parquet("fund_data/isin_map.parquet")
    funds = _read_parquet("fund_data/funds.parquet")
    meta = {
        "by_symbol": dict(zip(isin["symbol"], isin["company_id"])),
        "funds": {
            r["symbol"]: {**r, "series": [str(x) for x in (r["series"] if r["series"] is not None else [])]}
            for r in funds.reindex(columns=FUNDS_COLUMNS).to_dict("records")
        },
    }
    cache.set("funds:meta:v1", meta, timeout=TTL)
    return meta


def _holdings(company_ids):
    """{company_id: [(fund, weight, via)]}. Only per-company rows are cached; buckets are not."""
    out, missing = {}, {}
    for cid in company_ids:
        hit = cache.get(f"funds:company:{cid}:v1")
        if hit is not None:
            out[cid] = hit
        else:
            missing.setdefault(bucket_of(cid), []).append(cid)
    for n, cids in missing.items():
        frame = _read_parquet(f"fund_data/exposure/{n:02d}.parquet")
        frame = frame[frame["company_id"].isin(cids)]
        rows = {cid: [] for cid in cids}
        for r in frame.itertuples(index=False):
            rows[r.company_id].append((str(r.fund), float(r.weight), r.via or ""))
        for cid, tuples in rows.items():
            cache.set(f"funds:company:{cid}:v1", tuples, timeout=TTL)
            out[cid] = tuples
    return out


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
    groups = {}  # (region, issuer) -> kept rows, in kept order; only these can merge
    for row in sorted(rows, key=lambda r: -(r["aum"] or 0.0)):
        group = groups.setdefault((row["region"], row["issuer"]), []) if row["issuer"] else []
        for winner in group:
            if all(abs(winner["weights"][p]["weight"] - row["weights"][p]["weight"]) <= COLLAPSE_TOLERANCE
                   for p in winner["weights"]):
                winner["also"] = (winner["also"] | row["also"] | {row["symbol"]}) - {winner["symbol"]}
                break
        else:
            kept.append(row)
            group.append(row)
    return kept


def _query(include, exclude, listed, limit):
    meta = _meta()
    funds = meta["funds"]
    picks, unknown_in = _resolve(include, meta["by_symbol"])
    out, unknown_ex = _resolve(exclude, meta["by_symbol"])
    clash = {cid for _, cid in picks}
    for sym, cid in out:
        if cid in clash:
            raise BadQuery(f"{sym} is in both include and exclude")
    result = {"listed": listed, "include": [s for s, _ in picks], "exclude": [s for s, _ in out],
              "unknown": unknown_in + unknown_ex, "fetched": None, "funds": []}
    if not picks:
        return result

    holdings = _holdings(clash | {cid for _, cid in out})
    dropped = {f for _, cid in out for f, _, _ in holdings[cid]}
    per_fund = {}
    for _, cid in picks:
        for fund_symbol, weight, via in holdings[cid]:
            if fund_symbol in dropped:
                continue
            slot = per_fund.setdefault(fund_symbol, {}).setdefault(cid, [0.0, set()])
            slot[0] += weight
            if via:
                slot[1].add(via)

    rows = []
    for fund_symbol, by_company in per_fund.items():
        info = funds.get(fund_symbol)
        if info is None or (listed != "both" and info["region"] != listed):
            continue
        weights = {}
        for sym, cid in picks:
            weight, via = by_company.get(cid, (0.0, set()))
            weights[sym] = {"weight": round(weight, 4), "via": sorted(via)}
        rows.append({
            "symbol": fund_symbol, "name": info["name"], "exchange": info["exchange"],
            "region": info["region"], "currency": info["currency"],
            "combined": round(sum(w["weight"] for w in weights.values()), 4),
            "weights": weights, "mer": _num(info["mer"]), "aum": _num(info["aum"]),
            "fetched": info["fetched"], "issuer": info["issuer"] if isinstance(info["issuer"], str) else None,
            "also": set(info["series"]) - {fund_symbol},
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
    if result["include"]:  # junk queries must not mint cache keys
        cache.set(key, result, timeout=TTL)
    return result
