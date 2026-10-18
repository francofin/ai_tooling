from pipelines.checks import CheckResult
from pipelines.report import RunReport
from pipelines.results import StageResult


def make_report():
    return RunReport(run_id="lean-20261017-1000", job="weekly", mode="lean",
                     started_at="2026-10-17T10:00:00+00:00")


def test_add_stage_replaces_same_name():
    r = make_report()
    r.add_stage(StageResult("fetch_a", attempted=1, saved=1), 3.0)
    r.add_stage(StageResult("fetch_a", attempted=2, saved=2), 4.0)
    assert len(r.stages) == 1
    assert r.stage("fetch_a")["attempted"] == 2
    assert r.stage("fetch_a")["seconds"] == 4.0


def test_finish_takes_worst_check():
    r = make_report()
    r.add_checks([CheckResult("a", "pass"), CheckResult("b", "warn")])
    r.finish()
    assert r.verdict == "warn"
    assert r.finished_at is not None


def test_finish_override():
    r = make_report()
    r.add_checks([CheckResult("a", "fail")])
    r.finish(verdict_override="warn")
    assert r.verdict == "warn"


def test_round_trip():
    r = make_report()
    r.add_stage(StageResult("fetch_a", attempted=1, saved=1), 1.0)
    r.add_checks([CheckResult("a", "warn", 1, 0, "detail")])
    r.counts = {"stock_prices": 10}
    r.finish()
    back = RunReport.from_dict(r.to_dict())
    assert back == r


def test_summary_lists_non_passing_checks():
    r = make_report()
    r.add_stage(StageResult("fetch_a", attempted=100, saved=97, failed=3), 3725)
    r.add_checks([CheckResult("ok", "pass"),
                  CheckResult("freshness.tsx", "warn", 1, 1, "1 session behind")])
    r.finish()
    text = r.summary()
    assert "verdict: WARN" in text
    assert "fetch_a" in text and "1h02m" in text
    assert "1 pass, 1 warn, 0 fail" in text
    assert "WARN freshness.tsx — 1 session behind" in text
    assert "ok —" not in text


def test_summary_shows_bandwidth_and_price_fetch_modes():
    r = make_report()
    prices = StageResult("fetch_stock_prices", attempted=10, saved=10,
                         detail={"full": 1, "incremental": 8, "restated": 1})
    r.add_stage(prices, 60, downloaded=150_000_000)
    r.add_stage(StageResult("build_a", attempted=1, saved=1), 1)
    text = r.summary()
    assert "150.0 MB" in text
    assert "Downloaded from APIs: 150.0 MB" in text
    assert "fetch_stock_prices: 8 recent window, 1 restated (full re-download), 1 new" in text


def test_add_stage_without_download_records_zero_bytes():
    r = make_report()
    r.add_stage(StageResult("build_a"), 1)
    assert r.stage("build_a")["bytes"] == 0
