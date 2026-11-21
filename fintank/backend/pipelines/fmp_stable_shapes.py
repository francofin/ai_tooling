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


def holdings_rows(stable_rows: list[dict]) -> list[dict]:
    """Stable etf/holdings rows -> v3 etf-holder rows.

    securityCusip -> cusip, updatedAt -> updated, `symbol` (the ETF) dropped,
    and rows without an `asset` (cash lines) dropped."""
    return [{
        "asset": r["asset"],
        "name": r.get("name"),
        "isin": r.get("isin"),
        "cusip": r.get("securityCusip"),
        "sharesNumber": r.get("sharesNumber"),
        "weightPercentage": r.get("weightPercentage"),
        "marketValue": r.get("marketValue"),
        "updated": r.get("updatedAt"),
    } for r in stable_rows if r.get("asset")]


def _price(v):
    return float(v) if v not in (None, "") else None


def etf_list_rows(etf_list: list[dict], bulk_rows: list[dict],
                  exchange_filter: list[str]) -> list[dict]:
    """Stable etf-list ({symbol, name}) joined to profile-bulk CSV rows for the
    v3 etf/list shape. Keeps symbols present in both whose exchangeFullName is
    in `exchange_filter`; exchangeFullName -> exchange, exchange ->
    exchangeShortName, price parsed to float (empty -> None)."""
    by_symbol = {r["symbol"]: r for r in bulk_rows}
    out = []
    for e in etf_list:
        b = by_symbol.get(e.get("symbol"))
        if b is None or b.get("exchangeFullName") not in exchange_filter:
            continue
        out.append({
            "symbol": e["symbol"],
            "name": e.get("name"),
            "price": _price(b.get("price")),
            "exchange": b["exchangeFullName"],
            "exchangeShortName": b.get("exchange"),
            "type": "etf",
        })
    return out


# v3 field -> stable field that holds the same concept (None: no stable
# equivalent, the v3 key is emitted as None). Applies per statement kind, on
# top of the common filingDate/fiscalYear renames below.
_COMMON_RENAMES = {"fillingDate": "filingDate", "calendarYear": "fiscalYear"}
STATEMENT_RENAMES = {
    "income": {**_COMMON_RENAMES, "epsdiluted": "epsDiluted",
               "link": None, "finalLink": None},
    "balance": {**_COMMON_RENAMES,
                "othertotalStockholdersEquity": "otherTotalStockholdersEquity",
                "totalLiabilitiesAndStockholdersEquity": "totalLiabilitiesAndTotalEquity",
                "link": None, "finalLink": None},
    "cashflow": {**_COMMON_RENAMES,
                 "commonStockIssued": "commonStockIssuance",
                 "debtRepayment": "netDebtIssuance",
                 "dividendsPaid": "netDividendsPaid",
                 "netCashUsedForInvestingActivites": "netCashProvidedByInvestingActivities",
                 "netCashUsedProvidedByFinancingActivities": "netCashProvidedByFinancingActivities",
                 "otherFinancingActivites": "otherFinancingActivities",
                 "otherInvestingActivites": "otherInvestingActivities",
                 "link": None, "finalLink": None},
}

_MAPPED_SOURCES = {"totalLiabilitiesAndTotalEquity"}

# v3 ratio field -> the income field it divides by revenue.
_INCOME_RATIOS = {
    "grossProfitRatio": "grossProfit",
    "ebitdaratio": "ebitda",
    "operatingIncomeRatio": "operatingIncome",
    "incomeBeforeTaxRatio": "incomeBeforeTax",
    "netIncomeRatio": "netIncome",
}


def statement_rows(kind: str, rows: list) -> list:
    """Stable statement rows -> v3-shaped rows (FIELD_MAPPINGS keys all present).

    Stable keys are kept; renamed ones move to the v3 spelling (the stable
    spelling is dropped so a row never carries both). calendarYear stays a
    str as in v3. Income ratios are derived (part / revenue, None when revenue
    is 0 or None); link/finalLink are None."""
    renames = STATEMENT_RENAMES[kind]
    # totalLiabilitiesAndTotalEquity is itself a mapped v3 column (v3 carried
    # it alongside totalLiabilitiesAndStockholdersEquity), so it stays.
    sources = {s for s in renames.values() if s} - _MAPPED_SOURCES
    out = []
    for r in rows:
        row = {k: v for k, v in r.items() if k not in sources}
        for v3_key, src in renames.items():
            row[v3_key] = r.get(src) if src else None
        if row["calendarYear"] is not None:
            row["calendarYear"] = str(row["calendarYear"])
        if kind == "income":
            revenue = r.get("revenue")
            for ratio, part in _INCOME_RATIOS.items():
                num = r.get(part)
                row[ratio] = (num / revenue if revenue and num is not None
                              else None)
        out.append(row)
    return out
