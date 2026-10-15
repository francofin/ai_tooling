import os

from pipelines import stock_pipeline as sp
from pipelines.tests.helpers import write_constituents, write_price_json


def test_build_price_parquets_counts_files(pipeline):
    write_price_json(pipeline, "sp500", "AAA", "2026-10-09")
    folder = pipeline.json_dir("stock_prices", "sp500")
    with open(f"{folder}BAD_prices.json", "w") as f:
        f.write("{not json")
    result = pipeline.build_price_parquets(sub_universes=["sp500"])
    assert result.name == "build_price_parquets"
    assert (result.saved, result.failed) == (1, 1)
    assert result.failed_items == ["sp500/BAD"]
    assert result.detail["sp500"] == {"saved": 1, "failed": 1}


def test_build_factor_metrics_reports_stale_rows(pipeline):
    write_price_json(pipeline, "sp500", "NEW", "2026-10-09")
    write_price_json(pipeline, "sp500", "OLD", "2020-01-10")
    pipeline.build_price_parquets(sub_universes=["sp500"])
    result = pipeline.build_factor_metrics(sub_universes=["sp500"])
    assert result.name == "build_factor_metrics"
    assert result.detail["lists"]["sp500"] == {"rows": 2, "skipped": 0, "stale": 1}
    assert result.saved == 1


def test_build_factor_metrics_counts_empty_list_as_failed(pipeline):
    os.makedirs(pipeline.price_parquet_dir("daily", "nas"), exist_ok=True)
    result = pipeline.build_factor_metrics(sub_universes=["nas"])
    assert (result.saved, result.failed) == (0, 1)


def test_build_profile_aggregate_without_profiles_fails(pipeline):
    result = pipeline.build_profile_aggregate()
    assert (result.name, result.failed) == ("build_profile_aggregate", 1)


def test_build_contr_to_var_records_missing_prices(pipeline, monkeypatch):
    monkeypatch.setattr(sp.cfg, "CONSTITUENT_PROXY_ETFS", {"sp500_const": "SPY"})
    write_constituents(pipeline, "sp500_const", ["AAA", "BBB"])
    result = pipeline.build_contr_to_var()
    assert (result.name, result.failed, result.failed_items) == (
        "build_contr_to_var", 1, ["sp500"])


def test_modal_last_dates(pipeline):
    write_price_json(pipeline, "sp500", "AAA", "2026-10-09")
    write_price_json(pipeline, "sp500", "BBB", "2026-10-09")
    write_price_json(pipeline, "sp500", "CCC", "2026-10-08")
    dates = pipeline.modal_last_dates()
    assert dates["sp500"]["modal_last_date"] == "2026-10-09"
    assert dates["sp500"]["files"] == 3
    assert dates["nas"] == {"files": 0, "modal_last_date": None,
                            "newest": None, "sampled": 0}
