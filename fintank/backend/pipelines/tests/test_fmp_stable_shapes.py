import csv
import io

import pytest

from pipelines import pipeline_config as cfg
from pipelines.fmp_stable_shapes import (etf_list_rows, holdings_rows,
                                         index_payload, price_payload,
                                         statement_rows, ttm_rows, v3_label)

from .helpers import load_fixture


def test_v3_label_format():
    assert v3_label("2026-11-13") == "November 13, 26"


def test_v3_label_zero_pads_day():
    assert v3_label("2026-11-05") == "November 05, 26"


def test_price_payload_shape():
    full = load_fixture("px_full_aapl")
    adj = load_fixture("px_divadj_aapl")
    out = price_payload("AAPL", full, adj)
    assert out["symbol"] == "AAPL"
    hist = out["historical"]
    assert hist[0]["date"] == full[0]["date"]
    dates = [r["date"] for r in hist]
    assert dates == sorted(dates, reverse=True)
    adj_by_date = {r["date"]: r["adjClose"] for r in adj}
    need = {"date", "open", "high", "low", "close", "adjClose", "volume", "label"}
    for r in hist:
        assert need <= set(r)
        assert r["adjClose"] == adj_by_date[r["date"]]
        assert isinstance(r["volume"], int)
        assert not {"symbol", "adjOpen", "adjHigh", "adjLow"} & set(r)
    assert hist[0]["change"] == full[0]["change"]
    assert hist[0]["vwap"] == full[0]["vwap"]
    assert hist[0]["label"] == v3_label(hist[0]["date"])


def test_price_payload_joins_on_date_only():
    full = load_fixture("px_full_aapl")
    adj = load_fixture("px_divadj_aapl")
    missing = full[0]["date"]
    extra = dict(adj[1], date="2001-01-01")
    out = price_payload("AAPL", full, [r for r in adj if r["date"] != missing] + [extra])
    assert out["historical"][0]["adjClose"] is None
    assert "2001-01-01" not in [r["date"] for r in out["historical"]]
    assert len(out["historical"]) == len(full)


def test_index_payload_copies_close():
    full = load_fixture("idx_full_gsptse")
    out = index_payload("^GSPTSE", full)
    assert out["symbol"] == "^GSPTSE"
    hist = out["historical"]
    assert len(hist) == len(full)
    assert hist[0]["date"] == full[0]["date"]
    for r in hist:
        assert r["adjClose"] == r["close"]
        assert "symbol" not in r


HOLDING_KEYS = {"asset", "name", "isin", "cusip", "sharesNumber",
                "weightPercentage", "marketValue", "updated"}


def test_holdings_rows_drop_symbol_and_cash_lines():
    raw = load_fixture("etf_holdings_spy") + [{"symbol": "SPY", "asset": ""}]
    kept = [r for r in raw if r.get("asset")]
    assert len(kept) < len(raw)
    out = holdings_rows(raw)
    assert len(out) == len(kept)
    for r in out:
        assert set(r) == HOLDING_KEYS
        assert "symbol" not in r
    first, src = out[0], kept[0]
    assert first["cusip"] == src["securityCusip"]
    assert first["updated"] == src["updatedAt"]


def test_holdings_weight_is_float():
    for r in holdings_rows(load_fixture("etf_holdings_spy")):
        assert isinstance(r["weightPercentage"], float)


def _bulk():
    return list(csv.DictReader(io.StringIO(load_fixture("profile_bulk_part0", "csv"))))


def test_etf_list_rows_join_exchange():
    bulk = _bulk()
    # the captured etf-list sample and bulk sample share no symbols, so key the
    # list rows onto the bulk ETF symbols
    syms = [r["symbol"] for r in bulk if r["isEtf"] == "true"]
    etf_list = [{"symbol": s, "name": f"N {s}"} for s in syms]
    etf_list.append({"symbol": "NOT_IN_BULK", "name": "x"})
    out = etf_list_rows(etf_list, bulk, cfg.ETF_EXCHANGE_FILTER)
    assert out
    for r in out:
        assert set(r) == {"symbol", "name", "price", "exchange",
                          "exchangeShortName", "type"}
        assert r["exchange"] in cfg.ETF_EXCHANGE_FILTER
        assert r["type"] == "etf"
        assert r["price"] is None or isinstance(r["price"], float)
    got = {r["symbol"]: r for r in out}
    assert "NOT_IN_BULK" not in got and "2B7S.DE" not in got   # XETRA filtered
    sgov = got["SGOV"]
    assert sgov["name"] == "N SGOV" and sgov["price"] == float(
        next(b["price"] for b in bulk if b["symbol"] == "SGOV"))
    assert sgov["exchangeShortName"] == next(
        b["exchange"] for b in bulk if b["symbol"] == "SGOV")


