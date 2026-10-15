from pipelines.results import FAILED_ITEMS_CAP, StageResult, redact


def test_record_counts_and_rate():
    r = StageResult("fetch_x")
    r.record(True)
    r.record(False, "A")
    r.record(False, "B")
    assert (r.attempted, r.saved, r.failed) == (3, 1, 2)
    assert r.failed_items == ["A", "B"]
    assert r.failure_rate == 2 / 3


def test_empty_rate_is_zero():
    assert StageResult("x").failure_rate == 0.0


def test_redact_masks_api_keys():
    text = "500 Server Error for url: https://x/etf-holder/SPY?apikey=SECRET123&a=1"
    assert redact(text) == "500 Server Error for url: https://x/etf-holder/SPY?apikey=***&a=1"
    assert redact("https://serpapi.com/search?api_key=abc") == "https://serpapi.com/search?api_key=***"


def test_to_dict_caps_failed_items_and_round_trips():
    r = StageResult("x")
    for i in range(FAILED_ITEMS_CAP + 5):
        r.record(False, str(i))
    d = r.to_dict()
    assert len(d["failed_items"]) == FAILED_ITEMS_CAP
    assert d["failed_items_truncated"] is True
    assert d["failure_rate"] == 1.0
    back = StageResult.from_dict(d)
    assert back.failed == FAILED_ITEMS_CAP + 5
