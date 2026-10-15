import json

import pytest
import requests

from pipelines import stock_pipeline as sp
from pipelines.tests.helpers import price_rows, write_constituents


def fake_get(routes):
    """Return a _get replacement: the first route substring found in the URL
    decides the response; an Exception value is raised."""
    def _get(url, timeout=30):
        for needle, response in routes.items():
            if needle in url:
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError(f"unexpected URL {url}")
    return _get


def test_fetch_stock_prices_counts_each_symbol(pipeline):
    write_constituents(pipeline, "sp500_const", ["AAA", "BBB", "BAD"])
    pipeline._get = fake_get({
        "/AAA?": {"symbol": "AAA", "historical": price_rows("2026-10-09", 5)},
        "/BBB?": {"symbol": "BBB", "historical": price_rows("2026-10-09", 5)},
        "/BAD?": requests.HTTPError("500"),
    })
    result = pipeline.fetch_stock_prices(constituent_keys=["sp500_const"])
    assert result.name == "fetch_stock_prices"
    assert (result.attempted, result.saved, result.failed) == (3, 2, 1)
    assert result.failed_items == ["sp500_const:BAD"]
    assert result.detail["manifests"]


def test_fetch_etf_prices_is_named_for_itself(pipeline):
    write_constituents(pipeline, "etf_data", ["SPY"])
    pipeline._get = fake_get({"/SPY?": {"historical": price_rows("2026-10-09", 3)}})
    assert pipeline.fetch_etf_prices().name == "fetch_etf_prices"


def test_dataset_fetchers_count_symbols(pipeline):
    write_constituents(pipeline, "sp500_const", ["AAA", "BAD"])
    pipeline._get = fake_get({
        "ratios-ttm/AAA": [{"peRatioTTM": 10}],
        "key-metrics-ttm/AAA": [{"marketCapTTM": 1}],
        "ratios-ttm/BAD": [],
    })
    result = pipeline.fetch_ttm_ratios(constituent_keys=["sp500_const"])
    assert result.name == "fetch_ttm_ratios"
    assert (result.saved, result.failed) == (1, 1)


def test_refresh_constituents_keeps_shrunk_list(pipeline, monkeypatch):
    monkeypatch.setattr(sp.cfg, "CONSTITUENT_PROXY_ETFS",
                        {"sp500_const": "SPY", "nas_const": "QQQ"})
    write_constituents(pipeline, "sp500_const", [f"S{i}" for i in range(10)])
    pipeline._get = fake_get({
        "etf-holder/SPY": [{"asset": "S1"}, {"asset": "S2"}],          # shrank 10 → 2
        "etf-holder/QQQ": [{"asset": "Q1"}, {"asset": "Q2"}],          # first time
    })
    result = pipeline.refresh_constituents(include_etf_list=False)
    lists = result.detail["lists"]
    assert lists["sp500_const"]["status"] == "kept"
    assert lists["sp500_const"]["previous"] == 10
    assert "shrank" in lists["sp500_const"]["error"]
    assert lists["nas_const"] == {"status": "updated", "previous": None,
                                  "new": 2, "error": None}
    assert (result.saved, result.failed) == (1, 1)
    with open(pipeline.constituents_path("sp500_const")) as f:
        assert len(json.load(f)) == 10                      # old file intact


def test_revenue_segments_buckets(pipeline, monkeypatch):
    monkeypatch.setattr(sp.cfg, "SEGMENTATION_CONSTITUENT_KEYS", ["sp500_const"])
    write_constituents(pipeline, "sp500_const", ["AAA", "NONE", "ERR"])
    pipeline._normalise_segmentation = lambda payload: (payload, "USD", [])
    pipeline._get = fake_get({
        "symbol=AAA": {"2025": {"iPhone": 1}},
        "symbol=NONE": [],
        "symbol=ERR": requests.HTTPError("502"),
    })
    result = pipeline.fetch_revenue_segments()
    assert result.name == "fetch_revenue_segments"
    assert (result.attempted, result.saved, result.no_data, result.failed) == (3, 1, 1, 1)
    assert result.failed_items == ["ERR"]


def test_index_prices_counts_indexes(pipeline, monkeypatch):
    monkeypatch.setattr(sp.cfg, "INDEX_TICKERS", {
        "sp500": {"ticker": "^GSPC", "full_name": "S&P 500"},
        "dead": {"ticker": "^DEAD", "full_name": "Dead"},
    })
    pipeline._get = fake_get({
        "^GSPC": {"historical": price_rows("2026-10-09", 30)},
        "^DEAD": requests.HTTPError("404"),
    })
    result = pipeline.fetch_index_prices()
    assert (result.name, result.saved, result.failed) == ("fetch_index_prices", 1, 1)
    assert result.failed_items == ["dead"]


def test_sector_history_counts_combos(pipeline, monkeypatch):
    monkeypatch.setattr(sp.cfg, "EXCHANGES", {"nasdaq": {"index_name": "NASDAQ"}})
    monkeypatch.setattr(sp.cfg, "SECTOR_NAMES", {"tech": "Technology", "energy": "Energy"})
    pipeline._get = fake_get({
        "sector=Technology": [{"date": "2026-10-09", "averageChange": 1.0}],
        "sector=Energy": [],
    })
    result = pipeline.fetch_sector_history()
    assert (result.attempted, result.saved, result.failed) == (2, 1, 1)


def test_fred_counts_series(pipeline):
    pipeline._get = fake_get({
        "series_id=DGS10": {"observations": [{"date": "2026-10-08", "value": "4.1"}]},
        "series_id=GDP": {"observations": [{"date": "2026-07-01", "value": "."}]},
    })
    result = pipeline.fetch_fred_series(series_ids=["DGS10", "GDP"])
    assert (result.name, result.saved, result.failed) == ("fetch_fred_series", 1, 1)
