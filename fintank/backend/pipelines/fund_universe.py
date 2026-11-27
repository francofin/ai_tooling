"""Fund universe and company ids for the fund finder (pure, no network).

`build_universe` picks the ETFs worth indexing from FMP's bulk profile rows;
`company_ids` maps stock symbols/ISINs to one id per company so its
interlisted lines, share classes, dual listings and ADRs count once; `bucket_of` shards company ids.
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


_NORTH_AMERICAN_EXCHANGES = frozenset(cfg.FUND_US_EXCHANGES + cfg.FUND_CA_EXCHANGES)


def company_ids(bulk_rows, common_symbols=None):
    """Return (symbol_to_company, isin_to_company, detail).

    Every line of a company gets one id. Lines are grouped by company: each
    ISIN belongs to the companyName most of its listings carry (a tie or no
    name: it stays on its own, so one mislabelled row can't join two
    companies). An ISIN joins its company's group when
      * any listing is an ADR, or
      * it is not North American (ISIN not US/CA and no listing on a US/CA
        main exchange), or
      * one of its listings is in `common_symbols` (the US/Canadian index
        lists: common shares only, so preferreds and unknown OTC lines stay
        separate). Without index lists no North American line merges.
    Otherwise it keeps its own ISIN. The group's id is the member that is
    neither an ADR nor North American with the most listings (else any
    member with the most listings); ties go to the smallest ISIN.
    """
    common = set(common_symbols or ())
    stocks = [r for r in bulk_rows
              if not _flag(r, "isEtf") and not _flag(r, "isFund")
              and (r.get("isin") or "").strip()]
    lines = {}  # isin -> [rows]
    for r in stocks:
        lines.setdefault(r["isin"], []).append(r)

    def owner(isin):
        names = Counter((r.get("companyName") or "").strip() for r in lines[isin])
        names.pop("", None)
        top = names.most_common(2)
        if not top or (len(top) == 2 and top[0][1] == top[1][1]):
            return None
        return top[0][0]

    def is_adr(isin):
        return any(_flag(r, "isAdr") for r in lines[isin])

    def north_american(isin):
        return isin.startswith(("US", "CA")) or any(
            r.get("exchange") in _NORTH_AMERICAN_EXCHANGES for r in lines[isin])

    def eligible(isin):
        if is_adr(isin) or not north_american(isin):
            return True
        return any(r["symbol"] in common for r in lines[isin])

    groups = {}  # company name -> [isins]
    for isin in lines:
        name = owner(isin)
        if name is not None and eligible(isin):
            groups.setdefault(name, []).append(isin)

    def rank(isin):
        return (-len(lines[isin]), isin)

    isin_map = {isin: isin for isin in lines}
    merged = []
    for name, members in groups.items():
        home = [i for i in members if not is_adr(i) and not north_american(i)]
        canonical = min(home or members, key=rank)
        for i in members:
            isin_map[i] = canonical
        if len(members) > 1:
            merged.append({"name": name, "isins": sorted(members)})

    sym = {r["symbol"]: isin_map[r["isin"]] for r in stocks}
    adrs, linked, unlinked = 0, 0, []
    for r in stocks:
        if _flag(r, "isAdr"):
            adrs += 1
            if sym[r["symbol"]] != r["isin"]:
                linked += 1
            else:
                unlinked.append(r["symbol"])
    merged.sort(key=lambda g: (-len(g["isins"]), g["name"]))
    return sym, isin_map, {
        "adrs": adrs, "adrs_linked": linked, "unlinked": sorted(unlinked),
        "merged_groups": len(merged),
        "merged_isins": sum(len(g["isins"]) for g in merged),
        "largest_groups": merged[:10],
        "north_american_merge": bool(common)}


def bucket_of(company_id, n=64):
    """Stable shard number for a company id."""
    return int(hashlib.md5(company_id.encode()).hexdigest(), 16) % n
