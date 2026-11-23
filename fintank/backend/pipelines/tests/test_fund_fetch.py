"""Fund holdings / info fetch stages. Fakes only: no network."""
import json
import os

import pytest
from urllib.parse import parse_qs, urlparse

from pipelines import runner
from pipelines import stock_pipeline as sp
from pipelines.fund_universe import build_universe
from pipelines.stock_pipeline import FetchHTTPError
from pipelines.tests.helpers import load_fixture
from pipelines.tests.test_stable_constituents import counting_ticks

BULK = load_fixture("profile_bulk_funds", "csv")
CHECK = ["RY.TO", "TD.TO", "SHOP.TO", "AAPL", "MSFT"]


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(sp, "_sleep", lambda s: None)


def _funds():
    import csv
    import io
    return build_universe(list(csv.DictReader(io.StringIO(BULK))))[0]


def make_get(pipeline, fail=None, extra=None, empty=()):
    """Fake _get/_get_text; returns the list of (endpoint, symbol) requests."""
    calls = []
    fail = fail or {}
    extra = extra or {}

    def get_text(url, timeout=30):
        calls.append(("profile-bulk", None))
        return BULK if len([c for c in calls if c[0] == "profile-bulk"]) == 1 else ""

    def get(url, timeout=30):
        u = urlparse(url)
        endpoint = u.path.split("/stable/")[1]
        symbol = parse_qs(u.query).get("symbol", [None])[0]
        calls.append((endpoint, symbol))
        if (endpoint, symbol) in fail:
            raise fail[(endpoint, symbol)]
        if symbol in empty:
            return []
        if endpoint == "etf/holdings":
            if symbol in extra:
                return extra[symbol]
            return [{"symbol": symbol, "asset": "AAPL", "weightPercentage": 1.0}]
        if endpoint == "etf/asset-exposure":
            return load_fixture("etf_asset_exposure_ry")
        if endpoint == "etf/info":
            return load_fixture("etf_info_xiu")
        raise AssertionError(url)
    pipeline._get, pipeline._get_text = get, get_text
    return calls


def test_profile_bulk_memoised(pipeline):
    calls = make_get(pipeline)
    first = pipeline._profile_bulk()
    n = len(calls)
    assert pipeline._profile_bulk() is first
    assert len(calls) == n


def test_fetch_fund_holdings_saves_each_fund(pipeline):
    calls = make_get(pipeline)
    ticks = counting_ticks(pipeline)
    result = pipeline.fetch_fund_holdings()
    funds = _funds()
    assert result.failed == 0 and result.saved >= len(funds)
    for f in funds:
        assert os.path.exists(os.path.join(pipeline.fund_holdings_dir, f"{f['symbol']}.json"))
    with open(os.path.join(pipeline.fund_holdings_dir, "_universe.json")) as fh:
        assert [f["symbol"] for f in json.load(fh)] == [f["symbol"] for f in sorted(
            funds, key=lambda f: -f["aum"])]
    with open(os.path.join(pipeline.fund_holdings_dir, "_profile_slim.json")) as fh:
        slim = json.load(fh)
    assert set(slim[0]) == {"symbol", "isin", "exchange", "companyName",
                            "isEtf", "isFund", "isAdr"}
    held = [c for c in calls if c[0] == "etf/holdings"]
    assert len(held) == len(funds) + result.detail["look_through_fetched"]
    assert sorted(s for e, s in calls if e == "etf/asset-exposure") == sorted(CHECK)
    assert result.detail["crosscheck"] == CHECK
    for s in CHECK:
        assert os.path.exists(os.path.join(pipeline.fund_holdings_dir, "_crosscheck", f"{s}.json"))
    assert len(ticks) == len(calls)


def test_failed_fetch_keeps_previous(pipeline):
    os.makedirs(pipeline.fund_holdings_dir)
    path = os.path.join(pipeline.fund_holdings_dir, "XIU.TO.json")
    with open(path, "w") as f:
        f.write('["old"]')
    make_get(pipeline, fail={("etf/holdings", "XIU.TO"): FetchHTTPError("boom", 500)})
    result = pipeline.fetch_fund_holdings()
    with open(path) as f:
        assert f.read() == '["old"]'
    assert result.failed == 1 and "XIU.TO" in result.failed_items


def test_402_and_empty_are_no_data_and_keep_previous(pipeline):
    os.makedirs(pipeline.fund_holdings_dir)
    path = os.path.join(pipeline.fund_holdings_dir, "XEQT.TO.json")
    with open(path, "w") as f:
        f.write('["old"]')
    make_get(pipeline, fail={("etf/holdings", "XIU.TO"): FetchHTTPError("pay", 402)},
             empty=("XEQT.TO",))
    result = pipeline.fetch_fund_holdings()
    assert result.failed == 0 and result.no_data == 2
    with open(path) as f:
        assert f.read() == '["old"]'
    assert not os.path.exists(os.path.join(pipeline.fund_holdings_dir, "XIU.TO.json"))


def test_look_through_fetches_missing_underlying(pipeline):
    assert "TINY.TO" not in [f["symbol"] for f in _funds()]
    calls = make_get(pipeline, extra={"XIU.TO": [
        {"symbol": "XIU.TO", "asset": "TINY.TO", "weightPercentage": 5.0}]})
    result = pipeline.fetch_fund_holdings()
    assert result.detail["look_through_fetched"] == 1
    assert ("etf/holdings", "TINY.TO") in calls
    assert os.path.exists(os.path.join(pipeline.fund_holdings_dir, "TINY.TO.json"))


