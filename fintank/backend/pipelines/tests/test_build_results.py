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


def _attribution_fixture(p, monkeypatch, n=300, end="2026-11-13"):
    """Two lists with priced members, sectors and proxy-ETF prices."""
    import json

    import numpy as np
    import pandas as pd

    monkeypatch.setattr(sp.cfg, "CONSTITUENT_PROXY_ETFS",
                        {"sp500_const": "SPY", "nas_const": "QQQ"})
    dates = pd.bdate_range(end=end, periods=n)

    def write_prices(sub, symbol, start, stop):
        folder = p.price_parquet_dir("daily", sub)
        os.makedirs(folder, exist_ok=True)
        close = np.linspace(start, stop, n)
        frame = pd.DataFrame({"close": close, "adjClose": close},
                             index=dates.strftime("%Y-%m-%d"))
        frame.index.name = "date"
        frame.to_parquet(os.path.join(folder, f"{symbol}_prices.parquet"))

    members = {"sp500": {"AAA": 60.0, "BBB": 40.0}, "nas": {"CCC": 70.0, "DDD": 30.0}}
    for sub, weights in members.items():
        path = p.constituents_path(f"{sub}_const")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump([{"asset": s, "weightPercentage": w, "updated": f"{end} 15:00:00"}
                       for s, w in weights.items()], f)
        for i, s in enumerate(weights):
            write_prices(sub, s, 100.0, 120.0 - 30 * i)
        os.makedirs(p.factor_metrics_dir, exist_ok=True)
        pd.DataFrame({"symbol": list(weights), "sector": ["Tech", "Energy"]}).to_parquet(
            os.path.join(p.factor_metrics_dir, f"{sub}_metrics_returns.parquet"))
    for etf in ("SPY", "QQQ"):
        write_prices("etfs", etf, 100.0, 110.0)
    return pd.Timestamp(end)


def test_attribution_stage_writes_one_parquet_per_list(pipeline, monkeypatch):
    import pandas as pd

    from pipelines.attribution import COLUMNS

    today = _attribution_fixture(pipeline, monkeypatch)
    result = pipeline.build_index_attribution(today=today)
    assert (result.name, result.saved, result.failed) == ("build_index_attribution", 2, 0)
    for sub in ("sp500", "nas"):
        out = pd.read_parquet(os.path.join(pipeline.attribution_dir, f"{sub}_attribution.parquet"))
        assert list(out.columns) == COLUMNS
        assert out[out.level == "index"].ref_symbol.iloc[0] == {"sp500": "SPY", "nas": "QQQ"}[sub]
        windows = result.detail[sub]["windows"]
        assert list(windows) == ["1W", "2W", "1M", "3M", "ytd", "1Y"]
        assert all(w["identity_error_pp"] < 1e-9 for w in windows.values())
        assert all(w["covered_weight_pct"] == 100.0 for w in windows.values())
        assert all(w["non_finite"] == 0 for w in windows.values())
    assert result.detail["sp500"]["currency_basis"] == "USD"


def test_attribution_stage_keeps_old_parquet_when_a_list_has_no_prices(pipeline, monkeypatch):
    import shutil

    today = _attribution_fixture(pipeline, monkeypatch)
    os.makedirs(pipeline.attribution_dir, exist_ok=True)
    old = os.path.join(pipeline.attribution_dir, "nas_attribution.parquet")
    with open(old, "w") as f:
        f.write("last week")
    shutil.rmtree(pipeline.price_parquet_dir("daily", "nas"))
    result = pipeline.build_index_attribution(today=today)
    assert (result.saved, result.failed, result.failed_items) == (1, 1, ["nas"])
    with open(old) as f:
        assert f.read() == "last week"


def test_attribution_since_covers_one_year(pipeline, monkeypatch):
    today = _attribution_fixture(pipeline, monkeypatch, n=400)
    result = pipeline.build_index_attribution(constituent_keys=["sp500_const"], today=today)
    assert "1Y" in result.detail["sp500"]["windows"]


def test_attribution_is_a_build_stage_in_both_modes():
    from pipelines import runner
    assert "build_index_attribution" in runner.LEAN_STAGES
    assert "build_index_attribution" in runner.FULL_STAGES
    assert (runner.BUILD_STAGES.index("build_index_attribution")
            == runner.BUILD_STAGES.index("build_contr_to_var") + 1)
