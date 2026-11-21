"""Constituents and the ETF list fetched from FMP stable, saved in the v3 shape.
Fakes only: no network."""
import csv
import io
import json

import pytest

from pipelines import stock_pipeline as sp
from pipelines.stock_pipeline import FetchHTTPError
from pipelines.tests.helpers import load_fixture, write_constituents


def counting_ticks(pipeline):
    ticks = []
    pipeline.limiter = type("L", (), {"tick": lambda self: ticks.append(1)})()
    return ticks


def test_refresh_constituents_on_stable(pipeline, monkeypatch):
    monkeypatch.setattr(sp.cfg, "CONSTITUENT_PROXY_ETFS", {"sp500_const": "SPY"})
    raw = load_fixture("etf_holdings_spy")
    urls = []

    def get(url, timeout=30):
        urls.append(url)
        return raw
    pipeline._get = get
    ticks = counting_ticks(pipeline)
    result = pipeline.refresh_constituents(include_etf_list=False)
    assert "/stable/etf/holdings?symbol=SPY" in urls[0] and len(urls) == 1
    assert len(ticks) == 1
    with open(pipeline.constituents_path("sp500_const")) as f:
        saved = json.load(f)
    expect = [r for r in raw if r["asset"]]
    assert len(saved) == len(expect)
    assert set(saved[0]) == {"asset", "name", "isin", "cusip", "sharesNumber",
                             "weightPercentage", "marketValue", "updated"}
    day = expect[0]["updatedAt"][:10]
    assert result.detail["lists"]["sp500_const"]["snapshot"] == day


def test_refresh_constituents_stable_shrink_guard(pipeline, monkeypatch):
    monkeypatch.setattr(sp.cfg, "CONSTITUENT_PROXY_ETFS", {"sp500_const": "SPY"})
    write_constituents(pipeline, "sp500_const", [f"S{i}" for i in range(10)])
    pipeline._get = lambda url, timeout=30: [
        {"symbol": "SPY", "asset": "S1", "weightPercentage": 1, "updatedAt": "2026-11-14 02:04:06"}]
    result = pipeline.refresh_constituents(include_etf_list=False)
    info = result.detail["lists"]["sp500_const"]
    assert info["status"] == "kept" and "shrank" in info["error"]


def test_refresh_constituents_empty_holdings_fails(pipeline, monkeypatch):
    monkeypatch.setattr(sp.cfg, "CONSTITUENT_PROXY_ETFS", {"sp500_const": "SPY"})
    pipeline._get = lambda url, timeout=30: [{"symbol": "SPY", "asset": ""}]
    info = pipeline.refresh_constituents(
        include_etf_list=False).detail["lists"]["sp500_const"]
    assert info["status"] == "kept"
    assert "no rows with an 'asset' symbol" in info["error"]


def _csv(rows, header=("symbol", "price", "exchangeFullName", "exchange")):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    w.writerows(rows)
    return out.getvalue()


def test_profile_bulk_stops_at_empty_part(pipeline):
    parts = [_csv([["A", "1.5", "NASDAQ", "NASDAQ"]]),
             _csv([["B", "", "NASDAQ", "NASDAQ"]]),
             _csv([])]
    urls = []

    def get_text(url, timeout=30):
        urls.append(url)
        return parts[len(urls) - 1]
    pipeline._get_text = get_text
    ticks = counting_ticks(pipeline)
    rows = pipeline._profile_bulk()
    assert [r["symbol"] for r in rows] == ["A", "B"]
    assert len(urls) == 3 and len(ticks) == 3
    assert [u.rsplit("part=", 1)[1].split("&")[0] for u in urls] == ["0", "1", "2"]


def test_profile_bulk_stops_at_400_after_first_part(pipeline):
    calls = []

    def get_text(url, timeout=30):
        calls.append(url)
        if len(calls) == 2:
            raise FetchHTTPError("400 Client Error", 400)
        return _csv([["A", "1", "NASDAQ", "NASDAQ"]])
    pipeline._get_text = get_text
    ticks = counting_ticks(pipeline)
    assert [r["symbol"] for r in pipeline._profile_bulk()] == ["A"]
    assert len(ticks) == 2


def test_profile_bulk_part_zero_error_propagates(pipeline):
    def get_text(url, timeout=30):
        raise FetchHTTPError("400 Client Error", 400)
    pipeline._get_text = get_text
    counting_ticks(pipeline)
    with pytest.raises(FetchHTTPError):
        pipeline._profile_bulk()


def test_profile_bulk_other_error_mid_sequence_propagates(pipeline):
    calls = []

    def get_text(url, timeout=30):
        calls.append(1)
        if len(calls) >= 2:
            raise FetchHTTPError("500 Server Error", 500)
        return _csv([["A", "1", "NASDAQ", "NASDAQ"]])
    pipeline._get_text = get_text
    counting_ticks(pipeline)
    with pytest.raises(FetchHTTPError):
        pipeline._profile_bulk()


@pytest.fixture
def sleeps(monkeypatch):
    slept = []
    monkeypatch.setattr(sp, "_sleep", slept.append)
    return slept


@pytest.mark.parametrize("error", [RuntimeError("connection reset"),
                                   FetchHTTPError("429 Too Many", 429),
                                   FetchHTTPError("503 Unavailable", 503)])
