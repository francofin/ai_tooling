from pipelines.fmp_stable_shapes import index_payload, price_payload, v3_label

from .helpers import load_fixture


def test_v3_label_format():
    assert v3_label("2026-11-13") == "November 13, 26"


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
