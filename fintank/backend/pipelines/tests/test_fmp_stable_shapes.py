import csv
import io

from pipelines import pipeline_config as cfg
from pipelines.fmp_stable_shapes import (etf_list_rows, holdings_rows,
                                         index_payload, price_payload, v3_label)

from .helpers import load_fixture


def test_v3_label_format():
    assert v3_label("2026-11-13") == "November 13, 26"


def test_v3_label_zero_pads_day():
    assert v3_label("2026-11-05") == "November 05, 26"


def test_price_payload_shape():
    full = load_fixture("px_full_aapl")
    adj = load_fixture("px_divadj_aapl")
    out = price_payload("AAPL", full, adj)
    assert out["symbol"] == "AAPL"
    hist = out["historical"]
    assert hist[0]["date"] == full[0]["date"]
    dates = [r["date"] for r in hist]
    assert dates == sorted(dates, reverse=True)
    adj_by_date = {r["date"]: r["adjClose"] for r in adj}
    need = {"date", "open", "high", "low", "close", "adjClose", "volume", "label"}
    for r in hist:
        assert need <= set(r)
        assert r["adjClose"] == adj_by_date[r["date"]]
        assert isinstance(r["volume"], int)
        assert not {"symbol", "adjOpen", "adjHigh", "adjLow"} & set(r)
    assert hist[0]["change"] == full[0]["change"]
    assert hist[0]["vwap"] == full[0]["vwap"]
    assert hist[0]["label"] == v3_label(hist[0]["date"])


def test_price_payload_joins_on_date_only():
    full = load_fixture("px_full_aapl")
    adj = load_fixture("px_divadj_aapl")
    missing = full[0]["date"]
    extra = dict(adj[1], date="2001-01-01")
    out = price_payload("AAPL", full, [r for r in adj if r["date"] != missing] + [extra])
    assert out["historical"][0]["adjClose"] is None
    assert "2001-01-01" not in [r["date"] for r in out["historical"]]
    assert len(out["historical"]) == len(full)


def test_index_payload_copies_close():
    full = load_fixture("idx_full_gsptse")
    out = index_payload("^GSPTSE", full)
    assert out["symbol"] == "^GSPTSE"
    hist = out["historical"]
    assert len(hist) == len(full)
    assert hist[0]["date"] == full[0]["date"]
    for r in hist:
        assert r["adjClose"] == r["close"]
        assert "symbol" not in r


HOLDING_KEYS = {"asset", "name", "isin", "cusip", "sharesNumber",
                "weightPercentage", "marketValue", "updated"}


def test_holdings_rows_drop_symbol_and_cash_lines():
    raw = load_fixture("etf_holdings_spy") + [{"symbol": "SPY", "asset": ""}]
    kept = [r for r in raw if r.get("asset")]
    assert len(kept) < len(raw)
    out = holdings_rows(raw)
    assert len(out) == len(kept)
    for r in out:
        assert set(r) == HOLDING_KEYS
        assert "symbol" not in r
    first, src = out[0], kept[0]
    assert first["cusip"] == src["securityCusip"]
    assert first["updated"] == src["updatedAt"]


def test_holdings_weight_is_float():
    for r in holdings_rows(load_fixture("etf_holdings_spy")):
        assert isinstance(r["weightPercentage"], float)


def _bulk():
    return list(csv.DictReader(io.StringIO(load_fixture("profile_bulk_part0", "csv"))))


def test_etf_list_rows_join_exchange():
    bulk = _bulk()
    # the captured etf-list sample and bulk sample share no symbols, so key the
    # list rows onto the bulk ETF symbols
    syms = [r["symbol"] for r in bulk if r["isEtf"] == "true"]
    etf_list = [{"symbol": s, "name": f"N {s}"} for s in syms]
    etf_list.append({"symbol": "NOT_IN_BULK", "name": "x"})
    out = etf_list_rows(etf_list, bulk, cfg.ETF_EXCHANGE_FILTER)
    assert out
    for r in out:
        assert set(r) == {"symbol", "name", "price", "exchange",
                          "exchangeShortName", "type"}
        assert r["exchange"] in cfg.ETF_EXCHANGE_FILTER
        assert r["type"] == "etf"
        assert r["price"] is None or isinstance(r["price"], float)
    got = {r["symbol"]: r for r in out}
    assert "NOT_IN_BULK" not in got and "2B7S.DE" not in got   # XETRA filtered
    sgov = got["SGOV"]
    assert sgov["name"] == "N SGOV" and sgov["price"] == float(
        next(b["price"] for b in bulk if b["symbol"] == "SGOV"))
    assert sgov["exchangeShortName"] == next(
        b["exchange"] for b in bulk if b["symbol"] == "SGOV")


def test_etf_list_rows_empty_price_is_none():
    bulk = [{"symbol": "A", "price": "", "exchangeFullName": "NASDAQ",
             "exchange": "NASDAQ"}]
    out = etf_list_rows([{"symbol": "A", "name": "a"}], bulk, ["NASDAQ"])
    assert out[0]["price"] is None
