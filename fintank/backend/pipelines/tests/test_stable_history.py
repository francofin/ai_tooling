"""Prices and index history fetched from FMP stable, saved in the v3 shape.
Fakes only: no network."""
import json
import os

import pandas as pd
import pytest

from pipelines import stock_pipeline as sp
from pipelines.fmp_stable_shapes import HISTORY_ROW_CAP
from pipelines.tests.helpers import (load_fixture, price_rows,
                                     stable_history_get, write_constituents,
                                     write_price_json)

FULL, ADJ = "historical-price-eod/full", "historical-price-eod/dividend-adjusted"


def day_rows(newest, n):
    """n raw stable rows, one per calendar day, newest first."""
    days = pd.date_range(end=newest, periods=n)
    return [{"date": d.strftime("%Y-%m-%d"), "open": 1.0, "high": 1.0, "low": 1.0,
             "close": 1.0, "adjClose": 1.0, "volume": 10}
            for d in reversed(days)]


def saved(pipeline, sub, symbol):
    with open(f"{pipeline.json_dir('stock_prices', sub)}{symbol}_prices.json") as f:
        return json.load(f)["historical"]


def counting_ticks(pipeline):
    ticks = []
    pipeline.limiter = type("L", (), {"tick": lambda self: ticks.append(1)})()
    return ticks


def test_full_download_pages_past_5000_rows(pipeline):
    write_constituents(pipeline, "sp500_const", ["AAA"])
    rows = day_rows("2026-11-20", HISTORY_ROW_CAP + 300)
    pipeline._get, calls = stable_history_get({"AAA": rows})
    ticks = counting_ticks(pipeline)

    pipeline.fetch_stock_prices(from_date="1990-01-01",
                                constituent_keys=["sp500_const"])

    out = saved(pipeline, "sp500", "AAA")
    assert len(out) == 5300 and len({r["date"] for r in out}) == 5300
    assert out[0]["date"] == "2026-11-20" and "label" in out[0]
    # /full pages twice (5,000 then 300), /dividend-adjusted the same
    assert len(calls) == 4 and len(ticks) == 4
    assert [p.get("to") for path, p in calls if path == FULL][1] is not None
    assert all(p["from"] == "1990-01-01" for _, p in calls)


def test_incremental_window_uses_both_endpoints(pipeline):
    write_constituents(pipeline, "sp500_const", ["AAA"])
    write_price_json(pipeline, "sp500", "AAA", "2026-10-09")
    pipeline._get, calls = stable_history_get({"AAA": price_rows("2026-10-16", 45)})

    result = pipeline.fetch_stock_prices(from_date="1999-01-01",
                                         constituent_keys=["sp500_const"])

    assert result.detail["incremental"] == 1
    assert sorted(path for path, _ in calls) == [ADJ, FULL]
    assert all(p["from"] == "2026-09-29" for _, p in calls)
    assert len(saved(pipeline, "sp500", "AAA")) == 45


def test_restated_redownloads_full_history(pipeline):
    write_constituents(pipeline, "sp500_const", ["AAA"])
    write_price_json(pipeline, "sp500", "AAA", "2026-10-09")
    moved = [dict(r, adjClose=r["adjClose"] / 2) for r in price_rows("2026-10-16", 45)]
    pipeline._get, calls = stable_history_get({"AAA": moved})

    result = pipeline.fetch_stock_prices(from_date="1999-01-01",
                                         constituent_keys=["sp500_const"])

    assert result.detail["restated"] == 1
    assert [p["from"] for _, p in calls][2:] == ["1999-01-01"] * 2
    assert saved(pipeline, "sp500", "AAA")[0]["adjClose"] == moved[0]["adjClose"]


def test_empty_stable_history_raises(pipeline):
    write_constituents(pipeline, "sp500_const", ["AAA"])
    pipeline._get, _ = stable_history_get({"AAA": []})
    result = pipeline.fetch_stock_prices(from_date="1999-01-01",
                                         constituent_keys=["sp500_const"])
    assert result.failed == 1
    with pytest.raises(ValueError, match="empty 'historical' payload"):
        pipeline._full_price_payload("AAA", "1999-01-01")


def test_none_from_date_means_start_date(pipeline):
    pipeline._get, calls = stable_history_get({"AAA": price_rows("2026-10-16", 5)})
    pipeline._full_price_payload("AAA", None)
    assert all(p["from"] == sp.START_DATE for _, p in calls)


def test_non_list_body_raises_and_ticks_once(pipeline):
    ticks = counting_ticks(pipeline)
    pipeline._get = lambda url, timeout=30: {"Error Message": "nope"}
    with pytest.raises(ValueError):
        pipeline._stable_rows(FULL, symbol="AAA")
    assert len(ticks) == 1


def test_price_payload_matches_fixture_shape(pipeline):
    full, adj = load_fixture("px_full_aapl"), load_fixture("px_divadj_aapl")
    pipeline._get, _ = stable_history_get({"AAPL": full})
    rows = pipeline._stable_history(FULL, "AAPL", None)
    assert [r["date"] for r in rows] == sorted((r["date"] for r in full), reverse=True)
    assert adj  # fixture present for the join covered in test_fmp_stable_shapes


