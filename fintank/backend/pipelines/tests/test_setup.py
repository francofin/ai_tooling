import os

from pipelines import stock_pipeline as sp


def test_root_defaults_to_class_files(clean_env):
    p = sp.StockDataPipeline(env_path=str(clean_env))
    assert p.root == os.path.join(sp.BACKEND_DIR, "class_files")


def test_root_from_environment(clean_env, monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_DATA_ROOT", str(tmp_path))
    assert sp.StockDataPipeline(env_path=str(clean_env)).root == str(tmp_path)


def test_explicit_root_beats_environment(clean_env, monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_DATA_ROOT", "/somewhere/else")
    p = sp.StockDataPipeline(root=str(tmp_path), env_path=str(clean_env))
    assert p.root == str(tmp_path)


def test_bucket_defaults_to_live_bucket(clean_env):
    assert sp.StockDataPipeline(env_path=str(clean_env)).bucket == "thetradingfloor"


def test_s3_uses_default_chain_without_keys(clean_env, monkeypatch):
    calls = []
    monkeypatch.setattr(sp.boto3, "client",
                        lambda *a, **kw: calls.append((a, kw)) or object())
    sp.StockDataPipeline(env_path=str(clean_env)).s3
    assert calls == [(("s3",), {"region_name": "us-east-1"})]


def test_s3_uses_keys_when_present(clean_env, monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "id")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    calls = []
    monkeypatch.setattr(sp.boto3, "client",
                        lambda *a, **kw: calls.append((a, kw)) or object())
    sp.StockDataPipeline(env_path=str(clean_env)).s3
    assert calls[0][1]["aws_access_key_id"] == "id"
