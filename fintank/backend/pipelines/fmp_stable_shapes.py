"""Reshape FMP `stable` responses into the v3 row shapes the pipeline expects.

Pure functions: no I/O, no pandas, no Django.
"""
from datetime import date

from pipelines import pipeline_config as cfg

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
                 # APPROXIMATION: stable has no repayments-only field. netDebtIssuance
                 # is issuance minus repayment, so it can be positive in a quarter
                 # with net borrowing, unlike v3's repayment-only value. The Task 8
                 # live comparison against v3-era S3 values decides if this stands.
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
    is None; 0.0 when revenue and the part are both 0); link/finalLink are None."""
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
                if num is None or revenue is None:
                    row[ratio] = None
                elif revenue == 0:
                    # v3 wrote 0.0 for an all-zero row (66 live rows, Task 8); a
                    # non-zero part over zero revenue is undefined, so None.
                    row[ratio] = 0.0 if num == 0 else None
                else:
                    row[ratio] = num / revenue
        out.append(row)
    return out


# v3 TTM field -> (endpoint, stable field, scale). Endpoint "R" is stable
# ratios-ttm, "M" is key-metrics-ttm. Fields that kept their v3 name are not
# listed: ttm_rows copies them. Initial tables, to be checked against live
# values in Task 8.
RATIOS_TTM_SOURCES = {
    "cashConversionCycleTTM": ("M", "cashConversionCycleTTM", 1),
    "cashFlowCoverageRatiosTTM": ("R", "operatingCashFlowCoverageRatioTTM", 1),
    "cashFlowToDebtRatioTTM": ("R", "operatingCashFlowCoverageRatioTTM", 1),
    "companyEquityMultiplierTTM": ("R", "financialLeverageRatioTTM", 1),
    "daysOfInventoryOutstandingTTM": ("M", "daysOfInventoryOutstandingTTM", 1),
    "daysOfPayablesOutstandingTTM": ("M", "daysOfPayablesOutstandingTTM", 1),
    "daysOfSalesOutstandingTTM": ("M", "daysOfSalesOutstandingTTM", 1),
    "debtEquityRatioTTM": ("R", "debtToEquityRatioTTM", 1),
    "debtRatioTTM": ("R", "debtToAssetsRatioTTM", 1),
    "dividendYielPercentageTTM": ("R", "dividendYieldTTM", 100),
    "dividendYielTTM": ("R", "dividendYieldTTM", 1),
    # Task 8: v3 ebitPerRevenue is the operating margin (95% of 40 symbols within
    # 1%; ebitMarginTTM matched 8 of 40).
    "ebitPerRevenueTTM": ("R", "operatingProfitMarginTTM", 1),
    "interestCoverageTTM": ("R", "interestCoverageRatioTTM", 1),
    "longTermDebtToCapitalizationTTM": ("R", "longTermDebtToCapitalRatioTTM", 1),
    "operatingCycleTTM": ("M", "operatingCycleTTM", 1),
    "payoutRatioTTM": ("R", "dividendPayoutRatioTTM", 1),
    "peRatioTTM": ("R", "priceToEarningsRatioTTM", 1),
    "pegRatioTTM": ("R", "priceToEarningsGrowthRatioTTM", 1),
    "priceBookValueRatioTTM": ("R", "priceToBookRatioTTM", 1),
    "priceCashFlowRatioTTM": ("R", "priceToOperatingCashFlowRatioTTM", 1),
    "priceEarningsRatioTTM": ("R", "priceToEarningsRatioTTM", 1),
    "priceEarningsToGrowthRatioTTM": ("R", "priceToEarningsGrowthRatioTTM", 1),
    "priceFairValueTTM": ("R", "priceToFairValueTTM", 1),
    "priceSalesRatioTTM": ("R", "priceToSalesRatioTTM", 1),
    "priceToFreeCashFlowsRatioTTM": ("R", "priceToFreeCashFlowRatioTTM", 1),
    "priceToOperatingCashFlowsRatioTTM": ("R", "priceToOperatingCashFlowRatioTTM", 1),
    "returnOnAssetsTTM": ("M", "returnOnAssetsTTM", 1),
    "returnOnCapitalEmployedTTM": ("M", "returnOnCapitalEmployedTTM", 1),
    "returnOnEquityTTM": ("M", "returnOnEquityTTM", 1),
    "shortTermCoverageRatiosTTM": ("R", "shortTermOperatingCashFlowCoverageRatioTTM", 1),
    "totalDebtToCapitalizationTTM": ("R", "debtToCapitalRatioTTM", 1),
}

METRICS_TTM_SOURCES = {
    "bookValuePerShareTTM": ("R", "bookValuePerShareTTM", 1),
    "capexPerShareTTM": ("R", "capexPerShareTTM", 1),
    "cashPerShareTTM": ("R", "cashPerShareTTM", 1),
    "daysOfInventoryOnHandTTM": ("M", "daysOfInventoryOutstandingTTM", 1),
    "daysPayablesOutstandingTTM": ("M", "daysOfPayablesOutstandingTTM", 1),
    "daysSalesOutstandingTTM": ("M", "daysOfSalesOutstandingTTM", 1),
    "debtToAssetsTTM": ("R", "debtToAssetsRatioTTM", 1),
    "debtToEquityTTM": ("R", "debtToEquityRatioTTM", 1),
    "debtToMarketCapTTM": ("R", "debtToMarketCapTTM", 1),
    "dividendPerShareTTM": ("R", "dividendPerShareTTM", 1),
    "dividendYieldPercentageTTM": ("R", "dividendYieldTTM", 100),
    "dividendYieldTTM": ("R", "dividendYieldTTM", 1),
    "enterpriseValueOverEBITDATTM": ("M", "evToEBITDATTM", 1),
    "freeCashFlowPerShareTTM": ("R", "freeCashFlowPerShareTTM", 1),
    "interestCoverageTTM": ("R", "interestCoverageRatioTTM", 1),
    "interestDebtPerShareTTM": ("R", "interestDebtPerShareTTM", 1),
    "inventoryTurnoverTTM": ("R", "inventoryTurnoverTTM", 1),
    "marketCapTTM": ("M", "marketCap", 1),
    "netIncomePerShareTTM": ("R", "netIncomePerShareTTM", 1),
    "operatingCashFlowPerShareTTM": ("R", "operatingCashFlowPerShareTTM", 1),
    "payablesTurnoverTTM": ("R", "payablesTurnoverTTM", 1),
    "payoutRatioTTM": ("R", "dividendPayoutRatioTTM", 1),
    "pbRatioTTM": ("R", "priceToBookRatioTTM", 1),
    "peRatioTTM": ("R", "priceToEarningsRatioTTM", 1),
    "pfcfRatioTTM": ("R", "priceToFreeCashFlowRatioTTM", 1),
    "pocfratioTTM": ("R", "priceToOperatingCashFlowRatioTTM", 1),
    "priceToSalesRatioTTM": ("R", "priceToSalesRatioTTM", 1),
    "ptbRatioTTM": ("R", "priceToBookRatioTTM", 1),
    "receivablesTurnoverTTM": ("R", "receivablesTurnoverTTM", 1),
    "revenuePerShareTTM": ("R", "revenuePerShareTTM", 1),
    "roeTTM": ("M", "returnOnEquityTTM", 1),
    "roicTTM": ("M", "returnOnInvestedCapitalTTM", 1),
    "shareholdersEquityPerShareTTM": ("R", "shareholdersEquityPerShareTTM", 1),
    "tangibleBookValuePerShareTTM": ("R", "tangibleBookValuePerShareTTM", 1),
}


def _ttm_row(mapping, sources, own, other, both):
    row = {}
    for key in mapping:
        if key in sources:
            endpoint, field, scale = sources[key]
            value = both[endpoint].get(field)
            row[key] = value * scale if value is not None and scale != 1 else value
        elif key in own:
            row[key] = own[key]
        else:
            row[key] = other.get(key)
    # v3 TTM values are floats; stable sends a whole 0 as an int, which pandas
    # would store as int64 where the live column is float64.
    return {k: float(v) if isinstance(v, int) and not isinstance(v, bool) else v
            for k, v in row.items()}


def ttm_rows(ratios: dict, metrics: dict) -> tuple:
    """Stable ratios-ttm + key-metrics-ttm rows -> (v3 ratios row, v3 metrics row).

    Every FIELD_MAPPINGS['company_ratios_ttm'] / ['company_metrics_ttm'] key is
    present (None when unsourced). Sourced renames come from RATIOS_TTM_SOURCES /
    METRICS_TTM_SOURCES (scale 100 only when the value is not None); other keys
    are copied by name from the row's own endpoint, falling back to the other
    endpoint when absent there."""
    both = {"R": ratios, "M": metrics}
    return (_ttm_row(cfg.FIELD_MAPPINGS["company_ratios_ttm"], RATIOS_TTM_SOURCES,
                     ratios, metrics, both),
            _ttm_row(cfg.FIELD_MAPPINGS["company_metrics_ttm"], METRICS_TTM_SOURCES,
                     metrics, ratios, both))


def sector_snapshot_rows(rows_by_exchange: list) -> list:
    """Stable sector-performance-snapshot rows (one list per exchange) ->
    [{"sector", "changesPercentage": "x.xx%"}]: the mean averageChange per
    sector across the exchanges that report it, in first-seen sector order."""
    totals: dict = {}
    for rows in rows_by_exchange:
        for r in rows:
            totals.setdefault(r["sector"], []).append(float(r["averageChange"]))
    return [{"sector": s, "changesPercentage": f"{sum(v) / len(v):.2f}%"}
            for s, v in totals.items()]
