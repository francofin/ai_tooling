import json

import pytest

from pipelines import publish
from pipelines.outputs import Output
from pipelines.store import LAST_PUBLISHED_REPORT, LIVE_MANIFEST, S3Store, run_key


@pytest.fixture
def buckets(aws):
    aws.create_bucket(Bucket="state")
    aws.create_bucket(Bucket="live")
    aws.put_bucket_versioning(Bucket="live",
                              VersioningConfiguration={"Status": "Enabled"})
    return aws


def make_outputs(tmp_path, contents):
    outs = []
    for key, text in contents.items():
        path = tmp_path / key.replace("/", "__")
        path.write_text(text)
        dataset = "econ" if key.startswith("econ") else "stock_prices"
        outs.append(Output(str(path), key, dataset))
    return outs


def live_body(client, key):
    return client.get_object(Bucket="live", Key=key)["Body"].read().decode()


def do_run(client, tmp_path, run_id, contents):
    store = S3Store("state", client)
    store.put_json(run_key(run_id, "report.json"), {"run_id": run_id, "counts": {}})
    outs = make_outputs(tmp_path, contents)
    changed = publish.diff_outputs(outs, store.get_json(LIVE_MANIFEST, {}))
    publish.stage_changed(client, "state", run_id, changed)
    return changed, publish.publish(client, "state", "live", run_id)


def test_first_run_publishes_everything_then_nothing(buckets, tmp_path):
    contents = {"stock_data/stock_prices/daily/A.parquet": "a1", "econ_data/cpi.parquet": "c1"}
    changed, result = do_run(buckets, tmp_path, "r1", contents)
    assert len(changed) == 2
    assert result == {"published": 2, "by_dataset": {"stock_prices": 1, "econ": 1}}
    assert live_body(buckets, "econ_data/cpi.parquet") == "c1"
    head = buckets.head_object(Bucket="live", Key="econ_data/cpi.parquet")
    assert head["Metadata"]["sha256"] == publish.sha256_file(changed[1]["local_path"])
    store = S3Store("state", buckets)
    assert store.get_json(LAST_PUBLISHED_REPORT)["run_id"] == "r1"
    outs = make_outputs(tmp_path, contents)
    assert publish.diff_outputs(outs, store.get_json(LIVE_MANIFEST)) == []


def test_staged_in_publish_order(buckets, tmp_path):
    contents = {"econ_data/cpi.parquet": "c1", "stock_data/stock_prices/daily/A.parquet": "a1"}
    outs = make_outputs(tmp_path, contents)
    changed = publish.diff_outputs(outs, {})
    publish.stage_changed(buckets, "state", "r1", changed)
    manifest = S3Store("state", buckets).get_json(run_key("r1", "stage-manifest.json"))
    assert [f["dataset"] for f in manifest["files"]] == ["stock_prices", "econ"]


def test_rollback_restores_previous_versions_and_removes_new_keys(buckets, tmp_path):
    do_run(buckets, tmp_path, "r1", {"econ_data/cpi.parquet": "c1"})
    do_run(buckets, tmp_path, "r2", {"econ_data/cpi.parquet": "c2",
                                     "econ_data/new.parquet": "n2"})
    assert live_body(buckets, "econ_data/cpi.parquet") == "c2"

    assert publish.rollback(buckets, "state", "live", "r2") == 2
    assert live_body(buckets, "econ_data/cpi.parquet") == "c1"
    with pytest.raises(buckets.exceptions.NoSuchKey):
        buckets.get_object(Bucket="live", Key="econ_data/new.parquet")
    manifest = S3Store("state", buckets).get_json(LIVE_MANIFEST)
    assert "econ_data/new.parquet" not in manifest
    outs = make_outputs(tmp_path, {"econ_data/cpi.parquet": "c1"})
    assert publish.diff_outputs(outs, manifest) == []


def test_parquet_output_is_byte_stable(tmp_path):
    """The diff relies on identical input producing identical bytes; otherwise
    every run re-publishes every parquet (correct, just slower and dearer)."""
    import pandas as pd
    from pipelines.stock_pipeline import StockDataPipeline
    df = pd.DataFrame({"adjClose": [1.0, 2.0]},
                      index=pd.to_datetime(["2026-01-01", "2026-01-02"]))
    a, b = str(tmp_path / "a.parquet"), str(tmp_path / "b.parquet")
    StockDataPipeline._write_parquet(df, a)
    StockDataPipeline._write_parquet(df, b)
    assert publish.sha256_file(a) == publish.sha256_file(b)


def test_publish_refuses_unversioned_live_bucket(aws, tmp_path):
    aws.create_bucket(Bucket="state")
    aws.create_bucket(Bucket="live")
    with pytest.raises(RuntimeError, match="versioning"):
        publish.publish(aws, "state", "live", "r1")


class FlakyCopies:
    """Wraps an S3 client; copy_object raises for the named keys."""

    def __init__(self, client, fail_keys):
        self._client, self.fail_keys, self.copied = client, set(fail_keys), []

    def __getattr__(self, name):
        return getattr(self._client, name)

    def copy_object(self, **kwargs):
        if kwargs["Key"] in self.fail_keys:
            raise RuntimeError(f"copy of {kwargs['Key']} blew up")
        self.copied.append(kwargs["Key"])
        return self._client.copy_object(**kwargs)


