"""Pure shaping helpers for the stock-page analyst view (no Django/cache/network)."""
from datetime import date

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
    if consensus is None or (summary or {}).get("lastYearCount", 0) < MIN_TARGET_COUNT:
        return None
    vals = {out: consensus.get(src) for out, src in _TARGET_KEYS}
    cad = None
    if from_us and usdcad is not None:
        cad = {k: (v * usdcad if v is not None else None) for k, v in vals.items()}
    return {**vals, "count_last_year": summary["lastYearCount"],
            "currency": "USD" if from_us else None, "cad": cad}


def build_payload(symbol, *, estimates_annual, ratings, target, source, reporting_currency):
    if not estimates_annual and ratings is None and target is None:
        raise KeyError(symbol)
    return {"symbol": symbol, "estimates": {"annual": estimates_annual},
            "ratings": ratings, "target": target, "source": source,
            "reporting_currency": reporting_currency}
