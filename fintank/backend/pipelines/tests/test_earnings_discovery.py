import datetime as dt

import pytest

from pipelines import earnings_fmp as fmp
from pipelines import earnings_state as st
from pipelines.store import LocalStore

NOW = dt.datetime(2026, 11, 21, 12, 0, tzinfo=dt.timezone.utc)
TODAY = dt.date(2026, 11, 21)


def test_lock_blocks_second_run_and_stale_lock_is_taken(tmp_path):
    s = LocalStore(str(tmp_path))
    assert st.acquire_lock(s, "r1", NOW) is True
    assert st.acquire_lock(s, "r2", NOW + dt.timedelta(hours=29)) is False
    assert s.get_json(st.LOCK_KEY)["run_id"] == "r1"
    assert st.acquire_lock(s, "r3", NOW + dt.timedelta(hours=31)) is True
    assert s.get_json(st.LOCK_KEY)["run_id"] == "r3"


def test_release_lock_only_own(tmp_path):
    s = LocalStore(str(tmp_path))
    st.acquire_lock(s, "r1", NOW)
    st.release_lock(s, "other")
    assert s.exists(st.LOCK_KEY)
    st.release_lock(s, "r1")
    assert not s.exists(st.LOCK_KEY)


def test_load_state_default_and_round_trip(tmp_path):
    s = LocalStore(str(tmp_path))
    state = st.load_state(s)
    assert state == {"waiting": {}, "pending_batches": [], "written": [],
                     "attempts": {}, "last_run": None, "backfill_pending": None,
                     "handled": {}}
    state["written"].append("A|2026-Q1")
    st.save_state(s, state)
    assert st.load_state(s)["written"] == ["A|2026-Q1"]


def test_waiting_adds_only_covered_past_rows():
    covered = {"RY.TO": {"region": "ca", "name": "Royal"}, "AAPL": {"region": "us", "name": "Apple"}}
    rows = [
        {"symbol": "RY.TO", "date": "2026-11-20", "epsEstimated": 1.5, "epsActual": 1.6,
         "revenueEstimated": 10, "revenueActual": 11},
        {"symbol": "AAPL", "date": "2026-11-21", "epsEstimated": 2.0, "epsActual": None,
         "revenueEstimated": None, "revenueActual": None},
        {"symbol": "MSFT", "date": "2026-11-21"},
        {"symbol": "GMG.V", "date": "2026-11-20"},
        {"symbol": "RY.TO", "date": "2026-11-20"},
    ]
    state = st.load_state(LocalStore("/nonexistent-never-written"))
    st.update_waiting(state, rows + [{"symbol": "AAPL", "date": "2026-11-22"}], covered, TODAY)
    assert set(state["waiting"]) == {"RY.TO", "AAPL"}
    ry = state["waiting"]["RY.TO"]
    assert ry["report_date"] == "2026-11-20" and ry["first_seen"] == "2026-11-21"
    assert ry["estimates"] == {"eps_estimate": 1.5, "eps_actual": 1.6,
                               "revenue_estimate": 10, "revenue_actual": 11}
    # tomorrow's row alone is not added
    state2 = st.load_state(LocalStore("/nonexistent-never-written"))
    st.update_waiting(state2, [{"symbol": "AAPL", "date": "2026-11-22"}], covered, TODAY)
    assert state2["waiting"] == {}
    # an already-waiting symbol is not overwritten
    st.update_waiting(state, [{"symbol": "RY.TO", "date": "2026-11-21", "epsEstimated": 9}],
                      covered, TODAY + dt.timedelta(days=1))
    assert state["waiting"]["RY.TO"]["report_date"] == "2026-11-20"


def test_expire_after_7_days():
    state = {"waiting": {
        "OLD": {"first_seen": "2026-11-13"}, "EDGE": {"first_seen": "2026-11-14"},
        "NEW": {"first_seen": "2026-11-21"}}}
    assert st.expire_waiting(state, TODAY) == ["OLD"]
    assert set(state["waiting"]) == {"EDGE", "NEW"}


def test_is_written_repairs_state_from_live_object(tmp_path):
    live = LocalStore(str(tmp_path))
    state = {"written": []}
    assert st.is_written(state, live, "RY.TO", "2026-Q4") is False
    live.put_json(st.note_key("RY.TO", "2026-Q4"), {})
    assert st.is_written(state, live, "RY.TO", "2026-Q4") is True
    assert state["written"] == ["RY.TO|2026-Q4"]
    assert st.note_key("BRK-B", "2026-Q3") == "earnings_notes/BRK-B/2026-Q3.json"
    assert st.company_index_key("RY.TO") == "earnings_notes/RY.TO/index.json"
    assert st.LATEST_KEY == "earnings_notes/latest.json"


def test_covered_symbols_ca_wins():
    files = {
        "index_data/constituents/tsx_const_constituents.json":
            [{"asset": "RY.TO", "name": "Royal"}, {"asset": "DUAL", "name": "D-ca"}],
        "index_data/constituents/sp500_const_constituents.json":
            [{"asset": "AAPL", "name": "Apple"}, {"asset": "DUAL", "name": "D-us"}, {"asset": "X"}],
    }
    out = fmp.covered_symbols(lambda k, default=None: files.get(k, default))
    assert out["DUAL"] == {"region": "ca", "name": "D-ca"}
    assert out["AAPL"]["region"] == "us" and out["X"]["name"] == "X"


