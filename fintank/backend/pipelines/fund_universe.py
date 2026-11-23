"""Fund universe and company ids for the fund finder (pure, no network).

`build_universe` picks the ETFs worth indexing from FMP's bulk profile rows;
`company_ids` maps stock symbols/ISINs to one id per company so a stock and
its interlisted or ADR lines count once; `bucket_of` shards company ids.
"""
import hashlib
import math
import re
from collections import Counter

from . import pipeline_config as cfg

_LEVERAGED = re.compile(cfg.FUND_LEVERAGED_PATTERN, re.IGNORECASE)
_SERIES_SUFFIX = re.compile(r"[-.]([UT])(?=\.TO$|$)", re.IGNORECASE)
_NAME_NOISE = re.compile(
    r"\b(cad|usd|hedged|unhedged|non-hedged|units|series|class)\b")


def _flag(row, key):
    return str(row.get(key, "")).strip().lower() == "true"


def _aum(row):
    try:
        v = float(row.get("marketCap") or 0)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) else 0.0


def _region(exchange):
    if exchange in cfg.FUND_US_EXCHANGES:
        return "us"
    if exchange in cfg.FUND_CA_EXCHANGES:
        return "ca"
    return None


def _series_key(symbol, name):
    base = _SERIES_SUFFIX.sub("", symbol)
    norm = " ".join(_NAME_NOISE.sub(" ", name.lower()).split())
    return base, norm


def build_universe(bulk_rows):
    """Return (funds, detail) for active US/CA ETFs above the AUM floor.

    Leveraged/inverse funds are dropped by name; share-class series of one
    fund collapse into the largest line (the unsuffixed symbol on a tie).
    """
    active = []
    for r in bulk_rows:
        region = _region(r.get("exchange"))
        if (_flag(r, "isEtf") and _flag(r, "isActivelyTrading")
                and not _flag(r, "isFund") and region):
            active.append((r, region))

    dropped_leveraged, dropped_floor, kept = [], 0, []
    for r, region in active:
        name = r.get("companyName") or ""
        if _LEVERAGED.search(name):
            dropped_leveraged.append(name)
        elif _aum(r) < cfg.FUND_AUM_FLOOR[region]:
            dropped_floor += 1
        else:
            kept.append((r, region))

    groups = {}
    for r, region in kept:
        key = _series_key(r["symbol"], r.get("companyName") or "")
        groups.setdefault(key, []).append((r, region))

    funds, collapsed = [], 0
    for key, members in groups.items():
        base = key[0]
        # largest AUM first; on a tie the symbol without a suffix wins
        members.sort(key=lambda m: (-_aum(m[0]), m[0]["symbol"] != base,
                                    m[0]["symbol"]))
        r, region = members[0]
        others = sorted(m[0]["symbol"] for m in members[1:])
        collapsed += len(others)
        funds.append({
            "symbol": r["symbol"], "name": r.get("companyName") or "",
            "exchange": r.get("exchange"), "region": region,
            "currency": r.get("currency"), "aum": _aum(r),
            "isin": r.get("isin") or "", "series": others,
        })
    funds.sort(key=lambda f: f["symbol"])
    detail = {"active_etfs": len(active),
              "dropped_leveraged": sorted(dropped_leveraged),
              "dropped_floor": dropped_floor,
              "collapsed_series": collapsed, "funds": len(funds)}
    return funds, detail


def company_ids(bulk_rows):
    """Return (symbol_to_company, isin_to_company, detail).

    Company id is the home-share ISIN. An ADR links to its home line: among
    the non-ADR, non-US-listed stock rows with the identical company name,
    ignoring the ADR's own ISIN (the ADR traded abroad) and US/CA ISINs
    (depositary receipts), the ISIN with the most listings. On a tie, or with
    no candidate, it keeps its own ISIN.
    """
    stocks = [r for r in bulk_rows
              if not _flag(r, "isEtf") and not _flag(r, "isFund")
              and (r.get("isin") or "").strip()]
    home = {}  # company name -> Counter of home-candidate ISINs
    for r in stocks:
        if (not _flag(r, "isAdr")
                and r.get("exchange") not in cfg.FUND_US_EXCHANGES
                and not r["isin"].startswith(("US", "CA"))):
            home.setdefault(r.get("companyName"), Counter())[r["isin"]] += 1

    sym, isin_map = {}, {}
    adrs, linked, unlinked = 0, 0, []
    for r in stocks:
        own = r["isin"]
        cid = own
        if _flag(r, "isAdr"):
            adrs += 1
            cands = [(i, n) for i, n in
                     home.get(r.get("companyName"), Counter()).most_common()
                     if i != own]
            if cands and (len(cands) == 1 or cands[0][1] > cands[1][1]):
                cid = cands[0][0]
                linked += 1
            else:
                unlinked.append(r["symbol"])
        sym[r["symbol"]] = cid
        isin_map[own] = cid
    return sym, isin_map, {"adrs": adrs, "adrs_linked": linked,
                           "unlinked": sorted(unlinked)}


def bucket_of(company_id, n=64):
    """Stable shard number for a company id."""
    return int(hashlib.md5(company_id.encode()).hexdigest(), 16) % n
