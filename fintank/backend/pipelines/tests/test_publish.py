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