def test_profile_bulk_retries_a_transient_failure_once(pipeline, sleeps, error):
    attempts = []

    def get_text(url, timeout=30):
        attempts.append(url)
        if len(attempts) == 1:
            raise error
        return _csv([["A", "1", "N", "N"]]) if len(attempts) == 2 else _csv([])
    pipeline._get_text = get_text
    ticks = counting_ticks(pipeline)

    assert [r["symbol"] for r in pipeline._profile_bulk()] == ["A"]
    assert len(attempts) == 3 and len(ticks) == 3 and len(sleeps) == 1
    assert "part=0" in attempts[0] and "part=0" in attempts[1]


def test_profile_bulk_two_failures_raise(pipeline, sleeps):
    attempts = []

    def get_text(url, timeout=30):
        attempts.append(1)
        raise RuntimeError("connection reset")
    pipeline._get_text = get_text
    ticks = counting_ticks(pipeline)
    with pytest.raises(RuntimeError, match="connection reset"):
        pipeline._profile_bulk()
    assert len(attempts) == 2 and len(ticks) == 2 and len(sleeps) == 1


def test_profile_bulk_400_after_first_part_is_not_retried(pipeline, sleeps):
    attempts = []

    def get_text(url, timeout=30):
        attempts.append(1)
        if len(attempts) == 2:
            raise FetchHTTPError("400 Client Error", 400)
        return _csv([["A", "1", "N", "N"]])
    pipeline._get_text = get_text
    counting_ticks(pipeline)
    assert len(pipeline._profile_bulk()) == 1
    assert len(attempts) == 2 and sleeps == []


def test_profile_bulk_client_error_on_part_zero_not_retried(pipeline, sleeps):
    def get_text(url, timeout=30):
        raise FetchHTTPError("404 Not Found", 404)
    pipeline._get_text = get_text
    counting_ticks(pipeline)
    with pytest.raises(FetchHTTPError):
        pipeline._profile_bulk()
    assert sleeps == []


def test_etf_list_request_retried_once_then_succeeds(pipeline, sleeps):
    attempts = []

    def get(url, timeout=30):
        attempts.append(url)
        if len(attempts) == 1:
            raise FetchHTTPError("502 Bad Gateway", 502)
        return [{"symbol": "A", "name": "a"}]
    pipeline._get = get
    ticks = counting_ticks(pipeline)
    assert pipeline._etf_list_request() == [{"symbol": "A", "name": "a"}]
    assert len(attempts) == 2 and len(ticks) == 2 and len(sleeps) == 1


def test_etf_list_two_failures_keep_old_list(pipeline, sleeps, monkeypatch):
    monkeypatch.setattr(sp.cfg, "CONSTITUENT_PROXY_ETFS", {})
    attempts = []

    def get(url, timeout=30):
        attempts.append(1)
        raise RuntimeError("connection reset")
    pipeline._get = get
    pipeline._get_text = lambda url, timeout=30: _csv([])
    counting_ticks(pipeline)
    info = pipeline.refresh_constituents().detail["lists"]["etf_data"]
    assert info["status"] == "kept" and len(attempts) == 2


def test_profile_bulk_part_cap(pipeline):
    pipeline._get_text = lambda url, timeout=30: _csv([["A", "1", "N", "N"]])
    counting_ticks(pipeline)
    with pytest.raises(RuntimeError, match="parts"):
        pipeline._profile_bulk()


def test_refresh_etf_list_on_stable(pipeline, monkeypatch):
    monkeypatch.setattr(sp.cfg, "CONSTITUENT_PROXY_ETFS", {})
    pipeline._get = lambda url, timeout=30: [
        {"symbol": "SGOV", "name": "iShares 0-3 Month"}, {"symbol": "XXX", "name": "x"}]
    texts = [_csv([["SGOV", "100.5", "New York Stock Exchange Arca", "AMEX"],
                   ["XXX", "1", "Deutsche Boerse", "XETRA"]]), _csv([])]
    pipeline._get_text = lambda url, timeout=30: texts.pop(0)
    counting_ticks(pipeline)
    result = pipeline.refresh_constituents()
    assert result.detail["lists"]["etf_data"]["status"] == "updated"
    with open(pipeline.constituents_path("etf_data")) as f:
        assert json.load(f) == [{"symbol": "SGOV", "name": "iShares 0-3 Month",
                                 "price": 100.5,
                                 "exchange": "New York Stock Exchange Arca",
                                 "exchangeShortName": "AMEX", "type": "etf"}]


def test_refresh_etf_list_no_filter_match_fails(pipeline, monkeypatch):
    monkeypatch.setattr(sp.cfg, "CONSTITUENT_PROXY_ETFS", {})
    pipeline._get = lambda url, timeout=30: [{"symbol": "XXX", "name": "x"}]
    texts = [_csv([["XXX", "1", "Deutsche Boerse", "XETRA"]]), _csv([])]
    pipeline._get_text = lambda url, timeout=30: texts.pop(0)
    counting_ticks(pipeline)
    info = pipeline.refresh_constituents().detail["lists"]["etf_data"]
    assert info["status"] == "kept" and "exchange filter matched no ETFs" in info["error"]