def test_index_backfill_and_update_on_stable(pipeline, monkeypatch):
    monkeypatch.setattr(sp.cfg, "INDEX_TICKERS",
                        {"tsx": {"ticker": "^GSPTSE", "full_name": "TSX"}})
    rows = day_rows("2026-11-20", 400)
    pipeline._get, calls = stable_history_get({"^GSPTSE": rows})

    assert pipeline.fetch_index_prices().saved == 1
    assert [(path, p["from"]) for path, p in calls] == [(FULL, sp.START_DATE)]

    daily = f"{pipeline.index_prices_dir}/daily/tsx_prices.parquet"
    df = pd.read_parquet(daily)
    assert set(sp.RAW_PRICE_COLS) <= set(df.columns) and "label" in df.columns
    assert len(df) == 400
    first_cols = list(df.columns)

    calls.clear()
    assert pipeline.fetch_index_prices().saved == 1
    assert [(path, p["from"]) for path, p in calls] == [(FULL, "2026-11-20")]
    assert list(pd.read_parquet(daily).columns) == first_cols


def _unchanged_after(pipeline, sub, before):
    assert saved(pipeline, sub, "AAA") == before


def _full_only_get(full_rows):
    """/full has rows but /dividend-adjusted is empty."""
    def _get(url, timeout=30):
        return full_rows if "/full" in url else []
    return _get


def test_missing_adjusted_series_fails_incremental_and_keeps_file(pipeline):
    write_constituents(pipeline, "sp500_const", ["AAA"])
    write_price_json(pipeline, "sp500", "AAA", "2026-10-09")
    before = saved(pipeline, "sp500", "AAA")
    pipeline._get = _full_only_get(price_rows("2026-10-16", 45))

    result = pipeline.fetch_stock_prices(from_date="1999-01-01",
                                         constituent_keys=["sp500_const"])

    assert result.failed == 1 and result.saved == 0
    _unchanged_after(pipeline, "sp500", before)


def test_missing_adjusted_series_fails_full_download(pipeline):
    write_constituents(pipeline, "sp500_const", ["AAA"])
    pipeline._get = _full_only_get(price_rows("2026-10-16", 45))

    result = pipeline.fetch_stock_prices(from_date="1999-01-01",
                                         constituent_keys=["sp500_const"])

    assert result.failed == 1
    with pytest.raises(ValueError, match="no dividend-adjusted rows"):
        pipeline._full_price_payload("AAA", "1999-01-01")
    assert not os.path.exists(
        f"{pipeline.json_dir('stock_prices', 'sp500')}AAA_prices.json")


def test_missing_adjusted_series_fails_restated_path_and_keeps_file(pipeline):
    write_constituents(pipeline, "sp500_const", ["AAA"])
    write_price_json(pipeline, "sp500", "AAA", "2026-10-09")
    before = saved(pipeline, "sp500", "AAA")
    moved = [dict(r, close=r["close"] / 2) for r in price_rows("2026-10-16", 45)]
    adjusted = [dict(r, adjClose=r["adjClose"] / 2) for r in moved]

    def _get(url, timeout=30):
        if "/dividend-adjusted" in url:
            # incremental window answers; the full re-download comes back empty
            return adjusted if "from=2026-09-29" in url else []
        return moved
    pipeline._get = _get

    result = pipeline.fetch_stock_prices(from_date="1999-01-01",
                                         constituent_keys=["sp500_const"])

    assert result.failed == 1
    _unchanged_after(pipeline, "sp500", before)


def test_exactly_one_full_page_then_empty_page_stops(pipeline):
    rows = day_rows("2026-11-20", HISTORY_ROW_CAP)
    assert rows[-1]["date"] > "1990-01-01"
    pipeline._get, calls = stable_history_get({"AAA": rows})
    ticks = counting_ticks(pipeline)

    out = pipeline._stable_history(FULL, "AAA", "1990-01-01")

    assert len(out) == HISTORY_ROW_CAP and out[0]["date"] == "2026-11-20"
    assert len(calls) == 2 and len(ticks) == 2  # the full page, then the empty one


def test_page_not_older_than_previous_to_stops(pipeline):
    page_a = day_rows("2026-11-20", HISTORY_ROW_CAP)
    page_b = day_rows("2026-12-20", HISTORY_ROW_CAP)  # oldest is later than A's
    calls = []

    def get(url, timeout=30):
        calls.append(url)
        assert len(calls) < 10, "stuck-page guard did not stop the loop"
        return page_a if len(calls) % 2 else page_b
    pipeline._get = get
    counting_ticks(pipeline)

    out = pipeline._stable_history(FULL, "AAA", "1990-01-01")

    assert len(calls) == 2
    assert len(out) == len({r["date"] for r in page_a + page_b})


def test_failed_stable_rows_call_still_ticks(pipeline):
    ticks = counting_ticks(pipeline)

    def boom(url, timeout=30):
        raise RuntimeError("network down")
    pipeline._get = boom
    with pytest.raises(RuntimeError):
        pipeline._stable_rows(FULL, symbol="AAA")
    assert len(ticks) == 1


def test_get_text_decodes_utf8_without_charset(monkeypatch):
    raw = "symbol,companyName\nDB1,Deutsche Börse\n".encode("utf-8")

    class Resp:
        content = raw

        def raise_for_status(self):
            pass

        @property
        def text(self):  # what requests does for text/csv with no charset
            return raw.decode("iso-8859-1")

    monkeypatch.setattr(sp.requests, "get", lambda url, timeout=60: Resp())
    monkeypatch.setattr(sp.StockDataPipeline, "bytes_downloaded", 0)
    assert "Deutsche Börse" in sp.StockDataPipeline._get_text("https://fmp/x")