def stage_run(client, tmp_path, run_id, contents):
    store = S3Store("state", client)
    store.put_json(run_key(run_id, "report.json"), {"run_id": run_id, "counts": {}})
    outs = make_outputs(tmp_path, contents)
    publish.stage_changed(client, "state", run_id,
                          publish.diff_outputs(outs, store.get_json(LIVE_MANIFEST, {})))


def manifest_files(client, run_id):
    manifest = S3Store("state", client).get_json(run_key(run_id, "publish-manifest.json"))
    return {f["key"]: f for f in manifest["files"]}


def test_crash_mid_group_then_republish_keeps_original_previous_versions(buckets, tmp_path):
    do_run(buckets, tmp_path, "r1", {"econ_data/cpi.parquet": "c1"})
    r1_version = buckets.head_object(Bucket="live", Key="econ_data/cpi.parquet")["VersionId"]
    stage_run(buckets, tmp_path, "r2", {"econ_data/cpi.parquet": "c2",
                                        "econ_data/a.parquet": "a2",
                                        "econ_data/b.parquet": "b2"})
    flaky = FlakyCopies(buckets, {"econ_data/b.parquet"})
    with pytest.raises(RuntimeError, match="blew up"):
        publish.publish(flaky, "state", "live", "r2")
    files = manifest_files(buckets, "r2")
    assert set(files) == {"econ_data/cpi.parquet", "econ_data/a.parquet"}
    assert files["econ_data/cpi.parquet"]["previous_version"] == r1_version

    retry = FlakyCopies(buckets, set())
    result = publish.publish(retry, "state", "live", "r2")
    assert retry.copied == ["econ_data/b.parquet"]       # already-live keys skipped
    assert result["published"] == 1
    files = manifest_files(buckets, "r2")
    assert set(files) == {"econ_data/cpi.parquet", "econ_data/a.parquet",
                          "econ_data/b.parquet"}
    assert files["econ_data/cpi.parquet"]["previous_version"] == r1_version

    publish.rollback(buckets, "state", "live", "r2")
    assert live_body(buckets, "econ_data/cpi.parquet") == "c1"
    for key in ("econ_data/a.parquet", "econ_data/b.parquet"):
        with pytest.raises(buckets.exceptions.NoSuchKey):
            buckets.get_object(Bucket="live", Key=key)


def test_republish_of_live_run_copies_nothing_and_keeps_rollback(buckets, tmp_path):
    do_run(buckets, tmp_path, "r1", {"econ_data/cpi.parquet": "c1"})
    do_run(buckets, tmp_path, "r2", {"econ_data/cpi.parquet": "c2"})
    again = FlakyCopies(buckets, set())
    assert publish.publish(again, "state", "live", "r2")["published"] == 0
    assert again.copied == []
    publish.rollback(buckets, "state", "live", "r2")
    assert live_body(buckets, "econ_data/cpi.parquet") == "c1"


def test_rollback_restores_object_written_before_versioning(aws, tmp_path):
    aws.create_bucket(Bucket="state")
    aws.create_bucket(Bucket="live")
    aws.put_object(Bucket="live", Key="econ_data/cpi.parquet", Body=b"original")
    aws.put_bucket_versioning(Bucket="live",
                              VersioningConfiguration={"Status": "Enabled"})
    do_run(aws, tmp_path, "r1", {"econ_data/cpi.parquet": "c1"})
    entry = manifest_files(aws, "r1")["econ_data/cpi.parquet"]
    assert entry["previous_existed"] is True
    publish.rollback(aws, "state", "live", "r1")
    assert live_body(aws, "econ_data/cpi.parquet") == "original"


def test_rollback_of_older_run_refused_while_newer_run_is_live(buckets, tmp_path):
    do_run(buckets, tmp_path, "r1", {"econ_data/cpi.parquet": "c1"})
    do_run(buckets, tmp_path, "r2", {"econ_data/cpi.parquet": "c2"})
    with pytest.raises(RuntimeError, match="r2"):
        publish.rollback(buckets, "state", "live", "r1")
    assert live_body(buckets, "econ_data/cpi.parquet") == "c2"

    publish.rollback(buckets, "state", "live", "r2")       # latest first
    publish.rollback(buckets, "state", "live", "r1")       # now allowed
    with pytest.raises(buckets.exceptions.NoSuchKey):
        buckets.get_object(Bucket="live", Key="econ_data/cpi.parquet")


def test_rollback_force_overrides_the_newer_run_guard(buckets, tmp_path):
    do_run(buckets, tmp_path, "r1", {"econ_data/cpi.parquet": "c1"})
    do_run(buckets, tmp_path, "r2", {"econ_data/cpi.parquet": "c2"})
    publish.rollback(buckets, "state", "live", "r1", force=True)
    with pytest.raises(buckets.exceptions.NoSuchKey):
        buckets.get_object(Bucket="live", Key="econ_data/cpi.parquet")


def test_rollback_ignores_newer_runs_touching_other_keys(buckets, tmp_path):
    do_run(buckets, tmp_path, "r1", {"econ_data/cpi.parquet": "c1"})
    do_run(buckets, tmp_path, "r2", {"econ_data/gdp.parquet": "g2"})
    assert publish.rollback(buckets, "state", "live", "r1") == 1
