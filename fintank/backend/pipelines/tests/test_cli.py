import json

import pytest

from pipelines import cli
from pipelines.store import S3Store, run_key


class FakeSfn:
    def __init__(self):
        self.calls = []

    def send_task_success(self, **kw):
        self.calls.append(("send_task_success", kw))

    def send_task_failure(self, **kw):
        self.calls.append(("send_task_failure", kw))

    def start_execution(self, **kw):
        self.calls.append(("start_execution", kw))
        return {"executionArn": "arn:exec"}

    def get_paginator(self, name):
        assert name == "list_state_machines"
        machines = [{"name": cli.WEEKLY_MACHINE, "stateMachineArn": "arn:weekly"},
                    {"name": cli.NEWS_MACHINE, "stateMachineArn": "arn:news"},
                    {"name": cli.EARNINGS_MACHINE, "stateMachineArn": "arn:earnings"},
                    {"name": cli.EARNINGS_BACKFILL_MACHINE,
                     "stateMachineArn": "arn:earnings-backfill"}]
        return type("P", (), {"paginate": lambda self: [{"stateMachines": machines}]})()


@pytest.fixture(autouse=True)
def _no_anthropic_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def wired(aws, monkeypatch):
    aws.create_bucket(Bucket="state")
    monkeypatch.setenv("STATE_BUCKET", "state")
    sfn = FakeSfn()
    monkeypatch.setattr(cli, "aws_client",
                        lambda service: sfn if service == "stepfunctions" else aws)
    return sfn, aws


def test_parser_defaults():
    args = cli.build_parser().parse_args(["run"])
    assert (args.mode, args.dry_run, args.limit, args.run_id) == ("auto", False, None, None)
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["start"])            # --mode is required


def test_approve_sends_task_success(wired):
    sfn, s3 = wired
    S3Store("state", s3).put_json(run_key("lean-1", "approval-token.json"),
                                  {"task_token": "tok", "run_id": "lean-1"})
    assert cli.main(["approve", "lean-1"]) == 0
    assert sfn.calls == [("send_task_success",
                          {"taskToken": "tok", "output": json.dumps({"decision": "approve"})})]


def test_discard_sends_task_failure(wired):
    sfn, s3 = wired
    S3Store("state", s3).put_json(run_key("lean-1", "approval-token.json"),
                                  {"task_token": "tok", "run_id": "lean-1"})
    cli.main(["discard", "lean-1"])
    name, kwargs = sfn.calls[0]
    assert (name, kwargs["taskToken"], kwargs["error"]) == ("send_task_failure", "tok", "Discarded")


def test_approve_without_token_exits(wired):
    with pytest.raises(SystemExit, match="not waiting for approval"):
        cli.main(["approve", "lean-9"])


def test_start_passes_mode_limit_and_run_id(wired):
    sfn, _ = wired
    cli.main(["start", "--mode", "lean", "--limit", "5", "--run-id", "lean-1"])
    name, kwargs = sfn.calls[0]
    assert (name, kwargs["stateMachineArn"]) == ("start_execution", "arn:weekly")
    assert json.loads(kwargs["input"]) == {"mode": "lean", "limit": 5, "run_id": "lean-1"}


def test_start_news(wired):
    sfn, _ = wired
    cli.main(["start-news"])
    assert sfn.calls[0][1]["stateMachineArn"] == "arn:news"


def test_crash_sends_email_and_reraises(monkeypatch):
    sent = []

    class FakeNotifier:
        def send(self, subject, message):
            sent.append(subject)

    def boom(args):
        raise RuntimeError("kaboom")

    monkeypatch.setitem(cli.COMMANDS, "run", boom)
    monkeypatch.setattr(cli, "Notifier", FakeNotifier)
    with pytest.raises(RuntimeError):
        cli.main(["run", "--run-id", "lean-1"])
    assert sent == ["[Fintank] run lean-1 crashed"]


