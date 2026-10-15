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
                    {"name": cli.NEWS_MACHINE, "stateMachineArn": "arn:news"}]
        return type("P", (), {"paginate": lambda self: [{"stateMachines": machines}]})()


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
