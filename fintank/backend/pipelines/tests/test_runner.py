import datetime as dt

import pytest

from pipelines import runner
from pipelines.checks import CheckResult
from pipelines.report import RunReport
from pipelines.results import StageResult
from pipelines.store import LocalStore, run_key
from pipelines.tests.helpers import write_constituents, write_price_json


class FakePipeline:
    def __init__(self, root, fail_on=None):
        self.root = root
        self.calls = []
        self.fail_on = fail_on

    def __getattr__(self, name):
        if not name.startswith(("refresh_", "fetch_", "build_")):
            raise AttributeError(name)

        def stage(**kwargs):
            self.calls.append((name, kwargs))
            if name == self.fail_on:
                raise RuntimeError(f"{name} blew up")
            return StageResult(name, attempted=1, saved=1)
        return stage


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, subject, message):
        self.sent.append(subject)


def adds(status):
    return lambda ctx, report: report.add_checks([CheckResult("x", status)])


def nothing(ctx, report):
    pass


def make_ctx(tmp_path, pipeline=None, **kwargs):
    defaults = dict(pipeline=pipeline or FakePipeline(str(tmp_path / "data")),
                    store=LocalStore(str(tmp_path / "store")), run_id="lean-1",
                    mode="lean", dry_run=True, log=lambda *a: None)
    defaults.update(kwargs)
    return runner.RunContext(**defaults)


def test_resolve_mode():
    assert runner.resolve_mode("auto", dt.date(2026, 11, 7)) == "full"
    assert runner.resolve_mode("auto", dt.date(2026, 11, 8)) == "lean"
    assert runner.resolve_mode("lean", dt.date(2026, 11, 1)) == "lean"
    with pytest.raises(ValueError):
        runner.resolve_mode("weekly", dt.date(2026, 11, 1))


def test_make_run_id():
    assert runner.make_run_id("lean", dt.datetime(2026, 10, 17, 10, 0)) == "lean-20261017-1000"


def test_full_adds_the_quarterly_fetches():
    assert set(runner.FULL_STAGES) - set(runner.LEAN_STAGES) == {
        "fetch_profiles", "fetch_etf_profiles", "fetch_financial_statements",
        "fetch_ratios", "fetch_revenue_segments"}
    assert runner.LEAN_STAGES[0] == "refresh_constituents"
    assert runner.LEAN_STAGES[-len(runner.BUILD_STAGES):] == runner.BUILD_STAGES


def test_lean_order_and_arguments(tmp_path):
    ctx = make_ctx(tmp_path, limit=5)
    runner.run_weekly(ctx, checks=adds("pass"), staging=nothing)
    calls = dict(ctx.pipeline.calls)
    assert [name for name, _ in ctx.pipeline.calls] == runner.LEAN_STAGES
    assert calls["fetch_stock_prices"] == {"from_date": "1999-01-01", "limit": 5}
    assert calls["fetch_sector_history"] == {"from_date": "2010-01-01"}
    assert calls["refresh_constituents"] == {}


def test_resume_skips_checkpointed_stages_but_rebuilds(tmp_path):
    first = make_ctx(tmp_path, pipeline=FakePipeline(str(tmp_path), fail_on="fetch_ttm_ratios"))
    with pytest.raises(RuntimeError):
        runner.run_weekly(first, checks=adds("pass"), staging=nothing)
    second = make_ctx(tmp_path, pipeline=FakePipeline(str(tmp_path)))
    runner.run_weekly(second, checks=adds("pass"), staging=nothing)
    names = [name for name, _ in second.pipeline.calls]
    assert names[0] == "fetch_ttm_ratios"
    assert names[-len(runner.BUILD_STAGES):] == runner.BUILD_STAGES
    report = second.store.get_json(run_key("lean-1", "report.json"))
    assert {s["name"] for s in report["stages"]} == set(runner.LEAN_STAGES)


def test_warn_holds_and_notifies(tmp_path):
    notifier = FakeNotifier()
    ctx = make_ctx(tmp_path, notifier=notifier)
    report = runner.run_weekly(ctx, checks=adds("warn"), staging=nothing)
    assert report.verdict == "warn"
    assert ctx.store.get_json(run_key("lean-1", "verdict.json")) == {
        "run_id": "lean-1", "verdict": "warn", "hold": True}
    assert notifier.sent == ["[Fintank] Weekly run lean-1 held - WARN"]


@pytest.mark.parametrize("always_hold,hold,emails", [(True, True, 1), (False, False, 0)])
def test_pass_publishes_unless_always_hold(tmp_path, always_hold, hold, emails):
    notifier = FakeNotifier()
    ctx = make_ctx(tmp_path, notifier=notifier, always_hold=always_hold)
    runner.run_weekly(ctx, checks=adds("pass"), staging=nothing)
    assert ctx.store.get_json(run_key("lean-1", "verdict.json"))["hold"] is hold
    assert len(notifier.sent) == emails


