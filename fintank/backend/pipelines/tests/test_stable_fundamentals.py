"""Quarterly statements fetched from FMP stable, saved in the v3 shape.
Fakes only: no network."""
import json

import pytest

from pipelines import pipeline_config as cfg
from pipelines.stock_pipeline import FetchHTTPError
from pipelines.tests.helpers import load_fixture, write_constituents

_PATHS = {"income-statement": "income_q_aapl",
          "balance-sheet-statement": "balance_q_aapl",
          "cash-flow-statement": "cashflow_q_aapl"}


def _install(pipeline, overrides=None):
    urls, ticks = [], []
    overrides = overrides or {}

    def get(url, timeout=30):
        urls.append(url)
        for path, fixture in _PATHS.items():
            if f"/stable/{path}?" in url:
                resp = overrides.get(path, load_fixture(fixture))
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"unexpected URL {url}")
    pipeline._get = get
    pipeline.limiter = type("L", (), {"tick": lambda self: ticks.append(1)})()
    return urls, ticks


def test_statements_driver_saves_v3_rows(pipeline):
    write_constituents(pipeline, "sp500_const", ["AAPL"])
    urls, ticks = _install(pipeline)
    result = pipeline.fetch_financial_statements(constituent_keys=["sp500_const"])
    assert (result.attempted, result.saved, result.failed) == (1, 1, 0)
    assert len(urls) == 3 and len(ticks) == 3
    for path in _PATHS:
        assert any(f"/stable/{path}?symbol=AAPL&period=quarter&limit=400&apikey=" in u
                   for u in urls)
    sub = pipeline.sub_universe_for("sp500_const")
    for dt, suffix in (("income_statements", "_income_statement.json"),
                       ("balance_sheet_statements", "_balance_sheet.json"),
                       ("cash_flow_statements", "_cash_flow.json")):
        with open(f"{pipeline.json_dir(dt, sub)}AAPL{suffix}") as f:
            saved = json.load(f)
        assert len(saved) == 8
        assert set(cfg.FIELD_MAPPINGS[dt]) <= set(saved[0])
        assert type(saved[0]["calendarYear"]) is str


def test_statements_402_counts_as_not_on_plan(pipeline):
    write_constituents(pipeline, "sp500_const", ["AAPL"])
    _install(pipeline, {"income-statement": FetchHTTPError("402 Payment Required", 402)})
    result = pipeline.fetch_financial_statements(constituent_keys=["sp500_const"])
    assert result.failed == 0
    assert result.detail["not_on_plan"] == {"sp500_const": 1}


def test_statements_empty_payload_fails(pipeline):
    write_constituents(pipeline, "sp500_const", ["AAPL"])
    _install(pipeline, {"balance-sheet-statement": []})
    result = pipeline.fetch_financial_statements(constituent_keys=["sp500_const"])
    assert result.failed == 1
    assert result.failed_items == ["sp500_const:AAPL"]


def test_statements_error_dict_fails(pipeline):
    write_constituents(pipeline, "sp500_const", ["AAPL"])
    _install(pipeline, {"cash-flow-statement": {"Error Message": "x"}})
    result = pipeline.fetch_financial_statements(constituent_keys=["sp500_const"])
    assert result.failed == 1


def _install_ttm(pipeline, overrides=None):
    urls, ticks = [], []
    overrides = overrides or {}

    def get(url, timeout=30):
        urls.append(url)
        for path, fixture in (("ratios-ttm", "ratios_ttm_aapl"),
                              ("key-metrics-ttm", "key_metrics_ttm_aapl")):
            if f"/stable/{path}?" in url:
                resp = overrides.get(path, load_fixture(fixture))
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"unexpected URL {url}")
    pipeline._get = get
    pipeline.limiter = type("L", (), {"tick": lambda self: ticks.append(1)})()
    return urls, ticks


def test_ttm_pair_two_calls_per_symbol(pipeline):
    write_constituents(pipeline, "sp500_const", ["AAPL", "MSFT"])
    urls, ticks = _install_ttm(pipeline)
    result = pipeline.fetch_ttm_ratios(constituent_keys=["sp500_const"])
    assert (result.attempted, result.saved, result.failed) == (2, 2, 0)
    assert len(urls) == 4 and len(ticks) == 4
    assert all("/stable/" in u for u in urls)
    sub = pipeline.sub_universe_for("sp500_const")
    n = 0
    for dt, suffix, mapping in (("ratios_ttm", "_ratios_ttm.json", "company_ratios_ttm"),
                                ("metrics_ttm", "_metrics_ttm.json", "company_metrics_ttm")):
        for sym in ("AAPL", "MSFT"):
            with open(f"{pipeline.json_dir(dt, sub)}{sym}{suffix}") as f:
                saved = json.load(f)
            assert isinstance(saved, list) and len(saved) == 1
            assert set(cfg.FIELD_MAPPINGS[mapping]) <= set(saved[0])
            n += 1
    assert n == 4


def test_ttm_empty_payload_fails_and_does_not_leak(pipeline):
    write_constituents(pipeline, "sp500_const", ["AAPL", "MSFT"])
    urls, _ = _install_ttm(pipeline, {"key-metrics-ttm": []})
    result = pipeline.fetch_ttm_ratios(constituent_keys=["sp500_const"])
    assert result.failed == 2 and result.saved == 0
    sub = pipeline.sub_universe_for("sp500_const")
    import os
    assert not os.path.exists(f"{pipeline.json_dir('ratios_ttm', sub)}AAPL_ratios_ttm.json")
    # a failed symbol leaves no memo: MSFT refetched both endpoints itself
    assert sum("symbol=MSFT" in u for u in urls) >= 2


def test_ttm_402_counts_as_not_on_plan(pipeline):
    write_constituents(pipeline, "sp500_const", ["AAPL"])
    _install_ttm(pipeline, {"ratios-ttm": FetchHTTPError("402 Payment Required", 402)})
    result = pipeline.fetch_ttm_ratios(constituent_keys=["sp500_const"])
    assert result.failed == 0
    assert result.detail["not_on_plan"] == {"sp500_const": 1}
