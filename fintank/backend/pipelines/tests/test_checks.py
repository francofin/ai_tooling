import datetime as dt
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from pipelines import checks as c
from pipelines import thresholds as t
from pipelines.results import StageResult

D = dt.date


def statuses(results):
    return {r.name: r.status for r in results}


def test_verdict_is_worst():
    assert c.verdict([]) == c.PASS
    assert c.verdict([c.CheckResult("a", c.PASS), c.CheckResult("b", c.WARN)]) == c.WARN
    assert c.verdict([c.CheckResult("a", c.FAIL), c.CheckResult("b", c.WARN)]) == c.FAIL


def test_constituents():
    r = StageResult("refresh_constituents", detail={"lists": {
        "kept": {"status": "kept", "previous": 10, "new": None, "error": "shrank"},
        "grew": {"status": "updated", "previous": 100, "new": 151, "error": None},
        "fine": {"status": "updated", "previous": 100, "new": 150, "error": None},
        "new": {"status": "updated", "previous": None, "new": 5, "error": None},
    }})
    assert statuses(c.check_constituents(r)) == {
        "constituents.kept": c.FAIL, "constituents.grew": c.WARN,
        "constituents.fine": c.PASS, "constituents.new": c.PASS}


@pytest.mark.parametrize("failed,expected", [
    (2, c.PASS), (3, c.WARN), (10, c.WARN), (11, c.FAIL)])
def test_fetch_failure_rate_boundaries(failed, expected):
    r = StageResult("fetch_x", attempted=100, saved=100 - failed, failed=failed)
    result = c.check_fetch(r)
    assert (result.name, result.status) == ("fetch_x.failure_rate", expected)


def test_freshness():
    sessions = [D(2026, 10, 7), D(2026, 10, 8), D(2026, 10, 9)]
    results = c.check_freshness(
        {"a": "2026-10-09", "b": "2026-10-08", "c": "2026-10-07", "d": None,
         "e": "2026-10-10"}, sessions)
    assert statuses(results) == {
        "freshness.a": c.PASS, "freshness.b": c.WARN, "freshness.c": c.FAIL,
        "freshness.d": c.FAIL, "freshness.e": c.PASS}


def test_recent_nyse_sessions_skips_weekend_and_today():
    sessions = c.recent_nyse_sessions(D(2026, 10, 10))          # a Saturday
    assert sessions[-1] == D(2026, 10, 9)
    assert all(s.weekday() < 5 for s in sessions)


def test_outputs_readable(tmp_path):
    good = tmp_path / "AAA_prices.parquet"
    pd.DataFrame({"adjClose": [1.0], "returns": [0.0]}).to_parquet(good)
    missing_col = tmp_path / "BBB_prices.parquet"
    pd.DataFrame({"adjClose": [1.0]}).to_parquet(missing_col)
    broken = tmp_path / "x.parquet"
    broken.write_text("nope")
    seg = tmp_path / "A_segments.json"
    seg.write_text(json.dumps({"ok": 1}))
    outputs = [SimpleNamespace(local_path=str(good), dataset="stock_prices"),
               SimpleNamespace(local_path=str(missing_col), dataset="stock_prices"),
               SimpleNamespace(local_path=str(broken), dataset="econ"),
               SimpleNamespace(local_path=str(seg), dataset="revenue_segments")]
    results = statuses(c.check_outputs_readable(outputs))
    assert results == {"readable.stock_prices": c.FAIL, "readable.econ": c.FAIL,
                       "readable.revenue_segments": c.PASS}


def test_counts():
    assert statuses(c.check_counts({"x": 1}, None)) == {"counts": c.PASS}
    results = c.check_counts({"a": 98, "b": 97, "c": 89},
                             {"a": 100, "b": 100, "c": 100, "zero": 0})
    assert statuses(results) == {"counts.a": c.PASS, "counts.b": c.WARN,
                                 "counts.c": c.FAIL}


def test_factor_staleness():
    current = {"a": {"rows": 100, "stale": 11},   # 11% → fail
               "b": {"rows": 100, "stale": 10},   # 2x baseline 5, +5 → warn
               "c": {"rows": 100, "stale": 3},    # 3x baseline 1 but only +2 → pass
               "d": {"rows": 100, "stale": 4}}    # no baseline → pass
    baseline = {"a": {"stale": 1}, "b": {"stale": 5}, "c": {"stale": 1}}
    assert statuses(c.check_factor_staleness(current, baseline)) == {
        "factor_staleness.a": c.FAIL, "factor_staleness.b": c.WARN,
        "factor_staleness.c": c.PASS, "factor_staleness.d": c.PASS}


def test_price_sanity():
    calm = pd.Series([10.0, 10.5, 10.4])
    jump = pd.Series([10.0, 10.1, 30.0])
    bad = pd.Series([10.0, 0.0, 10.0])
    few = [("CALM", calm), ("JUMP", jump), ("BAD", bad)]
    results = statuses(c.check_price_sanity(few))
    assert results["prices.non_positive"] == c.WARN
    # 2 of 3 symbols jumped (BAD's recovery from 0 is a jump too): > 1% → warn
    assert results["prices.large_moves"] == c.WARN
    many = [(f"S{i}", calm) for i in range(200)] + [("JUMP", jump)]
    assert statuses(c.check_price_sanity(many))["prices.large_moves"] == c.PASS


def test_econ():
    today = D(2026, 10, 14)
    results = statuses(c.check_econ(
        {"DGS10": "2026-10-09", "GDP": "2026-01-01", "NEWSERIES": "2026-01-01"},
        today))
    assert results == {"econ.DGS10": c.PASS, "econ.GDP": c.WARN,
                       "econ.NEWSERIES": c.WARN}