def test_etf_list_rows_empty_price_is_none():
    bulk = [{"symbol": "A", "price": "", "exchangeFullName": "NASDAQ",
             "exchange": "NASDAQ"}]
    out = etf_list_rows([{"symbol": "A", "name": "a"}], bulk, ["NASDAQ"])
    assert out[0]["price"] is None


_STATEMENTS = [("income", "income_q_aapl", "income_statements"),
               ("balance", "balance_q_aapl", "balance_sheet_statements"),
               ("cashflow", "cashflow_q_aapl", "cash_flow_statements")]


@pytest.mark.parametrize("kind,fixture,mapping", _STATEMENTS)
def test_statement_rows_cover_field_mappings(kind, fixture, mapping):
    raw = load_fixture(fixture)
    out = statement_rows(kind, raw)
    assert len(out) == len(raw)
    for row in out:
        assert set(cfg.FIELD_MAPPINGS[mapping]) <= set(row)


@pytest.mark.parametrize("kind,fixture,mapping", _STATEMENTS)
def test_statement_rows_never_carry_both_spellings(kind, fixture, mapping):
    for row in statement_rows(kind, load_fixture(fixture)):
        assert not {"filingDate", "fiscalYear", "epsDiluted"} & set(row)


def test_income_ratios_derived():
    raw = load_fixture("income_q_aapl")
    row = statement_rows("income", raw)[0]
    r = raw[0]
    assert row["grossProfitRatio"] == pytest.approx(r["grossProfit"] / r["revenue"])
    assert row["ebitdaratio"] == pytest.approx(r["ebitda"] / r["revenue"])
    assert row["operatingIncomeRatio"] == pytest.approx(r["operatingIncome"] / r["revenue"])
    assert row["incomeBeforeTaxRatio"] == pytest.approx(r["incomeBeforeTax"] / r["revenue"])
    assert row["netIncomeRatio"] == pytest.approx(r["netIncome"] / r["revenue"])
    assert row["epsdiluted"] == r["epsDiluted"]
    assert row["fillingDate"] == r["filingDate"]
    assert row["link"] is None and row["finalLink"] is None


_RATIO_KEYS = ("grossProfitRatio", "ebitdaratio", "operatingIncomeRatio",
               "incomeBeforeTaxRatio", "netIncomeRatio")


@pytest.mark.parametrize("revenue", [0, None])
def test_income_ratios_none_when_revenue_zero(revenue):
    raw = [dict(load_fixture("income_q_aapl")[0], revenue=revenue)]
    row = statement_rows("income", raw)[0]
    for k in _RATIO_KEYS:
        assert row[k] is None


def test_income_ratios_zero_when_revenue_and_parts_zero():
    # v3 wrote 0.0 here (live rows, e.g. a pre-revenue miner).
    zero = dict(revenue=0, grossProfit=0, ebitda=0, operatingIncome=0,
                incomeBeforeTax=0, netIncome=0)
    row = statement_rows("income", [dict(load_fixture("income_q_aapl")[0], **zero)])[0]
    for k in _RATIO_KEYS:
        assert row[k] == 0.0 and isinstance(row[k], float)


@pytest.mark.parametrize("kind,fixture,mapping", _STATEMENTS)
def test_calendar_year_keeps_v3_type(kind, fixture, mapping):
    raw = load_fixture(fixture)
    row = statement_rows(kind, raw)[0]
    assert type(row["calendarYear"]) is str
    assert row["calendarYear"] == str(raw[0]["fiscalYear"])


def test_balance_and_cashflow_renames_carry_values():
    b = load_fixture("balance_q_aapl")[0]
    row = statement_rows("balance", [b])[0]
    assert row["othertotalStockholdersEquity"] == b["otherTotalStockholdersEquity"]
    assert row["totalLiabilitiesAndStockholdersEquity"] == b["totalLiabilitiesAndTotalEquity"]
    c = load_fixture("cashflow_q_aapl")[0]
    row = statement_rows("cashflow", [c])[0]
    assert row["debtRepayment"] == c["netDebtIssuance"]
    assert row["dividendsPaid"] == c["netDividendsPaid"]
    assert row["otherInvestingActivites"] == c["otherInvestingActivities"]