def test_dry_run_crash_sends_nothing(monkeypatch):
    sent = []
    monkeypatch.setitem(cli.COMMANDS, "run", lambda args: 1 / 0)
    monkeypatch.setattr(cli, "Notifier", lambda: sent.append("x"))
    with pytest.raises(ZeroDivisionError):
        cli.main(["run", "--dry-run"])
    assert sent == []


def test_rollback_passes_force(wired, monkeypatch):
    calls = []
    monkeypatch.setattr(cli.publishing, "rollback",
                        lambda *a, **kw: calls.append((a[-1], kw)) or 3)
    assert cli.main(["rollback", "lean-1", "--yes", "--force"]) == 0
    assert cli.main(["rollback", "lean-1", "--yes"]) == 0
    assert calls == [("lean-1", {"force": True}), ("lean-1", {"force": False})]


def test_rollback_refusal_exits_with_the_reason(wired, monkeypatch):
    def refuse(*a, **kw):
        raise RuntimeError("lean-2 published after lean-1 — roll back the latest run first")

    monkeypatch.setattr(cli.publishing, "rollback", refuse)
    with pytest.raises(SystemExit, match="roll back the latest run first"):
        cli.main(["rollback", "lean-1", "--yes"])


@pytest.fixture
def seed_root(tmp_path, monkeypatch):
    root = tmp_path / "data"
    (root / "index_data").mkdir(parents=True)
    (root / "index_data" / "x.json").write_text("{}")
    monkeypatch.setenv("PIPELINE_DATA_ROOT", str(root))
    return root


def state_keys(s3):
    return [o["Key"] for o in s3.list_objects_v2(Bucket="state").get("Contents", [])]


def test_seed_state_uploads_into_an_empty_bucket(wired, seed_root):
    _, s3 = wired
    assert cli.main(["seed-state"]) == 0
    assert state_keys(s3) == ["state/index_data.tar.zst"]


def test_seed_state_refuses_when_state_exists_unless_forced(wired, seed_root, capsys):
    _, s3 = wired
    s3.put_object(Bucket="state", Key="state/index_data.tar.zst", Body=b"aws copy")
    assert cli.main(["seed-state"]) == 1
    assert "already holds" in capsys.readouterr().out
    body = s3.get_object(Bucket="state", Key="state/index_data.tar.zst")["Body"].read()
    assert body == b"aws copy"
    assert cli.main(["seed-state", "--force"]) == 0
    body = s3.get_object(Bucket="state", Key="state/index_data.tar.zst")["Body"].read()
    assert body != b"aws copy"


def test_news_search_flags():
    parse = cli.build_parser().parse_args
    assert parse(["news"]).search is None
    assert parse(["news", "--search"]).search is True
    assert parse(["news", "--no-search"]).search is False


def test_start_news_can_force_searches(wired):
    sfn, _ = wired
    cli.main(["start-news", "--search"])
    assert json.loads(sfn.calls[0][1]["input"]) == {"search": True}


def test_approve_reads_the_token_as_step_functions_writes_it(wired):
    """The WaitForApproval state's putObject JSON-encodes its Body string, so the
    file holds a JSON string that itself contains the object (seen on AWS)."""
    sfn, s3 = wired
    inner = json.dumps({"task_token": "tok", "run_id": "lean-1"})
    s3.put_object(Bucket="state", Key=run_key("lean-1", "approval-token.json"),
                  Body=json.dumps(inner).encode())
    cli.main(["approve", "lean-1"])
    assert sfn.calls[0][1]["taskToken"] == "tok"


# --- earnings -------------------------------------------------------------------