def test_failed_crosscheck_only_omitted(pipeline):
    make_get(pipeline, fail={("etf/asset-exposure", "TD.TO"): FetchHTTPError("x", 500)})
    result = pipeline.fetch_fund_holdings()
    assert result.failed == 0
    assert "TD.TO" not in result.detail["crosscheck"]


def test_limit_caps_funds(pipeline):
    calls = make_get(pipeline)
    result = pipeline.fetch_fund_holdings(limit=2)
    held = [s for e, s in calls if e == "etf/holdings"]
    assert len(held) == 2 + result.detail["look_through_fetched"]
    assert len(json.load(open(os.path.join(pipeline.fund_holdings_dir, "_universe.json")))) == 2
    assert len([c for c in calls if c[0] == "etf/asset-exposure"]) == 5


def test_slash_in_symbol_replaced(pipeline):
    assert pipeline._fund_file(pipeline.fund_holdings_dir, "A/B").endswith("A_B.json")


def test_fetch_fund_info_full_only(pipeline):
    assert "fetch_fund_info" in runner.FULL_STAGES
    assert "fetch_fund_info" not in runner.LEAN_STAGES
    assert "fetch_fund_holdings" in runner.LEAN_STAGES
    assert runner.FULL_STAGES[1:3] == ["fetch_fund_holdings", "fetch_fund_info"]
    assert {"fetch_fund_holdings", "fetch_fund_info"} <= runner.LIMITABLE
    make_get(pipeline)
    pipeline.fetch_fund_holdings()
    result = pipeline.fetch_fund_info()
    assert result.failed == 0
    assert os.path.exists(os.path.join(pipeline.fund_info_dir, "XIU.TO.json"))


def test_fetch_fund_info_without_universe_fails(pipeline):
    result = pipeline.fetch_fund_info()
    assert result.failed == 1 and result.failed_items == ["_universe.json"]


def test_profile_bulk_failure_fails_stage_without_raising(pipeline, capsys):
    os.makedirs(pipeline.fund_holdings_dir)
    files = {name: f'["old {name}"]' for name in
             ("_universe.json", "_profile_slim.json", "XIU.TO.json")}
    for name, body in files.items():
        with open(os.path.join(pipeline.fund_holdings_dir, name), "w") as f:
            f.write(body)
    calls = make_get(pipeline)

    def boom():
        raise FetchHTTPError("GET https://x/stable/profile-bulk?apikey=SECRET9 failed", 500)
    pipeline._fetch_profile_bulk = boom
    result = pipeline.fetch_fund_holdings()
    assert result.failed == 1 and result.failed_items == ["profile-bulk"]
    assert [c for c in calls if c[0] == "etf/holdings"] == []
    for name, body in files.items():
        with open(os.path.join(pipeline.fund_holdings_dir, name)) as f:
            assert f.read() == body
    out = capsys.readouterr().out
    assert "SECRET9" not in out and "fetch_fund_holdings" in out


def test_profile_bulk_rows_released_after_holdings(pipeline):
    make_get(pipeline)
    pipeline._profile_bulk()
    pipeline.fetch_fund_holdings()
    assert pipeline._profile_bulk_rows is None


def test_fetch_fund_info_unexpected_error_fails_stage(pipeline, capsys):
    os.makedirs(pipeline.fund_holdings_dir)
    with open(os.path.join(pipeline.fund_holdings_dir, "_universe.json"), "w") as f:
        json.dump([{"no_symbol": 1}], f)
    make_get(pipeline)
    result = pipeline.fetch_fund_info()
    assert result.failed == 1 and result.failed_items == ["fund-info"]
    assert "fetch_fund_info" in capsys.readouterr().out


def _old_holdings(pipeline, symbol, n):
    os.makedirs(pipeline.fund_holdings_dir, exist_ok=True)
    path = os.path.join(pipeline.fund_holdings_dir, f"{symbol}.json")
    old = [{"symbol": symbol, "asset": f"A{i}", "weightPercentage": 1.0} for i in range(n)]
    with open(path, "w") as f:
        json.dump(old, f)
    return path, old


def test_shrunk_holdings_keep_previous_file(pipeline, capsys):
    path, old = _old_holdings(pipeline, "XIU.TO", 10)
    make_get(pipeline, extra={"XIU.TO": [
        {"symbol": "XIU.TO", "asset": "RY.TO", "weightPercentage": 9.0}] * 4})
    result = pipeline.fetch_fund_holdings()
    with open(path) as f:
        assert json.load(f) == old
    assert "XIU.TO" in result.failed_items
    assert "shrank 10 → 4" in capsys.readouterr().out


def test_holdings_at_half_previous_are_saved(pipeline):
    path, _ = _old_holdings(pipeline, "XIU.TO", 10)
    new = [{"symbol": "XIU.TO", "asset": f"B{i}", "weightPercentage": 1.0} for i in range(5)]
    make_get(pipeline, extra={"XIU.TO": new})
    result = pipeline.fetch_fund_holdings()
    with open(path) as f:
        assert json.load(f) == new
    assert "XIU.TO" not in result.failed_items
