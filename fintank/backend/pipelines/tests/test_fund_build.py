"""build_fund_finder: fund_holdings/ + fund_info/ on disk -> fund_data/. No network."""
import csv
import io
import json
import os

import pandas as pd
import pytest

from pipelines import runner
from pipelines import stock_pipeline as sp
from pipelines.fund_universe import bucket_of, build_universe
from pipelines.outputs import DATASET_ORDER
from pipelines.tests.helpers import load_fixture

RY = "CA7800871021"


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def stage_inputs(p, crosscheck=True):
    """What fetch_fund_holdings / fetch_fund_info leave on disk."""
    rows = list(csv.DictReader(io.StringIO(load_fixture("profile_bulk_funds", "csv"))))
    funds, _ = build_universe(rows)
    h = p.fund_holdings_dir
    _write(os.path.join(h, "_universe.json"), funds)
    _write(os.path.join(h, "_profile_slim.json"),
           [{k: r.get(k) for k in sp.StockDataPipeline._SLIM_KEYS} for r in rows])
    for sym, name in (("XIU.TO", "xiu"), ("XEQT.TO", "xeqt"), ("VEA", "vea"),
                      ("AGG", "agg")):
        _write(os.path.join(h, f"{sym}.json"), load_fixture(f"etf_holdings_{name}"))
    # A fund that left the universe: only its own file, nobody holds it.
    _write(os.path.join(h, "GONE.json"),
           [{"asset": "AAPL", "isin": "US0378331005", "weightPercentage": 100.0}])
    if crosscheck:
        _write(os.path.join(h, "_crosscheck", "RY.TO.json"),
               load_fixture("etf_asset_exposure_ry"))
    _write(os.path.join(p.fund_info_dir, "XIU.TO.json"), load_fixture("etf_info_xiu"))
    return funds


def test_build_writes_all_files(pipeline):
    funds = stage_inputs(pipeline)
    result = pipeline.build_fund_finder()
    assert result.name == "build_fund_finder"
    assert result.failed == 0 and result.saved == 1

    d = pipeline.fund_data_dir
    assert d == os.path.join(pipeline.root, "fund_data")
    names = sorted(os.listdir(os.path.join(d, "exposure")))
    assert names == [f"{i:02d}.parquet" for i in range(64)]
    assert os.path.isfile(os.path.join(d, "funds.parquet"))
    assert os.path.isfile(os.path.join(d, "isin_map.parquet"))

    import pyarrow as pa
    import pyarrow.parquet as pq
    schemas = {str(pq.read_schema(os.path.join(d, "exposure", n)).remove_metadata())
               for n in names}
    assert len(schemas) == 1                                  # empty buckets too
    schema = pq.read_schema(os.path.join(d, "exposure", names[0]))
    assert schema.field("company_id").type == pa.string()
    assert schema.field("via").type == pa.string()
    assert any(pq.read_metadata(os.path.join(d, "exposure", n)).num_rows == 0
               for n in names)                                # fixture has empty buckets

    total = 0
    for name in names:
        df = pd.read_parquet(os.path.join(d, "exposure", name))
        assert list(df.columns) == ["company_id", "fund", "weight", "via", "bucket"]
        assert all(bucket_of(c) == int(name[:2]) for c in df.company_id)
        assert (df.bucket == int(name[:2])).all()
        total += len(df)
    assert total == result.detail["rows"] > 0

    fdf = pd.read_parquet(os.path.join(d, "funds.parquet"))
    assert sorted(fdf.symbol) == sorted(f["symbol"] for f in funds)   # GONE excluded
    xiu = fdf.set_index("symbol").loc["XIU.TO"]
    assert xiu.mer == 0.18 and xiu.issuer == "BlackRock" and xiu.asset_class == "Equity"
    imap = pd.read_parquet(os.path.join(d, "isin_map.parquet"))
    ry = imap.set_index("symbol").loc["RY.TO"]
    assert ry.company_id == RY and ry["name"] and ry.is_adr in (False, 0)


def test_build_detail(pipeline):
    stage_inputs(pipeline)
    detail = pipeline.build_fund_finder().detail
    for key in ("funds", "funds_with_rows", "rows", "weight_sum_outside", "unexpanded",
                "deep_chains", "xeqt_asset_rows", "adrs", "adrs_linked", "unlinked"):
        assert key in detail
    assert detail["adr_link_pct"] == pytest.approx(75.0)          # 3 of 4 fixture ADRs
    assert detail["adr_pairs"]["TSM"] == {"adr": "TW0002330008", "home": "TW0002330008"}
    assert detail["adr_pairs"]["NVO"]["adr"] == detail["adr_pairs"]["NVO"]["home"]
    # FMP lists XIU.TO 9.43, ZEB.TO 19.8 (no holdings saved here), VEA 0.89.
    cc = detail["crosscheck"]["RY.TO"]
    assert cc["in_universe"] == 3
    assert cc["present_pct"] == pytest.approx(200 / 3)
    assert cc["weight_ok_pct"] == pytest.approx(200 / 3)


def test_crosscheck_skips_funds_outside_universe(pipeline):
    stage_inputs(pipeline, crosscheck=False)
    _write(os.path.join(pipeline.fund_holdings_dir, "_crosscheck", "AAPL.json"),
           [{"symbol": "NOTAFUND", "asset": "AAPL", "weightPercentage": 5.0}])
    cc = pipeline.build_fund_finder().detail["crosscheck"]
    assert cc == {"AAPL": {"in_universe": 0, "present_pct": 0.0, "weight_ok_pct": 0.0}}


def test_build_without_fund_info_still_writes(pipeline):
    stage_inputs(pipeline)
    import shutil
    shutil.rmtree(pipeline.fund_info_dir)
    result = pipeline.build_fund_finder()
    assert result.failed == 0
    fdf = pd.read_parquet(os.path.join(pipeline.fund_data_dir, "funds.parquet"))
    assert fdf.mer.isna().all()


def test_build_exception_records_failure_and_writes_nothing(pipeline, capsys):
    # No _universe.json at all.
    result = pipeline.build_fund_finder()
    assert result.failed == 1 and result.attempted == 1
    assert not os.path.exists(pipeline.fund_data_dir)
    assert "build_fund_finder" in capsys.readouterr().out


def test_build_error_message_is_redacted(pipeline, monkeypatch, capsys):
    stage_inputs(pipeline)

    def boom(*a, **kw):
        raise RuntimeError("GET https://x/stable/etf?apikey=SECRET123 failed")
    monkeypatch.setattr(sp, "build_lookup", boom)
    result = pipeline.build_fund_finder()
    assert result.failed == 1
    out = capsys.readouterr().out
    assert "SECRET123" not in out and "apikey=***" in out
    assert not os.path.exists(pipeline.fund_data_dir)


def test_build_stage_registered():
    i = runner.BUILD_STAGES.index("build_index_attribution")
    assert runner.BUILD_STAGES[i + 1] == "build_fund_finder"
    assert DATASET_ORDER[DATASET_ORDER.index("attribution") + 1] == "fund_finder"

