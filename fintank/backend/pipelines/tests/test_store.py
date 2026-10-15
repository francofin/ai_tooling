import pytest

from pipelines import store


@pytest.fixture(params=["local", "s3"])
def any_store(request, tmp_path, aws):
    if request.param == "local":
        return store.LocalStore(str(tmp_path / "runs-store"))
    aws.create_bucket(Bucket="state")
    return store.S3Store("state", client=aws)


def test_json_round_trip_and_default(any_store):
    assert any_store.get_json("runs/x/a.json") is None
    assert any_store.get_json("runs/x/a.json", {"d": 1}) == {"d": 1}
    any_store.put_json("runs/x/a.json", {"v": 1})
    assert any_store.get_json("runs/x/a.json") == {"v": 1}
    assert any_store.exists("runs/x/a.json")
    assert not any_store.exists("runs/x/b.json")


def test_put_file_and_list_prefixes(any_store, tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("hi")
    any_store.put_file("runs/r1/f.txt", str(f))
    any_store.put_json("runs/r2/report.json", {})
    assert any_store.list_prefixes("runs/") == ["runs/r1/", "runs/r2/"]


def test_run_key():
    assert store.run_key("lean-1", "report.json") == "runs/lean-1/report.json"


def test_default_state_bucket(monkeypatch):
    class FakeSts:
        def get_caller_identity(self):
            return {"Account": "123456789012"}
    monkeypatch.delenv("STATE_BUCKET", raising=False)
    assert store.default_state_bucket(FakeSts()) == "fintank-pipeline-123456789012"
    monkeypatch.setenv("STATE_BUCKET", "custom")
    assert store.default_state_bucket(FakeSts()) == "custom"


def test_live_bucket(monkeypatch):
    monkeypatch.delenv("LIVE_BUCKET", raising=False)
    assert store.live_bucket() == "thetradingfloor"
