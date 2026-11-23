import csv
import io

import pytest

from pipelines.fund_lookup import build_lookup
from pipelines.fund_universe import build_universe, company_ids

from .helpers import load_fixture

RY = "CA7800871021"


def bulk():
    return list(csv.DictReader(io.StringIO(load_fixture("profile_bulk_funds", "csv"))))


def listings_of(rows):
    return {r["symbol"]: {"name": r["companyName"], "exchange": r["exchange"],
                          "is_adr": str(r["isAdr"]).lower() == "true"}
            for r in rows}


def run(holdings, fund_symbols=None, info=None):
    rows = bulk()
    funds, _ = build_universe(rows)
    sym, isin, _ = company_ids(rows)
    if fund_symbols is not None:
        have = {f["symbol"] for f in funds}
        funds = [f for f in funds if f["symbol"] in fund_symbols] + [
            {"symbol": s, "name": s, "exchange": "TSX", "region": "ca",
             "currency": "CAD", "aum": 1.0, "isin": "", "series": []}
            for s in fund_symbols if s not in have]
    return build_lookup(holdings, funds, sym, isin, info or {},
                        listings=listings_of(rows))


def fx(n):
    return load_fixture(f"etf_holdings_{n}")


def row(asset, w, isin="", at="2026-11-22 10:00:00"):
    return {"asset": asset, "isin": isin, "weightPercentage": w, "updatedAt": at}


def test_direct_rows_resolve_by_isin():
    exp, *_ = run({"XIU.TO": fx("xiu")})
    r = exp[(exp.company_id == RY) & (exp.fund == "XIU.TO")]
    assert len(r) == 1
    assert r.iloc[0].weight == pytest.approx(9.42991875)
    assert r.iloc[0].via == ""


def test_symbol_fallback_when_no_isin():
    exp, *_ = run({"XIU.TO": [row("RY.TO", 5.0)]})
    assert exp.iloc[0].company_id == RY


def test_tiny_rows_dropped():
    apple = "US0378331005"
    # A company held nowhere else in VEA: kept at 0.01, dropped at 0.0005.
    kept, *_ = run({"VEA": fx("vea") + [row("AAPL", 0.01, isin=apple)]})
    assert (kept.company_id == apple).sum() == 1
    exp, *_ = run({"VEA": fx("vea") + [row("AAPL", 0.0005, isin=apple)]})
    assert not (exp.company_id == apple).any()
    assert (exp.weight >= 0.001).all()


def test_look_through_expands_one_level():
    h = {"XIU.TO": fx("xiu"), "VEA": fx("vea"),
         "MIX.TO": [row("XIU.TO", 50), row("VEA", 50)]}
    exp, funds_df, _, detail = run(h, {"MIX.TO"})
    r = exp[(exp.company_id == RY) & (exp.fund == "MIX.TO")].sort_values("via")
    assert list(r.via) == ["VEA", "XIU.TO"]
    assert sum(r.weight) == pytest.approx(0.5 * 9.42991875 + 0.5 * 0.89248737)
    assert detail["unexpanded"] == []


def test_look_through_deep_chain_logged():
    h = {"XIU.TO": fx("xiu"), "MIX.TO": [row("XIU.TO", 100)],
         "TOP.TO": [row("MIX.TO", 100)]}
    exp, _, _, detail = run(h, {"TOP.TO"})
    assert detail["deep_chains"] == ["TOP.TO"]
    assert exp.empty or (exp.via != "MIX.TO").all()


def test_xeqt_comes_looked_through():
    exp, _, _, detail = run({"XEQT.TO": fx("xeqt")})
    assert len(exp) > 0
    assert (exp.via == "").all()
    assert detail["xeqt_asset_rows"] == 40


def test_coverage_and_weight_sum():
    agg = fx("agg")
    exp, funds_df, _, detail = run({"AGG": agg})
    f = funds_df[funds_df.symbol == "AGG"].iloc[0]
    assert len(exp) == 0 and f.rows == 0 and f.coverage_pct == 0
    # fixture is a 20-row excerpt (sums to ~9.7): scale it to a full fund
    total = sum(r["weightPercentage"] for r in agg)
    full = [dict(r, weightPercentage=r["weightPercentage"] * 100 / total)
            for r in agg]
    *_, detail = run({"AGG": full})
    assert "AGG" not in detail["weight_sum_outside"]
    *_, detail = run({"AGG": agg})
    assert "AGG" in detail["weight_sum_outside"]


def test_isin_map_lists_all_listings():
    h = {"XIU.TO": fx("xiu"), "VEA": [row("2330.TW", 3.0)]}
    exp, _, imap, _ = run(h)
    ry = imap[imap.company_id == RY]
    assert {"RY", "RY.TO"} <= set(ry.symbol)
    tsm = imap[imap.symbol == "TSM"].iloc[0]
    assert tsm.company_id == "TW0002330008" and bool(tsm.is_adr) is True


def test_dtypes_fetched_and_info():
    exp, funds_df, _, _ = run({"XIU.TO": fx("xiu")},
                              info={"XIU.TO": {"mer": 0.18, "issuer": "iShares",
                                               "asset_class": "Equity"}})
    assert str(exp.weight.dtype) == "float64" and str(exp.bucket.dtype) == "int64"
    f = funds_df[funds_df.symbol == "XIU.TO"].iloc[0]
    assert f.fetched == "2026-11-22" and f.mer == 0.18 and f.issuer == "iShares"
    assert isinstance(f.series, list)


def test_holdings_over_coverage_limit_drop_the_fund():
    apple = "US0378331005"
    lev = [row("AAPL", 127.5, isin=apple), row("", -27.5)]      # cash borrow
    edge = [row("AAPL", 110.0, isin=apple), row("", -10.0)]     # at the limit: kept
    exp, funds_df, _, detail = run({"LEV.TO": lev, "EDGE.TO": edge, "XIU.TO": fx("xiu")},
                                   {"LEV.TO", "EDGE.TO", "XIU.TO"})
    assert detail["dropped_leveraged_holdings"] == ["LEV.TO"]
    assert "LEV.TO" not in set(exp.fund) and "LEV.TO" not in set(funds_df.symbol)
    assert {"EDGE.TO", "XIU.TO"} <= set(exp.fund) and "EDGE.TO" in set(funds_df.symbol)
    assert detail["funds_with_rows"] == 2
