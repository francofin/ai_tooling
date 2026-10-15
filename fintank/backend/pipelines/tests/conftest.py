import boto3
import pytest
from moto import mock_aws

from pipelines import stock_pipeline as sp

LEAKY_ENV = ("PIPELINE_DATA_ROOT", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
             "AWS_SESSION_TOKEN", "AWS_BUCKET_NAME", "AWS_PROFILE",
             "SNS_TOPIC_ARN", "STATE_BUCKET", "LIVE_BUCKET", "ALWAYS_HOLD")


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Nothing real leaks in from the shell or backend/.env. Returns a path to
    a .env that does not exist, for StockDataPipeline(env_path=...)."""
    for name in LEAKY_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FMP_API", "test-fmp-key")
    monkeypatch.setenv("FRED_API", "test-fred-key")
    return tmp_path / "no.env"


@pytest.fixture
def pipeline(clean_env, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    p = sp.StockDataPipeline(root=str(root), env_path=str(clean_env))
    p.limiter = sp.RateLimiter(max_calls=10**9, pause=0)
    return p


@pytest.fixture
def aws(clean_env, monkeypatch):
    """moto-backed AWS with fake credentials. Yields an S3 client."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        yield boto3.client("s3", region_name="us-east-1")
