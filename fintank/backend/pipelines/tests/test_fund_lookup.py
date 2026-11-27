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


def test_coverage_band_keeps_and_flags_leveraged():
    apple = "US0378331005"
    lev = [row("AAPL", 127.5, isin=apple), row("", -27.5)]      # 1.275x: kept, flagged
    edge = [row("AAPL", 110.0, isin=apple), row("", -10.0)]     # at 110: kept, not flagged
    wild = [row("AAPL", 160.0, isin=apple), row("", -60.0)]     # over 150: dropped
    exp, funds_df, _, detail = run({"LEV.TO": lev, "EDGE.TO": edge, "WILD.TO": wild, "XIU.TO": fx("xiu")},
                                   {"LEV.TO", "EDGE.TO", "WILD.TO", "XIU.TO"})
    assert detail["dropped_leveraged_holdings"] == ["WILD.TO"]
    assert detail["leveraged_kept"] == ["LEV.TO"]
    assert "WILD.TO" not in set(exp.fund) and "WILD.TO" not in set(funds_df.symbol)
    flags = dict(zip(funds_df.symbol, funds_df.leveraged))
    assert flags == {"LEV.TO": True, "EDGE.TO": False, "XIU.TO": False}
    assert funds_df.leveraged.dtype == bool
    lev_w = exp[(exp.fund == "LEV.TO")].weight.sum()
    assert lev_w == pytest.approx(127.5)                          # real weight, not scaled
    assert detail["funds_with_rows"] == 3


def _ten(total):
    return [row(f"S{i}", total / 10) for i in range(10)]


def _top10_run(rows, info):
    sym = {f"S{i}": f"ID{i}" for i in range(10)}
    funds = [{"symbol": "TEN.TO", "name": "Ten", "exchange": "TSX", "region": "ca",
              "currency": "CAD", "aum": 1.0, "isin": "", "series": []}]
    return build_lookup({"TEN.TO": rows}, funds, sym, {}, info)


@pytest.mark.parametrize("info", [{"TEN.TO": {"holdings_count": 0}},
                                  {"TEN.TO": {"holdings_count": None}}, {}])
def test_top10_only_fund_dropped_and_counted(info):
    exp, funds_df, _, detail = _top10_run(_ten(100.0), info)
    assert exp.empty and funds_df.empty
    assert detail["dropped_top10_only"] == 1
    assert detail["dropped_top10_only_symbols"] == ["TEN.TO"]
    assert funds_df.attrs["dropped_top10_only"] == 1


@pytest.mark.parametrize("rows,info", [
    (_ten(100.0), {"TEN.TO": {"holdings_count": 10}}),   # FMP says it really has 10
    (_ten(60.0), {"TEN.TO": {"holdings_count": 0}}),     # not rescaled to 100
    (_ten(100.0)[:9] + [row("S9", 1.0)] + [row("X", 9.0)], {}),   # 11 rows
])
def test_ten_row_fund_kept_when_not_top10_only(rows, info):
    exp, funds_df, _, detail = _top10_run(rows, info)
    assert list(funds_df.symbol) == ["TEN.TO"] and not exp.empty
    assert detail["dropped_top10_only"] == 0 and funds_df.attrs["dropped_top10_only"] == 0


def test_non_string_assets_skipped_and_counted():
    rows = [row("RY.TO", 5.0, isin=RY), {"asset": ["X"], "weightPercentage": 3.0},
            {"asset": {"a": 1}, "weightPercentage": 2.0}, {"asset": 7, "weightPercentage": 1.0}]
    exp, funds_df, _, detail = run({"XIU.TO": rows, "MIX.TO": [row("XIU.TO", 50)]},
                                   {"XIU.TO", "MIX.TO"})
    assert detail["bad_asset_rows"] == 3
    assert set(exp.fund) == {"XIU.TO", "MIX.TO"}


def test_two_lines_of_one_company_sum_into_one_row():
    def line(symbol, isin, exchange):
        return {"symbol": symbol, "companyName": "Henkel AG & Co. KGaA", "isin": isin,
                "exchange": exchange, "isEtf": "false", "isFund": "false", "isAdr": "false"}
    lines = [line("HEN.DE", "DE0006048408", "XETRA"), line("HEN3.DE", "DE0006048432", "XETRA"),
             line("HEN3.F", "DE0006048432", "FSX")]
    sym, isin, _ = company_ids(lines)
    fund = {"symbol": "F", "name": "F", "exchange": "TSX", "region": "ca",
            "currency": "CAD", "aum": 1.0, "isin": "", "series": []}
    holdings = {"F": [row("HEN.DE", 2.0, "DE0006048408"), row("HEN3.DE", 1.5, "DE0006048432")]}
    exp, *_ = build_lookup(holdings, [fund], sym, isin, {}, listings=listings_of(lines))
    r = exp[(exp.company_id == "DE0006048432") & (exp.fund == "F")]
    assert len(r) == 1 and r.iloc[0].weight == pytest.approx(3.5)
    assert len(exp[exp.fund == "F"]) == 1