def test_earnings_parser_cases():
    parse = cli.build_parser().parse_args
    a = parse(["earnings"])
    assert (a.run_id, a.no_claude, a.dry_run) == (None, False, False)
    a = parse(["earnings", "--run-id", "e-1", "--no-claude", "--dry-run"])
    assert (a.run_id, a.no_claude, a.dry_run) == ("e-1", True, True)
    for step in ("submit", "check", "stage", "publish", "discarded"):
        a = parse(["earnings-backfill", step, "--run-id", "b-1"])
        assert (a.step, a.run_id, a.no_claude, a.from_results) == (step, "b-1", False, None)
    a = parse(["earnings-backfill", "stage", "--run-id", "b-2", "--from-results", "b-1"])
    assert a.from_results == "b-1"
    with pytest.raises(SystemExit):
        parse(["earnings-backfill", "submit"])                # --run-id is required
    with pytest.raises(SystemExit):
        parse(["earnings-backfill", "approve", "--run-id", "b-1"])
    assert parse(["start-earnings"]).command == "start-earnings"
    assert parse(["start-earnings-backfill"]).no_claude is False
    assert parse(["start-earnings-backfill", "--no-claude"]).no_claude is True
    a = parse(["pull-note", "BBD-B.TO", "2026-Q3"])
    assert (a.symbol, a.quarter) == ("BBD-B.TO", "2026-Q3")
    assert cli.EARNINGS_MACHINE == "fintank-daily-earnings"
    assert cli.EARNINGS_BACKFILL_MACHINE == "fintank-earnings-backfill"


def test_start_earnings_machines(wired):
    sfn, _ = wired
    cli.main(["start-earnings"])
    cli.main(["start-earnings-backfill", "--no-claude"])
    cli.main(["start-earnings-backfill"])
    assert [(c[1]["stateMachineArn"], json.loads(c[1]["input"])) for c in sfn.calls] == [
        ("arn:earnings", {}), ("arn:earnings-backfill", {"no_claude": True}),
        ("arn:earnings-backfill", {})]


@pytest.fixture
def earnings_env(clean_env, tmp_path, monkeypatch):
    """A backend/.env holding a Claude key: the CLI must never read it."""
    from pipelines import stock_pipeline as sp
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=from-the-file\nFMP_API=file-fmp\n")
    monkeypatch.setattr(sp, "BACKEND_DIR", str(tmp_path))
    monkeypatch.setenv("PIPELINE_DATA_ROOT", str(tmp_path / "data"))
    return tmp_path


class _Report:
    verdict = "pass"

    def summary(self):
        return "ok"


def test_earnings_dry_run_is_local_no_claude_and_ignores_env_file(earnings_env, monkeypatch):
    from pipelines import earnings
    seen = {}

    def fake_run_daily(run_id, fmp_key, anthropic_key, store, live, **kw):
        seen.update(fmp=fmp_key, key=anthropic_key, store=type(store).__name__,
                    live=type(live).__name__, no_claude=kw["no_claude"],
                    client=kw.get("batch_client"), notifier=kw.get("notifier"))
        return _Report()

    monkeypatch.setattr(earnings, "run_daily", fake_run_daily)
    assert cli.main(["earnings", "--dry-run", "--run-id", "e-1"]) == 0
    assert seen == {"fmp": "test-fmp-key", "key": "unset", "store": "LocalStore",
                    "live": "LocalStore", "no_claude": True, "client": None,
                    "notifier": None}


def test_earnings_reads_the_claude_key_from_the_environment_only(earnings_env, wired,
                                                                  monkeypatch):
    from pipelines import earnings
    seen = {}

    def fake_run_daily(run_id, fmp_key, anthropic_key, store, live, **kw):
        seen.update(key=anthropic_key, store=type(store).__name__,
                    no_claude=kw["no_claude"], client=kw.get("batch_client"))
        return _Report()

    monkeypatch.setattr(earnings, "run_daily", fake_run_daily)
    cli.main(["earnings", "--run-id", "e-1"])
    assert seen == {"key": "unset", "store": "S3Store", "no_claude": False, "client": None}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-placeholder")
    cli.main(["earnings", "--run-id", "e-2", "--no-claude"])
    assert (seen["key"], seen["no_claude"]) == ("env-placeholder", True)


def test_earnings_requires_fmp_key(earnings_env, monkeypatch):
    monkeypatch.delenv("FMP_API")
    (earnings_env / ".env").write_text("")
    with pytest.raises(SystemExit, match="FMP_API"):
        cli.main(["earnings", "--dry-run"])


