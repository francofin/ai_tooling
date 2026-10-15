"""backend/.env holds a legacy AWS key: reading it must never export it, or
boto3 would use it instead of AWS_PROFILE on Franc's terminal."""
import os

from pipelines import cli, news
from pipelines import stock_pipeline as sp

LEGACY_ENV = ("AWS_ACCESS_KEY_ID=legacy-key\nAWS_SECRET_ACCESS_KEY=legacy-secret\n"
              "FMP_API=file-fmp\nSERPAPI_KEY=file-serp\n")


def test_pipeline_reads_env_file_without_exporting_it(clean_env, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(LEGACY_ENV)
    p = sp.StockDataPipeline(root=str(tmp_path / "data"), env_path=str(env_file))
    assert "AWS_ACCESS_KEY_ID" not in os.environ
    assert "AWS_SECRET_ACCESS_KEY" not in os.environ
    assert p.aws_key == "legacy-key"          # still there for the notebooks' upload_*
    assert p.fmp_api == "test-fmp-key"        # the environment wins over the file


def test_cmd_news_reads_env_file_without_exporting_it(clean_env, tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(LEGACY_ENV)
    monkeypatch.setattr(sp, "BACKEND_DIR", str(tmp_path))
    monkeypatch.setenv("PIPELINE_DATA_ROOT", str(tmp_path / "data"))
    seen = {}

    class Report:
        def summary(self):
            return "ok"

    def fake_run_news(run_id, fmp_key, serp_key, *args, **kwargs):
        seen.update(fmp=fmp_key, serp=serp_key,
                    aws=os.environ.get("AWS_ACCESS_KEY_ID"))
        return Report()

    monkeypatch.setattr(news, "run_news", fake_run_news)
    assert cli.main(["news", "--dry-run"]) == 0
    assert seen == {"fmp": "test-fmp-key", "serp": "file-serp", "aws": None}
    assert "AWS_ACCESS_KEY_ID" not in os.environ
