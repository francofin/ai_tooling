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