def test_debt_repayment_sign_convention_pinned():
    # Approximation: debtRepayment is stable's net debt issuance (see
    # STATEMENT_RENAMES); AAPL's first fixture quarter is a net repayment.
    c = load_fixture("cashflow_q_aapl")[0]
    row = statement_rows("cashflow", [c])[0]
    assert row["debtRepayment"] == c["netDebtIssuance"]
    assert row["debtRepayment"] < 0


def _ttm():
    return ttm_rows(load_fixture("ratios_ttm_aapl")[0],
                    load_fixture("key_metrics_ttm_aapl")[0])


def test_ttm_rows_cover_field_mappings():
    ratios, metrics = _ttm()
    assert len(cfg.FIELD_MAPPINGS["company_ratios_ttm"]) == 58
    assert len(cfg.FIELD_MAPPINGS["company_metrics_ttm"]) == 61
    assert set(cfg.FIELD_MAPPINGS["company_ratios_ttm"]) <= set(ratios)
    assert set(cfg.FIELD_MAPPINGS["company_metrics_ttm"]) <= set(metrics)
    assert ratios["symbol"] == "AAPL" and metrics["symbol"] == "AAPL"
    # every key the sources table maps resolved to a real value on the fixture
    assert all(ratios[k] is not None for k in ratios if k != "symbol")


def test_ttm_scale_100():
    ratios, metrics = _ttm()
    r = load_fixture("ratios_ttm_aapl")[0]["dividendYieldTTM"]
    assert ratios["dividendYielTTM"] == r
    assert ratios["dividendYielPercentageTTM"] == 100 * r
    assert metrics["dividendYieldPercentageTTM"] == 100 * r


def test_ttm_scale_100_keeps_none():
    r = load_fixture("ratios_ttm_aapl")[0]
    r["dividendYieldTTM"] = None
    ratios, metrics = ttm_rows(r, load_fixture("key_metrics_ttm_aapl")[0])
    assert ratios["dividendYielPercentageTTM"] is None
    assert metrics["dividendYieldPercentageTTM"] is None


def test_ttm_ebit_per_revenue_is_operating_margin():
    ratios, _ = _ttm()
    assert ratios["ebitPerRevenueTTM"] == load_fixture("ratios_ttm_aapl")[0]["operatingProfitMarginTTM"]


def test_ttm_whole_numbers_become_floats():
    r = load_fixture("ratios_ttm_aapl")[0]
    r["priceToEarningsRatioTTM"] = 0
    ratios, metrics = ttm_rows(r, load_fixture("key_metrics_ttm_aapl")[0])
    assert ratios["peRatioTTM"] == 0.0 and isinstance(ratios["peRatioTTM"], float)
    assert isinstance(metrics["peRatioTTM"], float)


def test_ttm_cross_endpoint():
    ratios, metrics = _ttm()
    m = load_fixture("key_metrics_ttm_aapl")[0]
    assert ratios["returnOnEquityTTM"] == m["returnOnEquityTTM"]
    assert metrics["roeTTM"] == m["returnOnEquityTTM"]
    assert metrics["marketCapTTM"] == m["marketCap"]


def test_ttm_same_name_other_endpoint_fallback():
    r = load_fixture("ratios_ttm_aapl")[0]
    m = load_fixture("key_metrics_ttm_aapl")[0]
    del m["currentRatioTTM"]
    _, metrics = ttm_rows(r, m)
    assert metrics["currentRatioTTM"] == r["currentRatioTTM"]


def test_sector_snapshot_averages_exchanges():
    from pipelines.fmp_stable_shapes import sector_snapshot_rows
    nyse = load_fixture("sector_snapshot_nyse")
    nasdaq = load_fixture("sector_snapshot_nasdaq")
    rows = sector_snapshot_rows([nyse, nasdaq])
    assert len(rows) == 11
    assert all(set(r) == {"sector", "changesPercentage"} for r in rows)
    assert all(r["changesPercentage"].endswith("%") for r in rows)
    sector = nyse[0]["sector"]
    other = next(r for r in nasdaq if r["sector"] == sector)
    mean = (nyse[0]["averageChange"] + other["averageChange"]) / 2
    got = next(r for r in rows if r["sector"] == sector)
    assert got["changesPercentage"] == f"{mean:.2f}%"
    assert [r["sector"] for r in rows][0] == sector


def test_sector_snapshot_single_exchange_sector_kept():
    from pipelines.fmp_stable_shapes import sector_snapshot_rows
    nyse = load_fixture("sector_snapshot_nyse")
    rows = sector_snapshot_rows([nyse, []])
    assert len(rows) == 11
    assert rows[0]["changesPercentage"] == f"{nyse[0]['averageChange']:.2f}%"
    assert sector_snapshot_rows([[], []]) == []
