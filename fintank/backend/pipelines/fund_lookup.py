"""Turn raw ETF holdings into the fund-finder lookup (pure, no network).

`build_lookup` resolves each holding row to a company id, expands funds held
by funds one level, and returns (exposure, funds_df, isin_map, detail).
"""
from collections import Counter

import pandas as pd

from . import pipeline_config as cfg
from .fund_universe import bucket_of
from .thresholds import (FUND_BUCKETS, FUND_LEVERAGE_COVERAGE_PCT,
                         FUND_MIN_HOLDING_PCT, FUND_WEIGHT_SUM_RANGE)

EXPOSURE_COLS = ["company_id", "fund", "weight", "via", "bucket"]
FUND_COLS = ["symbol", "name", "exchange", "region", "currency", "aum", "mer",
             "issuer", "asset_class", "fetched", "series", "rows",
             "coverage_pct"]
ISIN_COLS = ["symbol", "company_id", "name", "exchange", "is_adr"]


def _w(row):
    try:
        v = float(row.get("weightPercentage") or 0)
    except (TypeError, ValueError):
        return 0.0
    return v if v == v else 0.0


def _fetched(rows):
    days = [str(r["updatedAt"])[:10] for r in rows if r.get("updatedAt")]
    return Counter(days).most_common(1)[0][0] if days else None


def _top10_only(rows, info):
    """FMP's top 10 rescaled to 100% instead of the full portfolio."""
    if len(rows) != cfg.FUND_TOP10_ROWS or (info or {}).get("holdings_count"):
        return False
    return abs(sum(_w(r) for r in rows) - 100.0) <= cfg.FUND_TOP10_SUM_TOLERANCE


def _clean(holdings):
    """Rows whose asset is a string or absent (an ISIN-only row); returns
    (holdings, number of rows dropped for a non-string asset)."""
    bad = 0
    out = {}
    for fund, rows in holdings.items():
        keep = []
        for r in rows or []:
            if not isinstance(r, dict):
                bad += 1
            elif r.get("asset") is None or isinstance(r.get("asset"), str):
                keep.append(r)
            else:
                bad += 1
        out[fund] = keep
    return out, bad


def build_lookup(holdings, funds, symbol_to_company, isin_to_company,
                 fund_info, *, listings=None):
    holdings, bad_assets = _clean(holdings)
    def resolve(r):
        isin = (r.get("isin") or "").strip()
        return (isin_to_company.get(isin) if isin else None) \
            or symbol_to_company.get(r.get("asset") or "")

    universe = {f["symbol"] for f in funds}
    agg = {}  # (company_id, fund, via) -> weight
    stats = {}
    deep, unexpanded, outside = [], [], []
    lo, hi = FUND_WEIGHT_SUM_RANGE

    def add(cid, fund, via, w):
        k = (cid, fund, via)
        agg[k] = agg.get(k, 0.0) + w

    for f in funds:
        sym = f["symbol"]
        rows = holdings.get(sym) or []
        raw = sum(_w(r) for r in rows)
        resolved = 0.0
        is_deep = False
        for r in rows:
            asset = r.get("asset") or ""
            w = _w(r)
            if asset and asset != sym and asset in holdings:
                got = 0.0
                for ir in holdings[asset]:
                    ia = ir.get("asset") or ""
                    if ia and ia != asset and ia in holdings:
                        is_deep = True
                        continue
                    cid = resolve(ir)
                    if cid:
                        iw = _w(ir)
                        got += iw
                        add(cid, sym, asset, w / 100.0 * iw)
                resolved += w / 100.0 * got
                continue
            if asset and asset in universe and asset != sym:
                unexpanded.append(sym)
            cid = resolve(r)
            if cid:
                resolved += w
                add(cid, sym, "", w)
        if is_deep:
            deep.append(sym)
        if rows and not lo <= raw <= hi:
            outside.append(sym)
        stats[sym] = {"fetched": _fetched(rows),
                      "coverage": round(resolved / raw * 100, 2) if raw > 0 and resolved > 0 else 0}

    # Holdings worth more than the fund (a leveraged line the name filter
    # missed) would top every ranking: drop the fund from the lookup.
    levered = sorted(s for s, st in stats.items()
                     if st["coverage"] > FUND_LEVERAGE_COVERAGE_PCT)
    top10 = sorted(f["symbol"] for f in funds if f["symbol"] not in levered
                   and _top10_only(holdings.get(f["symbol"]) or [],
                                   fund_info.get(f["symbol"])))
    drop = set(levered) | set(top10)
    recs = [(c, fd, w, via, bucket_of(c, FUND_BUCKETS))
            for (c, fd, via), w in agg.items()
            if w >= FUND_MIN_HOLDING_PCT and fd not in drop]
    exposure = pd.DataFrame(recs, columns=EXPOSURE_COLS).astype(
        {"company_id": "object", "fund": "object", "weight": "float64",
         "via": "object", "bucket": "int64"})
    counts = exposure.fund.value_counts().to_dict()

    frecs = []
    for f in funds:
        if f["symbol"] in drop:
            continue
        i = fund_info.get(f["symbol"]) or {}
        frecs.append({
            "symbol": f["symbol"], "name": f["name"], "exchange": f["exchange"],
            "region": f["region"], "currency": f["currency"], "aum": f["aum"],
            "mer": i.get("mer"), "issuer": i.get("issuer"),
            "asset_class": i.get("asset_class"),
            "fetched": stats[f["symbol"]]["fetched"],
            "series": list(f.get("series") or []),
            "rows": int(counts.get(f["symbol"], 0)),
            "coverage_pct": stats[f["symbol"]]["coverage"]})
    funds_df = pd.DataFrame(frecs, columns=FUND_COLS)
    # Saved in funds.parquet's pandas metadata; Django shows it as a footnote.
    funds_df.attrs["dropped_top10_only"] = len(top10)

    present = set(exposure.company_id)
    lst = listings or {}
    irecs = []
    for s, cid in symbol_to_company.items():
        if cid in present:
            m = lst.get(s) or {}
            irecs.append({"symbol": s, "company_id": cid,
                          "name": m.get("name"), "exchange": m.get("exchange"),
                          "is_adr": bool(m.get("is_adr", False))})
    isin_map = pd.DataFrame(irecs, columns=ISIN_COLS)

    xeqt = sum(1 for r in holdings.get("XEQT.TO", []) if r.get("asset"))
    detail = {"funds": len(funds),
              "funds_with_rows": int((funds_df.rows > 0).sum()),
              "rows": len(exposure), "weight_sum_outside": sorted(outside),
              "unexpanded": sorted(set(unexpanded)),
              "deep_chains": sorted(deep), "xeqt_asset_rows": xeqt,
              "dropped_leveraged_holdings": levered,
              "dropped_top10_only": len(top10), "dropped_top10_only_symbols": top10,
              "bad_asset_rows": bad_assets}
    return exposure, funds_df, isin_map, detail