def test_real_run_pulls_and_pushes_state(tmp_path, monkeypatch):
    pulled, pushed = [], []
    monkeypatch.setattr(runner.state, "pull", lambda *a, **kw: pulled.append(a))
    monkeypatch.setattr(runner.state, "push", lambda *a, **kw: pushed.append(kw["since"]))
    ctx = make_ctx(tmp_path, dry_run=False, s3=object(), state_bucket="state")
    runner.run_weekly(ctx, checks=adds("pass"), staging=nothing)
    assert len(pulled) == 1
    assert len(pushed) == len([s for s in runner.LEAN_STAGES if s in runner.CHECKPOINTED])


def test_run_checks_on_fixture_data(pipeline, tmp_path):
    write_constituents(pipeline, "sp500_const", ["AAA"])
    write_price_json(pipeline, "sp500", "AAA", "2026-10-09")
    pipeline.build_price_parquets(sub_universes=["sp500"])
    ctx = make_ctx(tmp_path, pipeline=pipeline, today=dt.date(2026, 10, 10))
    report = RunReport("lean-1", "weekly", "lean", "2026-10-10T10:00:00+00:00", dry_run=True)
    report.add_stage(StageResult("fetch_stock_prices", attempted=1, saved=1), 1.0)
    runner.run_checks(ctx, report)
    runner.stage_outputs(ctx, report)
    by_name = {c["name"]: c["status"] for c in report.checks}
    assert by_name["freshness.sp500"] == "pass"
    assert by_name["fetch_stock_prices.failure_rate"] == "pass"
    assert by_name["readable.stock_prices"] == "pass"
    assert by_name["counts"] == "pass"
    assert by_name["prices.non_positive"] == "pass"
    assert by_name["staging"] == "pass"
    assert report.counts["stock_prices"] == 2           # daily + monthly


class RecordingStore(LocalStore):
    def __init__(self, base):
        super().__init__(base)
        self.writes = []

    def put_json(self, key, data):
        self.writes.append(key.rsplit("/", 1)[-1])
        super().put_json(key, data)


def test_report_is_written_before_progress_for_a_checkpointed_stage(tmp_path):
    ctx = make_ctx(tmp_path, store=RecordingStore(str(tmp_path / "store")))
    runner.run_weekly(ctx, checks=adds("pass"), staging=nothing)
    first_progress = ctx.store.writes.index("progress.json")
    assert ctx.store.writes[:first_progress] == ["report.json"]


def test_stale_verdict_is_removed_when_a_run_starts(tmp_path):
    ctx = make_ctx(tmp_path, pipeline=FakePipeline(str(tmp_path), fail_on="fetch_ttm_ratios"))
    verdict_key = run_key("lean-1", "verdict.json")
    ctx.store.put_json(verdict_key, {"run_id": "lean-1", "verdict": "pass", "hold": False})
    with pytest.raises(RuntimeError):
        runner.run_weekly(ctx, checks=adds("pass"), staging=nothing)
    assert ctx.store.get_json(verdict_key) is None


def test_failed_held_email_leaves_no_verdict(tmp_path):
    class BrokenNotifier:
        def send(self, subject, message):
            raise RuntimeError("SNS is down")

    ctx = make_ctx(tmp_path, notifier=BrokenNotifier())
    with pytest.raises(RuntimeError, match="SNS"):
        runner.run_weekly(ctx, checks=adds("warn"), staging=nothing)
    assert ctx.store.get_json(run_key("lean-1", "verdict.json")) is None


def test_fred_last_dates_ignores_series_no_longer_fetched(pipeline):
    import json
    import os
    os.makedirs(pipeline.econ_json_dir, exist_ok=True)
    for sid, last in (("DGS10", "2026-10-09"), ("CPGRLE01USM659N", "2025-04-01")):
        with open(os.path.join(pipeline.econ_json_dir, f"{sid}.json"), "w") as f:
            json.dump([{"date": last, "value": 1.0}], f)
    assert runner.fred_last_dates(pipeline) == {"DGS10": "2026-10-09"}


def test_build_failures_count_as_checks(pipeline, tmp_path):
    ctx = make_ctx(tmp_path, pipeline=pipeline, today=dt.date(2026, 10, 10))
    report = RunReport("lean-1", "weekly", "lean", "2026-10-10T10:00:00+00:00", dry_run=True)
    report.add_stage(StageResult("build_relative_performance", attempted=20, saved=5,
                                 failed=15), 1.0)
    runner.run_checks(ctx, report)
    by_name = {c["name"]: c["status"] for c in report.checks}
    assert by_name["build_relative_performance.failure_rate"] == "fail"
    assert by_name["minimum.stock_prices"] == "fail"           # empty fixture data