def test_fetch_calendar_params():
    seen = {}

    def get(url, params=None, **kw):
        seen.update(url=url, params=params)
        return [{"symbol": "A"}]

    assert fmp.fetch_calendar("K", dt.date(2026, 11, 14), TODAY, get) == [{"symbol": "A"}]
    assert seen["url"].endswith("/stable/earnings-calendar")
    assert seen["params"] == {"from": "2026-11-14", "to": "2026-11-21", "apikey": "K"}
    assert "v3" not in seen["url"]


def test_fiscal_labels_come_from_transcript_dates():
    def get(url, params=None, **kw):
        assert url.endswith("/earning-call-transcript-dates")
        return [{"quarter": 4, "fiscalYear": 2026, "date": "2026-12-03"},
                {"quarter": 3, "fiscalYear": 2026, "date": "2026-08-27"}]

    # calendar says 2026-12-03 (calendar Q4 / Dec) but the label is the transcript's
    assert fmp.transcript_dates("K", "RY.TO", get) == [
        (2026, 4, "2026-12-03"), (2026, 3, "2026-08-27")]


def test_fetch_transcript_ok_and_empty_raises():
    def ok(url, params=None, **kw):
        assert params["year"] == 2026 and params["quarter"] == 4
        return [{"symbol": "RY.TO", "content": "Hello.", "date": "2026-12-03"}]

    assert fmp.fetch_transcript("K", "RY.TO", 2026, 4, ok) == ("Hello.", "2026-12-03")
    for payload in ([], [{"content": "  "}], [{"content": None}]):
        with pytest.raises(LookupError):
            fmp.fetch_transcript("K", "RY.TO", 2026, 4, lambda *a, **k: payload)


def test_http_get_never_leaks_the_api_key(monkeypatch):
    import requests

    class Failing:
        def raise_for_status(self):
            raise requests.HTTPError("403 for url: https://f/x?apikey=SECRET")

    monkeypatch.setattr(fmp.requests, "get", lambda *a, **kw: Failing())
    monkeypatch.setattr(fmp.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError) as info:
        fmp.http_get_json("https://f/x", params={"apikey": "SECRET"})
    assert "SECRET" not in str(info.value)


COV = {"AAPL": {"region": "us", "name": "Apple"}}


def _fresh():
    return st.load_state(LocalStore("/nonexistent-never-written"))


def test_dropped_symbol_does_not_reenter():
    state = _fresh()
    row = {"symbol": "AAPL", "date": "2026-11-15"}
    st.update_waiting(state, [row], COV, dt.date(2026, 11, 15))
    later = dt.date(2026, 11, 23)
    assert st.expire_waiting(state, later) == ["AAPL"]
    assert state["handled"] == {"AAPL|2026-11-15": "dropped"}
    st.update_waiting(state, [row], COV, later)
    assert state["waiting"] == {}


def test_handled_published_does_not_reenter():
    state = _fresh()
    st.mark_handled(state, "AAPL", "2026-11-20", "published")
    st.update_waiting(state, [{"symbol": "AAPL", "date": "2026-11-20"}], COV, TODAY)
    assert state["waiting"] == {}


def test_row_age_limit_is_wait_days():
    old, edge = _fresh(), _fresh()
    st.update_waiting(old, [{"symbol": "AAPL", "date": "2026-11-13"}], COV, TODAY)   # 8 days
    st.update_waiting(edge, [{"symbol": "AAPL", "date": "2026-11-14"}], COV, TODAY)  # 7 days
    assert old["waiting"] == {} and "AAPL" in edge["waiting"]


def test_malformed_calendar_rows_are_skipped():
    state = _fresh()
    st.update_waiting(state, [{"symbol": "AAPL", "date": "garbage"}, {"symbol": "AAPL"},
                              {"symbol": "AAPL", "date": None}], COV, TODAY)
    assert state["waiting"] == {}


def test_stale_takeover_aborts_if_lock_replaced_midway(tmp_path):
    class Racy(LocalStore):
        reads = 0

        def get_json(self, key, default=None):
            v = super().get_json(key, default)
            if key == st.LOCK_KEY:
                Racy.reads += 1
                if Racy.reads == 1:        # right after our first read, another run takes over
                    self.put_json(key, {"run_id": "other", "taken_at": NOW.isoformat()})
            return v

    s = Racy(str(tmp_path))
    LocalStore.put_json(s, st.LOCK_KEY, {"run_id": "old", "taken_at":
                                         (NOW - dt.timedelta(hours=40)).isoformat()})
    assert st.acquire_lock(s, "mine", NOW) is False
    assert LocalStore.get_json(s, st.LOCK_KEY)["run_id"] == "other"


def test_malformed_lock_is_held_and_logged(tmp_path):
    s = LocalStore(str(tmp_path))
    s.put_json(st.LOCK_KEY, {"oops": 1})
    msgs = []
    assert st.acquire_lock(s, "r", NOW, log=msgs.append) is False
    assert "malformed" in msgs[0] and "earnings/lock.json" in msgs[0]
    assert s.get_json(st.LOCK_KEY) == {"oops": 1}