def test_quarterly_gdp_is_current_until_the_next_advance_estimate():
    # Q2 is dated 2026-04-01 and stays the latest observation until the Q3
    # advance estimate at the end of October.
    results = statuses(c.check_econ({"GDP": "2026-04-01"}, D(2026, 10, 28)))
    assert results == {"econ.GDP": c.PASS}


def test_staging():
    assert c.check_staging(0, 100).status == c.FAIL
    assert c.check_staging(0, 0).status == c.PASS
    assert c.check_staging(5, 100).status == c.PASS


def test_minimums_fail_below_floor_even_without_baseline():
    counts = dict(t.MIN_COUNTS)
    counts["profile_rows.company_profiles"] = 45          # a truncated aggregate
    results = statuses(c.check_minimums(counts))
    assert results["minimum.profile_rows.company_profiles"] == c.FAIL
    assert results["minimum.stock_prices"] == c.PASS
    missing = statuses(c.check_minimums({}))
    assert set(missing.values()) == {c.FAIL}


def test_factor_coverage_against_constituent_lists():
    lists = {"sp500": {"rows": 493, "stale": 1}, "nas": {"rows": 5, "stale": 4},
             "unknown": {"rows": 3, "stale": 0}}
    members = {"sp500": 504, "nas": 101}
    assert statuses(c.check_factor_coverage(lists, members)) == {
        "factor_coverage.sp500": c.PASS, "factor_coverage.nas": c.FAIL}


def _window(cov=100.0, res=0.0, ident=0.0, nf=0):
    return {"covered_weight_pct": cov, "residual_pp": res,
            "identity_error_pp": ident, "non_finite": nf}


def _attr_detail(sub="sp500", **window):
    return {sub: {"rows": 10, "currency_basis": "USD",
                  "windows": {w: _window(**window) for w in t.ATTRIBUTION_RESIDUAL_WARN_BP}}}


def _by_name(results):
    return {r.name: r.status for r in results}


def test_attribution_clean_lists_pass():
    detail = {**_attr_detail("sp500"), **_attr_detail("nas")}
    out = _by_name(c.check_attribution(detail, expected_lists=2))
    assert set(out.values()) == {c.PASS}
    assert {"attribution.sp500.coverage", "attribution.sp500.identity",
            "attribution.sp500.non_finite", "attribution.sp500.residual",
            "attribution.lists"} <= set(out)


def test_attribution_low_coverage_warns_but_long_tail_floor_is_lower():
    assert _by_name(c.check_attribution(_attr_detail("sp500", cov=95.0), 1))[
        "attribution.sp500.coverage"] == c.WARN
    assert _by_name(c.check_attribution(_attr_detail("rmicro", cov=95.0), 1))[
        "attribution.rmicro.coverage"] == c.PASS


def test_attribution_identity_and_non_finite_warn():
    out = _by_name(c.check_attribution(_attr_detail("sp500", ident=1e-3, nf=2), 1))
    assert out["attribution.sp500.identity"] == c.WARN
    assert out["attribution.sp500.non_finite"] == c.WARN


def test_attribution_residual_thresholds_by_group():
    assert _by_name(c.check_attribution(_attr_detail("sp500", res=0.30), 1))[
        "attribution.sp500.residual"] == c.WARN          # 30bp > 25bp at 1W
    detail = {"tsx": {"rows": 1, "currency_basis": "CAD",
                      "windows": {"1W": _window(res=0.30)}}}
    assert _by_name(c.check_attribution(detail, 1))["attribution.tsx.residual"] == c.PASS


def test_attribution_local_currency_residual_is_reported_not_checked():
    res = c.check_attribution(_attr_detail("msci_eafe", res=-4.0), 1)
    r = next(x for x in res if x.name == "attribution.msci_eafe.residual")
    assert r.status == c.PASS and r.value == pytest.approx(-4.0)


def test_attribution_missing_reference_passes():
    res = c.check_attribution(_attr_detail("sp500", res=None), 1)
    r = next(x for x in res if x.name == "attribution.sp500.residual")
    assert r.status == c.PASS and "no reference" in r.detail


def test_attribution_fewer_lists_than_expected_warns():
    assert _by_name(c.check_attribution(_attr_detail("sp500"), expected_lists=8))[
        "attribution.lists"] == c.WARN


@pytest.mark.parametrize("window", [
    dict(cov=0.0), dict(res=1e6), dict(ident=1e6), dict(nf=10**6)])
def test_attribution_never_fails_in_v1(window):
    out = c.check_attribution({**_attr_detail("sp500", **window), "junk": "x"}, 8)
    assert c.FAIL not in {r.status for r in out}


def test_attribution_stage_failure_rate_is_capped_at_warn():
    r = StageResult("build_index_attribution")
    for ok in (False, False, True):
        r.record(ok, "x")
    assert c.check_build_stage(r).status == c.WARN
    other = StageResult("build_contr_to_var")
    for ok in (False, False, True):
        other.record(ok, "x")
    assert c.check_build_stage(other).status == c.FAIL


def test_small_cap_long_window_residual_is_reported_not_checked():
    detail = {"r2000": {"rows": 1, "currency_basis": "USD", "windows": {
        "3M": _window(res=0.05), "ytd": _window(res=-4.86), "1Y": _window(res=-6.8)}}}
    r = next(x for x in c.check_attribution(detail, 1) if x.name == "attribution.r2000.residual")
    assert r.status == c.PASS and "reconstitution" in r.detail
    detail["r2000"]["windows"]["3M"] = _window(res=2.0)       # still checked through 3M
    r = next(x for x in c.check_attribution(detail, 1) if x.name == "attribution.r2000.residual")
    assert r.status == c.WARN