def test_backfill_steps_dispatch(earnings_env, wired, monkeypatch):
    from pipelines import earnings_backfill as earnings
    calls = []
    monkeypatch.setattr(earnings, "backfill_submit",
                        lambda run_id, fmp, key, store, live, **kw:
                        calls.append(("submit", run_id, key, kw["no_claude"],
                                      kw["batch_client"])) or {"status": "no_claude"})
    monkeypatch.setattr(earnings, "backfill_stage",
                        lambda run_id, store, **kw:
                        calls.append(("stage", run_id, kw)) or {"hold": True})
    monkeypatch.setattr(earnings, "backfill_publish",
                        lambda run_id, store, live: calls.append(("publish", run_id)) or 2)
    monkeypatch.setattr(earnings, "backfill_discarded",
                        lambda run_id, store: calls.append(("discarded", run_id)))
    cli.main(["earnings-backfill", "submit", "--run-id", "b-1", "--no-claude"])
    cli.main(["earnings-backfill", "stage", "--run-id", "b-2", "--from-results", "b-1"])
    cli.main(["earnings-backfill", "publish", "--run-id", "b-1"])
    cli.main(["earnings-backfill", "discarded", "--run-id", "b-1"])
    assert calls == [("submit", "b-1", "unset", True, None),
                     ("stage", "b-2", {"batch_client": None, "from_results": "b-1"}),
                     ("publish", "b-1"), ("discarded", "b-1")]


def test_backfill_check_without_key_builds_no_client(earnings_env, wired):
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        cli.main(["earnings-backfill", "check", "--run-id", "b-1"])


def test_backfill_steps_after_submit_do_not_need_fmp(earnings_env, wired, monkeypatch):
    from pipelines import earnings_backfill
    monkeypatch.delenv("FMP_API")
    (earnings_env / ".env").write_text("")
    calls = []
    monkeypatch.setattr(earnings_backfill, "backfill_stage",
                        lambda run_id, store, **kw: calls.append("stage") or {})
    monkeypatch.setattr(earnings_backfill, "backfill_publish",
                        lambda run_id, store, live: calls.append("publish") or 0)
    monkeypatch.setattr(earnings_backfill, "backfill_discarded",
                        lambda run_id, store: calls.append("discarded"))
    cli.main(["earnings-backfill", "stage", "--run-id", "b-2", "--from-results", "b-1"])
    cli.main(["earnings-backfill", "publish", "--run-id", "b-2"])
    cli.main(["earnings-backfill", "discarded", "--run-id", "b-2"])
    assert calls == ["stage", "publish", "discarded"]
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):    # not FMP_API
        cli.main(["earnings-backfill", "check", "--run-id", "b-2"])
    with pytest.raises(SystemExit, match="FMP_API"):
        cli.main(["earnings-backfill", "submit", "--run-id", "b-3", "--no-claude"])


def test_pull_note(wired, monkeypatch):
    from pipelines import earnings
    calls = []
    monkeypatch.setattr(earnings, "pull_note",
                        lambda live, sym, q, lock_store: calls.append(
                            (live.bucket, sym, q, lock_store.bucket)))
    assert cli.main(["pull-note", "BBD-B.TO", "2026-Q3"]) == 0
    assert calls == [("thetradingfloor", "BBD-B.TO", "2026-Q3", "state")]


def test_pull_note_lock_held_exits(wired, monkeypatch):
    from pipelines import earnings

    def held(live, sym, q, lock_store):
        raise RuntimeError(earnings.LOCK_HELD)

    monkeypatch.setattr(earnings, "pull_note", held)
    with pytest.raises(SystemExit, match="another earnings run holds the lock"):
        cli.main(["pull-note", "RY.TO", "2026-Q3"])


def test_pull_note_unknown_quarter_exits(wired, monkeypatch):
    from pipelines import earnings

    def missing(live, sym, q, lock_store):
        raise KeyError(q)

    monkeypatch.setattr(earnings, "pull_note", missing)
    with pytest.raises(SystemExit, match="no 2026-Q9"):
        cli.main(["pull-note", "RY.TO", "2026-Q9"])
