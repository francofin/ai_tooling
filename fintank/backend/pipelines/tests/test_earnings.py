"""Earnings run orchestration. Spend safety: no real Claude client is ever built
here — every test uses FakeBatch, the key is a placeholder, and the autouse
fixture removes ANTHROPIC_API_KEY and makes AnthropicBatchClient explode."""
import datetime as dt
import re

import pytest

from pipelines import earnings as e
from pipelines import earnings_backfill as bf
from pipelines import earnings_state as st
from pipelines.earnings_claude import BatchResult
from pipelines.notify import earnings_message
from pipelines.report import RunReport
from pipelines.store import LocalStore, run_key

NOW = dt.datetime(2026, 11, 21, 12, 0, tzinfo=dt.timezone.utc)
FAKE_KEY = "test-placeholder-not-a-key"


@pytest.fixture(autouse=True)
def _no_real_claude(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    class Forbidden:
        def __init__(self, *a, **kw):
            raise AssertionError("AnthropicBatchClient must never be built in tests")

    monkeypatch.setattr(e, "AnthropicBatchClient", Forbidden)


def words(n, seed="steady"):
    return " ".join(f"{seed}{i % 7}" for i in range(n))


def good_output(previous=False):
    sections = {k: words(150, k[:4]) for k in e.SECTION_KEYS}
    sections["what_changed"] = words(150, "chg") if previous else None
    return {"lean": "neutral", "headline": "A steady quarter.",
            "key_points": ["One thing.", "Another thing.", "A third thing."],
            "sections": sections}


def bad_output():
    out = good_output()
    out["sections"]["guidance"] += " revenue will reach $4.1 billion"
    return out


class FakeBatch:
    """Records submits. Output per symbol: 'good' (default) or 'bad'."""

    def __init__(self, statuses=None, bad=(), status_raises=False):
        self.submits, self.batches = [], {}
        self.statuses = list(statuses or [])
        self.bad = set(bad)
        self.status_raises = status_raises
        self.status_calls = 0

    def submit(self, requests):
        self.submits.append(requests)
        batch_id = f"batch-{len(self.submits)}"
        self.batches[batch_id] = requests
        return batch_id

    def status(self, batch_id):
        self.status_calls += 1
        if self.status_raises:
            raise RuntimeError("container killed")
        return self.statuses.pop(0) if self.statuses else "ended"

    def results(self, batch_id):
        for req in self.batches[batch_id]:
            text = req["params"]["messages"][0]["content"]
            symbol = re.search(r"<company>.*\((\S+)\)</company>", text).group(1)
            has_prev = "<previous_note>none</previous_note>" not in text
            out = bad_output() if symbol in self.bad else good_output(has_prev)
            yield BatchResult(req["custom_id"], "succeeded", output=out,
                              usage={"input_tokens": 1000, "output_tokens": 500})


class FakeFmp:
    def __init__(self):
        self.calendar = []
        self.dates = {}         # symbol -> [{"fiscalYear", "quarter", "date"}]
        self.history = {}       # symbol -> earnings rows (stable /earnings)
        self.calls = []

    def report(self, symbol, date, fy, q, call_date=None):
        self.calendar.append({"symbol": symbol, "date": date, "epsEstimated": None,
                              "epsActual": None, "revenueEstimated": None,
                              "revenueActual": None})
        if fy is not None:
            self.dates.setdefault(symbol, []).insert(
                0, {"fiscalYear": fy, "quarter": q, "date": call_date or date})

    def __call__(self, url, params=None, **kw):
        self.calls.append((url.rsplit("/", 1)[-1], dict(params or {})))
        if url.endswith("/earnings-calendar"):
            return list(self.calendar)
        if url.endswith("/earning-call-transcript-dates"):
            return list(self.dates.get(params["symbol"], []))
        if url.endswith("/earnings"):
            history = self.history.get(params["symbol"], [])
            if isinstance(history, Exception):
                raise history
            return list(history)
        if url.endswith("/earning-call-transcript"):
            return [{"symbol": params["symbol"], "year": params["year"],
                     "date": "2026-11-20", "content": "The call went well. " * 50}]
        raise AssertionError(url)


class Clock:
    def __init__(self):
        self.t = 0

    def sleep(self, seconds):
        self.t += seconds


class World:
    def __init__(self, tmp_path):
        self.store = LocalStore(str(tmp_path / "state"))
        self.live = LocalStore(str(tmp_path / "live"))
        self.fmp = FakeFmp()
        self.clock = Clock()
        self.sent = []
        self.live.put_json("index_data/constituents/tsx_const_constituents.json",
                           [{"asset": "RY.TO", "name": "Royal Bank"},
                            {"asset": "BBD-B.TO", "name": "Bombardier"}])
        self.live.put_json("index_data/constituents/sp500_const_constituents.json",
                           [{"asset": "AAPL", "name": "Apple"},
                            {"asset": "MSFT", "name": "Microsoft"}])

    def send(self, subject, body):
        self.sent.append((subject, body))

    def run(self, run_id, client, now=NOW, key=FAKE_KEY, no_claude=False):
        return e.run_daily(run_id, "fmp-test", key, self.store, self.live,
                           batch_client=client, no_claude=no_claude, notifier=self,
                           now=now, get=self.fmp, sleep=self.clock.sleep,
                           log=lambda *a: None)

    def state(self):
        return st.load_state(self.store)

    def summary(self, run_id):
        return self.store.get_json(run_key(run_id, "summary.json"))


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def test_us_and_tsx_reporters_get_notes_published(world):
    world.fmp.report("RY.TO", "2026-11-20", 2026, 4)
    world.fmp.report("AAPL", "2026-11-19", 2026, 1)
    client = FakeBatch()
    report = world.run("earnings-1", client)
    assert len(client.submits) == 1 and len(client.submits[0]) == 2
    for sym, q in (("RY.TO", "2026-Q4"), ("AAPL", "2026-Q1")):
        note = world.live.get_json(st.note_key(sym, q))
        assert note["symbol"] == sym and note["model"] == "claude-opus-5-5"
        index = world.live.get_json(st.company_index_key(sym))
        assert index["symbol"] == sym
        assert index["quarters"][0] == {
            "quarter": q, "fiscal_year": note["fiscal_year"],
            "fiscal_quarter": note["fiscal_quarter"], "report_date": note["report_date"],
            "lean": "neutral", "headline": "A steady quarter.",
            "key_points": note["key_points"], "withdrawn": False}
    assert world.live.get_json(st.LATEST_KEY) == {"RY.TO": "2026-Q4", "AAPL": "2026-Q1"}
    state = world.state()
    assert set(state["written"]) == {"RY.TO|2026-Q4", "AAPL|2026-Q1"}
    assert state["waiting"] == {} and state["pending_batches"] == []
    assert state["attempts"] == {"RY.TO|2026-Q4": 1, "AAPL|2026-Q1": 1}
    assert state["last_run"] == "2026-11-21"
    assert not world.store.exists(st.LOCK_KEY)
    assert report.verdict == "pass"
    assert world.store.get_json(run_key("earnings-1", "results.json"))
    assert world.sent[0][0] == "[Fintank] Earnings earnings-1 - 2 published, 0 failed"


def test_late_transcript_waits_then_publishes_next_run(world):
    world.fmp.report("MSFT", "2026-11-20", None, None)   # no transcript yet
    world.fmp.dates["MSFT"] = [{"fiscalYear": 2026, "quarter": 1, "date": "2026-08-01"}]
    client = FakeBatch()
    world.run("earnings-1", client)
    assert client.submits == []
    assert "MSFT" in world.state()["waiting"]
    assert not world.live.exists(st.note_key("MSFT", "2026-Q1"))   # older quarter not written
    world.fmp.dates["MSFT"].insert(0, {"fiscalYear": 2026, "quarter": 2, "date": "2026-11-21"})
    world.run("earnings-2", client, now=NOW + dt.timedelta(days=1))
    assert world.live.exists(st.note_key("MSFT", "2026-Q2"))
    assert world.state()["waiting"] == {}


def test_dropped_after_7_days_is_reported(world):
    world.fmp.report("MSFT", "2026-11-20", None, None)
    client = FakeBatch()
    world.run("earnings-1", client)
    world.fmp.calendar = []
    world.run("earnings-2", client, now=NOW + dt.timedelta(days=8))
    assert world.state()["waiting"] == {}
    assert world.summary("earnings-2")["dropped"] == ["MSFT"]
    assert "MSFT" in world.sent[-1][1] and "Dropped" in world.sent[-1][1]
    # the calendar still listing it does not bring it back
    world.fmp.report("MSFT", "2026-11-20", None, None)
    world.run("earnings-3", client, now=NOW + dt.timedelta(days=9))
    assert world.state()["waiting"] == {}


def test_batch_still_running_at_cap_is_collected_next_run_without_resubmit(world):
    world.fmp.report("RY.TO", "2026-11-20", 2026, 4)
    polls = e.DAILY_MAX_WAIT_SECONDS // e.POLL_SECONDS
    client = FakeBatch(statuses=["in_progress"] * (polls + 1))
    world.run("earnings-1", client)
    assert world.clock.t == e.DAILY_MAX_WAIT_SECONDS
    state = world.state()
    assert [b["batch_id"] for b in state["pending_batches"]] == ["batch-1"]
    assert not world.live.exists(st.note_key("RY.TO", "2026-Q4"))
    assert world.summary("earnings-1")["pending_batches"] == ["batch-1"]
    client.statuses = ["ended"]
    world.run("earnings-2", client, now=NOW + dt.timedelta(days=1))
    assert len(client.submits) == 1
    assert world.live.exists(st.note_key("RY.TO", "2026-Q4"))
    assert world.state()["pending_batches"] == []


def test_running_batch_is_not_resubmitted_while_still_running(world):
    world.fmp.report("RY.TO", "2026-11-20", 2026, 4)
    polls = e.DAILY_MAX_WAIT_SECONDS // e.POLL_SECONDS
    client = FakeBatch(statuses=["in_progress"] * (2 * polls + 10))
    world.run("earnings-1", client)
    world.run("earnings-2", client, now=NOW + dt.timedelta(days=1))
    assert len(client.submits) == 1


def test_crash_after_submit_does_not_resubmit(world):
    world.fmp.report("RY.TO", "2026-11-20", 2026, 4)
    client = FakeBatch(status_raises=True)
    with pytest.raises(RuntimeError, match="container killed"):
        world.run("earnings-1", client)
    assert not world.store.exists(st.LOCK_KEY)
    assert [b["batch_id"] for b in world.state()["pending_batches"]] == ["batch-1"]
    client.status_raises = False
    world.run("earnings-2", client)
    assert len(client.submits) == 1
    assert world.live.exists(st.note_key("RY.TO", "2026-Q4"))


def test_failed_check_goes_to_failed_and_retries_once_only(world):
    world.fmp.report("RY.TO", "2026-11-20", 2026, 4)
    client = FakeBatch(bad={"RY.TO"})
    world.run("earnings-1", client)
    failed = world.store.get_json(run_key("earnings-1", "failed/RY.TO_2026-Q4.json"))
    assert any("$4.1 billion" in r for r in failed["reasons"])
    assert world.summary("earnings-1")["failed"][0]["symbol"] == "RY.TO"
    assert "RY.TO" in world.state()["waiting"]
    world.run("earnings-2", client, now=NOW + dt.timedelta(days=1))
    assert len(client.submits) == 2
    state = world.state()
    assert state["attempts"]["RY.TO|2026-Q4"] == 2
    assert state["waiting"] == {}
    assert state["handled"]["RY.TO|2026-11-20"] == "max_attempts"
    world.run("earnings-3", client, now=NOW + dt.timedelta(days=2))
    assert len(client.submits) == 2
    assert not world.live.exists(st.note_key("RY.TO", "2026-Q4"))


def test_daily_cap_150_leaves_rest_waiting(world, monkeypatch):
    monkeypatch.setattr(e, "DAILY_CAP", 2)
    for sym in ("RY.TO", "BBD-B.TO", "AAPL", "MSFT"):
        world.fmp.report(sym, "2026-11-20", 2026, 3)
    client = FakeBatch()
    world.run("earnings-1", client)
    assert len(client.submits[0]) == 2
    assert len(world.state()["waiting"]) == 2


def test_caps_and_timings_are_the_agreed_values():
    assert (e.DAILY_CAP, e.BACKFILL_CAP, e.WAIT_DAYS, e.MAX_ATTEMPTS,
            e.POLL_SECONDS, e.DAILY_MAX_WAIT_SECONDS) == (150, 800, 7, 2, 300, 10800)
    assert e.WAIT_DAYS is st.WAIT_DAYS


@pytest.mark.parametrize("key", ["unset", "", "  ", None])
def test_unset_key_makes_no_client_and_says_so(world, key):
    world.fmp.report("RY.TO", "2026-11-20", 2026, 4)
    client = FakeBatch()
    world.run("earnings-1", client, key=key)
    assert client.submits == [] and client.status_calls == 0
    assert world.store.exists(run_key("earnings-1", "requests.json"))
    subject, body = world.sent[0]
    assert "no Claude key, nothing was generated" in body
    assert not world.live.exists(st.note_key("RY.TO", "2026-Q4"))


def test_no_claude_writes_requests_and_no_submit(world):
    world.fmp.report("RY.TO", "2026-11-20", 2026, 4)
    world.fmp.report("BBD-B.TO", "2026-11-20", 2026, 4)
    client = FakeBatch()
    world.run("earnings-1", client, no_claude=True)
    assert client.submits == [] and client.status_calls == 0
    saved = world.store.get_json(run_key("earnings-1", "requests.json"))
    assert len(saved["requests"]) == 2
    assert sorted(saved["ids"]) == ["note-0000", "note-0001"]
    assert {"symbol": "RY.TO", "quarter": "2026-Q4"} in saved["ids"].values()
    summary = world.summary("earnings-1")
    assert summary["no_claude"] is True
    assert summary["usage"]["estimated_input_tokens"] > 0
    assert "RY.TO" in world.state()["waiting"]           # still waiting for the real run


def test_no_claude_skips_collecting_pending_batches(world):
    state = st.load_state(world.store)
    state["pending_batches"].append({"batch_id": "batch-9", "run_id": "old",
                                     "jobs_key": run_key("old", "jobs.json"), "tags": []})
    st.save_state(world.store, state)
    client = FakeBatch()
    world.run("earnings-1", client, no_claude=True)
    assert client.status_calls == 0
    assert world.state()["pending_batches"][0]["batch_id"] == "batch-9"


def test_lock_held_refuses(world):
    world.fmp.report("RY.TO", "2026-11-20", 2026, 4)
    st.acquire_lock(world.store, "other-run", NOW)
    client = FakeBatch()
    report = world.run("earnings-1", client)
    assert report.verdict == "fail"
    assert "another earnings run holds the lock" in report.checks[0]["detail"]
    assert client.submits == [] and world.fmp.calls == []
    assert world.store.get_json(st.LOCK_KEY)["run_id"] == "other-run"
    assert not world.store.exists(st.STATE_KEY)


def test_backfill_pending_blocks_daily(world):
    world.fmp.report("RY.TO", "2026-11-20", 2026, 4)
    state = st.load_state(world.store)
    state["backfill_pending"] = "backfill-1"
    st.save_state(world.store, state)
    client = FakeBatch()
    report = world.run("earnings-1", client)
    assert report.verdict == "fail"
    assert client.submits == [] and world.fmp.calls == []
    assert "backfill-1" in world.sent[0][1]
    assert not world.store.exists(st.LOCK_KEY)


def test_previous_note_is_sent_and_what_changed_required(world):
    world.fmp.report("RY.TO", "2026-08-27", 2026, 3)
    client = FakeBatch()
    world.run("earnings-1", client, now=dt.datetime(2026, 8, 28, 12, tzinfo=dt.timezone.utc))
    world.fmp.calendar = []
    world.fmp.report("RY.TO", "2026-11-20", 2026, 4)
    world.run("earnings-2", client)
    text = client.submits[1][0]["params"]["messages"][0]["content"]
    assert "<previous_note>none</previous_note>" not in text
    assert "A steady quarter." in text
    assert world.live.get_json(st.LATEST_KEY) == {"RY.TO": "2026-Q4"}
    quarters = world.live.get_json(st.company_index_key("RY.TO"))["quarters"]
    assert [q["quarter"] for q in quarters] == ["2026-Q4", "2026-Q3"]


# --- backfill ---------------------------------------------------------------

def backfill_world(world):
    for sym, fy, q in (("RY.TO", 2026, 4), ("BBD-B.TO", 2026, 3), ("AAPL", 2026, 1),
                       ("MSFT", 2026, 1)):
        world.fmp.dates[sym] = [{"fiscalYear": fy, "quarter": q, "date": "2026-11-01"}]


def submit(world, run_id, client, no_claude=False, key=FAKE_KEY):
    return bf.backfill_submit(run_id, "fmp-test", key, world.store, world.live,
                             batch_client=client, no_claude=no_claude, get=world.fmp,
                             log=lambda *a: None, now=NOW)


def test_backfill_submit_check_stage_publish(world):
    backfill_world(world)
    world.live.put_json(st.note_key("MSFT", "2026-Q1"), {"symbol": "MSFT"})  # already live
    client = FakeBatch(statuses=["in_progress", "ended"])
    status = submit(world, "backfill-1", client)
    assert status["status"] == "submitted" and status["batch_id"] == "batch-1"
    assert len(client.submits[0]) == 3
    assert all("<previous_note>none</previous_note>"
               in r["params"]["messages"][0]["content"] for r in client.submits[0])
    assert world.state()["backfill_pending"] == "backfill-1"
    assert world.store.get_json(run_key("backfill-1", "backfill-status.json")) == status
    assert bf.backfill_check("backfill-1", world.store, batch_client=client)["status"] == "in_progress"
    assert bf.backfill_check("backfill-1", world.store, batch_client=client)["status"] == "ended"
    verdict = bf.backfill_stage("backfill-1", world.store, batch_client=client)
    assert verdict["hold"] is True and (verdict["passed"], verdict["failed"]) == (3, 0)
    assert world.store.get_json(run_key("backfill-1", "verdict.json")) == verdict
    assert world.store.exists(run_key("backfill-1", "report.json"))
    assert world.store.exists(run_key("backfill-1", "notes/BBD-B.TO_2026-Q3.json"))
    assert not world.live.exists(st.note_key("RY.TO", "2026-Q4"))         # nothing live yet
    assert not world.live.exists(st.LATEST_KEY)
    assert bf.backfill_publish("backfill-1", world.store, world.live) == 3
    for sym, q in (("RY.TO", "2026-Q4"), ("BBD-B.TO", "2026-Q3"), ("AAPL", "2026-Q1")):
        assert world.live.exists(st.note_key(sym, q))
    assert world.live.get_json(st.LATEST_KEY) == {"RY.TO": "2026-Q4", "BBD-B.TO": "2026-Q3",
                                                  "AAPL": "2026-Q1"}
    state = world.state()
    assert state["backfill_pending"] is None
    assert "BBD-B.TO|2026-Q3" in state["written"]
    assert not world.store.exists(st.LOCK_KEY)
    with pytest.raises(RuntimeError, match="not the staged backfill"):
        bf.backfill_publish("backfill-1", world.store, world.live)       # already settled


def test_backfill_sends_consensus_from_earnings_history(world):
    backfill_world(world)
    # FakeFmp's transcript is dated 2026-11-20: RY.TO reported the day before
    world.fmp.history["RY.TO"] = [{"date": "2026-11-19", "epsEstimated": 4.03, "epsActual": 4.24,
                                   "revenueEstimated": 1.82e10, "revenueActual": 1.84e10}]
    world.fmp.history["AAPL"] = RuntimeError("FMP down")        # lookup failure: still a job
    client = FakeBatch()
    submit(world, "backfill-c", client)
    texts = {re.search(r"\((\S+)\)</company>", t).group(1): t for t in
             (r["params"]["messages"][0]["content"] for r in client.submits[0])}
    assert set(texts) == {"RY.TO", "BBD-B.TO", "AAPL", "MSFT"}
    assert "<report_date>2026-11-19</report_date>" in texts["RY.TO"]
    assert '"eps_estimate": 4.03' in texts["RY.TO"] and '"eps_actual": 4.24' in texts["RY.TO"]
    for sym in ("AAPL", "BBD-B.TO"):
        assert "<report_date>2026-11-20</report_date>" in texts[sym]
        assert '"eps_estimate": null' in texts[sym]


def test_backfill_submit_retry_never_resubmits(world):
    backfill_world(world)
    client = FakeBatch()
    first = submit(world, "backfill-1", client)
    again = submit(world, "backfill-1", client)
    assert again == first and len(client.submits) == 1
    with pytest.raises(RuntimeError, match="backfill-1"):
        submit(world, "backfill-2", client)
    assert len(client.submits) == 1


def test_backfill_no_claude_and_nothing_to_do(world):
    backfill_world(world)
    client = FakeBatch()
    status = submit(world, "backfill-1", client, no_claude=True)
    assert status["status"] == "no_claude" and status["targets"] == 4
    assert status["estimated_input_tokens"] > 0
    assert world.store.exists(run_key("backfill-1", "requests.json"))
    assert submit(world, "backfill-2", client, key="unset")["status"] == "no_claude"
    assert client.submits == [] and world.state()["backfill_pending"] is None
    world.fmp.dates = {}
    assert submit(world, "backfill-3", client)["status"] == "nothing_to_do"
    assert client.submits == []


def test_backfill_cap(world, monkeypatch):
    backfill_world(world)
    monkeypatch.setattr(e, "BACKFILL_CAP", 2)
    client = FakeBatch()
    assert submit(world, "backfill-1", client)["targets"] == 2
    assert len(client.submits[0]) == 2


class ForbiddenClient:
    def __getattr__(self, name):
        raise AssertionError(f"Claude client used: {name}")


def test_backfill_from_results_makes_no_claude_call(world):
    backfill_world(world)
    client = FakeBatch(bad={"AAPL"})
    submit(world, "backfill-1", client)
    first = bf.backfill_stage("backfill-1", world.store, batch_client=client)
    assert (first["passed"], first["failed"]) == (3, 1)
    bf.backfill_discarded("backfill-1", world.store)
    verdict = bf.backfill_stage("backfill-2", world.store, batch_client=ForbiddenClient(),
                               from_results="backfill-1")
    assert verdict["hold"] is True and (verdict["passed"], verdict["failed"]) == (3, 1)
    assert world.store.exists(run_key("backfill-2", "notes/RY.TO_2026-Q4.json"))
    assert world.state()["backfill_pending"] == "backfill-2"
    assert bf.backfill_publish("backfill-2", world.store, world.live) == 3
    assert len(client.submits) == 1


def test_discarded_backfill_keeps_results_and_unblocks_daily(world):
    backfill_world(world)
    client = FakeBatch()
    submit(world, "backfill-1", client)
    bf.backfill_stage("backfill-1", world.store, batch_client=client)
    bf.backfill_discarded("backfill-1", world.store)
    assert world.store.exists(run_key("backfill-1", "results.json"))
    state = world.state()
    assert state["backfill_pending"] is None
    assert not any(t.startswith("RY.TO") for t in state["written"])
    assert not world.live.exists(st.note_key("RY.TO", "2026-Q4"))
    world.fmp.report("RY.TO", "2026-11-20", 2026, 4)
    report = world.run("earnings-1", FakeBatch())
    assert report.verdict == "pass"
    assert world.live.exists(st.note_key("RY.TO", "2026-Q4"))


def test_backfill_steps_respect_the_lock(world):
    backfill_world(world)
    st.acquire_lock(world.store, "other-run", NOW)
    client = FakeBatch()
    with pytest.raises(RuntimeError, match="another earnings run holds the lock"):
        submit(world, "backfill-1", client)
    assert client.submits == []


# --- publishing ---------------------------------------------------------------

def stored(symbol, fy, q, lean="neutral"):
    return {"symbol": symbol, "company_name": symbol, "fiscal_year": fy,
            "fiscal_quarter": q, "report_date": f"{fy}-0{q}-15", "call_date": "",
            "lean": lean, "headline": f"{symbol} {fy}-Q{q}", "key_points": ["a", "b", "c"],
            "sections": {}, "model": "claude-opus-5-5", "generated_at": "x", "source": "s"}


def test_pull_note_withdraws_and_repoints_latest(world):
    live = world.live
    e.publish_note(live, stored("RY.TO", 2026, 2))
    e.publish_note(live, stored("RY.TO", 2026, 4))
    e.publish_note(live, stored("RY.TO", 2026, 3))      # out of order still sorts
    quarters = live.get_json(st.company_index_key("RY.TO"))["quarters"]
    assert [q["quarter"] for q in quarters] == ["2026-Q4", "2026-Q3", "2026-Q2"]
    assert live.get_json(st.LATEST_KEY) == {"RY.TO": "2026-Q4"}
    e.pull_note(live, "RY.TO", "2026-Q4")
    quarters = live.get_json(st.company_index_key("RY.TO"))["quarters"]
    assert quarters[0]["withdrawn"] is True and quarters[1]["withdrawn"] is False
    assert live.get_json(st.LATEST_KEY) == {"RY.TO": "2026-Q3"}
    assert live.exists(st.note_key("RY.TO", "2026-Q4"))     # object stays
    e.pull_note(live, "RY.TO", "2026-Q3")
    e.pull_note(live, "RY.TO", "2026-Q2")
    assert "RY.TO" not in live.get_json(st.LATEST_KEY)
    with pytest.raises(KeyError):
        e.pull_note(live, "RY.TO", "2025-Q1")
    with pytest.raises(KeyError):
        e.pull_note(live, "NOPE", "2026-Q1")


def test_republishing_a_quarter_replaces_its_entry(world):
    e.publish_note(world.live, stored("AAPL", 2026, 1, lean="bearish"))
    e.publish_note(world.live, stored("AAPL", 2026, 1, lean="bullish"))
    quarters = world.live.get_json(st.company_index_key("AAPL"))["quarters"]
    assert len(quarters) == 1 and quarters[0]["lean"] == "bullish"


def test_symbol_with_dash_and_dot_keys(world):
    world.fmp.report("BBD-B.TO", "2026-11-20", 2026, 3)
    client = FakeBatch()
    world.run("earnings-1", client)
    assert re.match(r"^[a-zA-Z0-9_-]{1,64}$", client.submits[0][0]["custom_id"])
    assert world.live.exists("earnings_notes/BBD-B.TO/2026-Q3.json")
    assert world.live.get_json("earnings_notes/BBD-B.TO/index.json")["symbol"] == "BBD-B.TO"
    assert world.live.get_json(st.LATEST_KEY) == {"BBD-B.TO": "2026-Q3"}
    e.pull_note(world.live, "BBD-B.TO", "2026-Q3")
    assert world.live.get_json(st.LATEST_KEY) == {}


# --- email --------------------------------------------------------------------

def test_earnings_message_subject_and_cost():
    report = RunReport("earnings-20261121-1100", "earnings", "daily", NOW.isoformat())
    report.finish(verdict_override="warn")
    summary = {"published": [{"symbol": "RY.TO", "quarter": "2026-Q4", "lean": "bullish"}],
               "failed": [{"symbol": "AAPL", "quarter": "2026-Q1",
                           "reasons": ["unsourced figures: $4.1 billion"]}],
               "waiting": ["MSFT"], "dropped": ["XYZ"], "pending_batches": ["batch-7"],
               "usage": {"input_tokens": 1_000_000, "output_tokens": 100_000},
               "cost_usd": 3.0, "no_claude": False}
    subject, body = earnings_message(report, summary, "state-bucket")
    assert subject == "[Fintank] Earnings earnings-20261121-1100 - 1 published, 1 failed"
    assert subject.isascii()
    for text in ("RY.TO 2026-Q4", "$4.1 billion", "MSFT", "XYZ", "batch-7",
                 "1,000,000", "$3.00", "pull-note"):
        assert text in body
    no_key = dict(summary, published=[], failed=[], no_claude=True, no_key=True,
                  usage={"estimated_input_tokens": 5000}, cost_usd=0.01)
    subject, body = earnings_message(report, no_key, None)
    assert subject.endswith("0 published, 0 failed")
    assert "no Claude key, nothing was generated" in body and "5,000" in body


# --- fix round 1 (R12) -----------------------------------------------------------

def pending_daily(world, tags, batch_id="batch-9"):
    state = st.load_state(world.store)
    state["pending_batches"].append({"batch_id": batch_id, "run_id": "old",
                                     "jobs_key": run_key("old", "jobs.json"), "tags": tags})
    st.save_state(world.store, state)


def sent_symbols(client, i=0):
    return {re.search(r"\((\S+)\)</company>", r["params"]["messages"][0]["content"]).group(1)
            for r in client.submits[i]}


def test_backfill_skips_quarters_in_a_pending_daily_batch(world):
    backfill_world(world)
    world.fmp.dates["RY.TO"] = [{"fiscalYear": 2026, "quarter": 3, "date": "2026-11-01"}]
    pending_daily(world, ["RY.TO|2026-Q3"])
    client = FakeBatch()
    assert submit(world, "backfill-1", client)["targets"] == 3
    assert "RY.TO" not in sent_symbols(client)


def test_backfill_skips_exhausted_quarters(world):
    backfill_world(world)
    state = st.load_state(world.store)
    state["attempts"]["AAPL|2026-Q1"] = e.MAX_ATTEMPTS
    state["attempts"]["MSFT|2026-Q1"] = e.MAX_ATTEMPTS - 1
    st.save_state(world.store, state)
    client = FakeBatch()
    submit(world, "backfill-1", client)
    assert sent_symbols(client) == {"RY.TO", "BBD-B.TO", "MSFT"}
    assert world.state()["attempts"]["MSFT|2026-Q1"] == e.MAX_ATTEMPTS     # counted at submit
    bf.backfill_discarded("backfill-1", world.store)
    submit(world, "backfill-2", client)                  # second and last paid try
    assert sent_symbols(client, 1) == {"RY.TO", "BBD-B.TO"}
    bf.backfill_discarded("backfill-2", world.store)
    assert submit(world, "backfill-3", client)["status"] == "nothing_to_do"
    assert len(client.submits) == 2


class DiesInSubmit(FakeBatch):
    """The API accepted the batch, then the container died before the id came back."""

    def submit(self, requests):
        super().submit(requests)
        raise RuntimeError("container killed mid-submit")


def test_killed_in_submit_never_resubmits_and_says_so(world):
    world.fmp.report("RY.TO", "2026-11-20", 2026, 4)
    client = DiesInSubmit()
    with pytest.raises(RuntimeError, match="mid-submit"):
        world.run("earnings-1", client)
    marker = world.state()["pending_batches"]
    assert marker[0]["batch_id"] is None and marker[0]["tags"] == ["RY.TO|2026-Q4"]
    good = FakeBatch()
    report = world.run("earnings-2", good)
    assert len(client.submits) == 1 and good.submits == [] and good.status_calls == 0
    assert report.verdict == "warn"
    assert world.summary("earnings-2")["unrecorded_submits"] == ["RY.TO|2026-Q4"]
    body = world.sent[-1][1]
    assert "without a recorded batch id" in body and "Anthropic console" in body
    # the backfill skips it too
    world.fmp.dates = {"RY.TO": [{"fiscalYear": 2026, "quarter": 4, "date": "2026-11-20"}]}
    assert submit(world, "backfill-1", good)["status"] == "nothing_to_do"


def test_crash_between_note_and_index_is_repaired_without_claude(world, monkeypatch):
    world.fmp.report("RY.TO", "2026-11-20", 2026, 4)
    client = FakeBatch()
    real = e._index_note
    monkeypatch.setattr(e, "_index_note", lambda live, note: (_ for _ in ()).throw(
        RuntimeError("S3 hiccup")))
    with pytest.raises(RuntimeError, match="S3 hiccup"):
        world.run("earnings-1", client)
    assert world.live.exists(st.note_key("RY.TO", "2026-Q4"))
    assert not world.live.exists(st.company_index_key("RY.TO"))
    monkeypatch.setattr(e, "_index_note", real)
    world.run("earnings-2", client)
    assert len(client.submits) == 1
    assert world.live.get_json(st.company_index_key("RY.TO"))["quarters"][0]["quarter"] == "2026-Q4"
    assert world.live.get_json(st.LATEST_KEY) == {"RY.TO": "2026-Q4"}


def test_ensure_indexed_leaves_withdrawn_alone(world):
    e.publish_note(world.live, stored("RY.TO", 2026, 3))
    e.pull_note(world.live, "RY.TO", "2026-Q3")
    assert e.ensure_indexed(world.live, "RY.TO", "2026-Q3") is False
    assert world.live.get_json(st.company_index_key("RY.TO"))["quarters"][0]["withdrawn"] is True
    assert e.ensure_indexed(world.live, "NOPE", "2026-Q1") is False


def test_pull_note_takes_the_lock(world):
    e.publish_note(world.live, stored("RY.TO", 2026, 3))
    st.acquire_lock(world.store, "earnings-1", NOW)
    with pytest.raises(RuntimeError, match="another earnings run holds the lock"):
        e.pull_note(world.live, "RY.TO", "2026-Q3", lock_store=world.store, now=NOW)
    assert world.live.get_json(st.LATEST_KEY) == {"RY.TO": "2026-Q3"}
    st.release_lock(world.store, "earnings-1")
    e.pull_note(world.live, "RY.TO", "2026-Q3", lock_store=world.store, now=NOW)
    assert world.live.get_json(st.LATEST_KEY) == {}
    assert not world.store.exists(st.LOCK_KEY)


def test_publishing_a_discarded_backfill_is_refused(world):
    backfill_world(world)
    client = FakeBatch()
    submit(world, "backfill-1", client)
    bf.backfill_stage("backfill-1", world.store, batch_client=client)
    bf.backfill_discarded("backfill-1", world.store)
    with pytest.raises(RuntimeError, match="not the staged backfill"):
        bf.backfill_publish("backfill-1", world.store, world.live)
    assert not world.live.exists(st.LATEST_KEY)


def test_missing_staged_note_is_a_clear_error(world):
    backfill_world(world)
    client = FakeBatch()
    submit(world, "backfill-1", client)
    bf.backfill_stage("backfill-1", world.store, batch_client=client)
    world.store.delete(run_key("backfill-1", "notes/BBD-B.TO_2026-Q3.json"))
    with pytest.raises(RuntimeError, match="staged note .*BBD-B.TO_2026-Q3.json is missing"):
        bf.backfill_publish("backfill-1", world.store, world.live)
    assert world.state()["backfill_pending"] == "backfill-1"        # still settle-able


def test_stage_refuses_a_batch_that_has_not_ended(world):
    backfill_world(world)
    client = FakeBatch(statuses=["in_progress"])
    submit(world, "backfill-1", client)
    with pytest.raises(RuntimeError, match="not ended"):
        bf.backfill_stage("backfill-1", world.store, batch_client=client)
    assert not world.store.exists(run_key("backfill-1", "results.json"))
    assert not world.store.exists(run_key("backfill-1", "verdict.json"))


# --- fix wave: held email, saved-results guard, SIGTERM ---------------------------

def test_backfill_stage_emails_held_for_approval(world):
    backfill_world(world)
    client = FakeBatch(bad={"AAPL"})
    submit(world, "backfill-1", client)
    bf.backfill_stage("backfill-1", world.store, batch_client=client, notifier=world,
                      state_bucket="state-bkt", now=NOW, log=lambda *a: None)
    assert len(world.sent) == 1
    subject, body = world.sent[0]
    assert subject == "[Fintank] Earnings backfill backfill-1 held - WARN, 3 staged, 1 failed"
    assert "Staged (passed the checks): 3" in body and "Failed: 1" in body
    assert "  AAPL 2026-Q1: " in body and "4.1 billion" in body        # the reason
    assert "Tokens: 4,000 in, 2,000 out; cost $0.03" in body           # 4 x (1000, 500)
    assert "Publish:  python -m pipelines approve backfill-1" in body
    assert "Discard:  python -m pipelines discard backfill-1" in body
    assert ("python -m pipelines earnings-backfill stage --run-id <new-id> "
            "--from-results backfill-1") in body
    assert "prefix=runs/backfill-1/report.json" in body


def test_backfill_restage_email_points_at_the_manual_steps(world):
    backfill_world(world)
    client = FakeBatch()
    submit(world, "backfill-1", client)
    bf.backfill_stage("backfill-1", world.store, batch_client=client)
    bf.backfill_discarded("backfill-1", world.store)
    bf.backfill_stage("backfill-2", world.store, from_results="backfill-1", notifier=world)
    subject, body = world.sent[-1]
    assert "backfill-2 held - PASS, 4 staged, 0 failed" in subject
    assert "earnings-backfill publish --run-id backfill-2" in body
    assert "earnings-backfill discarded --run-id backfill-2" in body
    assert "paid once, by backfill-1" in body
    assert "--from-results backfill-1" in body


def test_backfill_held_email_caps_the_failure_list():
    from pipelines.notify import BACKFILL_FAILED_LISTED, backfill_held_message
    failed = [{"symbol": f"S{i}", "quarter": "2026-Q1", "reasons": ["too short"]}
              for i in range(BACKFILL_FAILED_LISTED + 5)]
    report = RunReport("backfill-9", "earnings", "backfill", "2026-11-21T00:00:00Z")
    verdict = {"verdict": "warn", "passed": 0, "failed": len(failed)}
    _, body = backfill_held_message(report, {"failed": failed, "usage": {}, "cost_usd": 0},
                                    verdict, None)
    assert body.count("too short") == BACKFILL_FAILED_LISTED
    assert "... and 5 more (runs/backfill-9/failed/)" in body


def test_backfill_status_doc_carries_targets_and_tokens(world):
    backfill_world(world)
    no_claude = submit(world, "backfill-1", FakeBatch(), no_claude=True)
    saved = world.store.get_json(run_key("backfill-1", "backfill-status.json"))
    assert saved == no_claude
    assert saved["targets"] == 4 and saved["estimated_input_tokens"] > 0
    world.fmp.dates = {}
    submit(world, "backfill-2", FakeBatch())
    nothing = world.store.get_json(run_key("backfill-2", "backfill-status.json"))
    assert (nothing["status"], nothing["targets"], nothing["estimated_input_tokens"]) == (
        "nothing_to_do", 0, 0)


def test_paid_backfill_submit_refused_while_saved_results_exist(world):
    backfill_world(world)
    client = FakeBatch()
    submit(world, "backfill-1", client)
    bf.backfill_stage("backfill-1", world.store, batch_client=client)
    bf.backfill_discarded("backfill-1", world.store)
    assert world.state()["backfill_runs"] == ["backfill-1"]
    with pytest.raises(RuntimeError, match=r"--from-results backfill-1.*--force"):
        submit(world, "backfill-2", client)
    assert len(client.submits) == 1
    assert not world.store.exists(st.LOCK_KEY)
    assert submit(world, "backfill-3", client, no_claude=True)["status"] == "no_claude"
    assert submit(world, "backfill-4", client, key="unset")["status"] == "no_claude"
    forced = bf.backfill_submit("backfill-5", "fmp-test", FAKE_KEY, world.store, world.live,
                                batch_client=client, force=True, get=world.fmp,
                                log=lambda *a: None, now=NOW)
    assert forced["status"] == "submitted" and len(client.submits) == 2


def test_publishing_a_backfill_clears_its_saved_results_guard(world):
    backfill_world(world)
    client = FakeBatch(bad={"AAPL"})
    submit(world, "backfill-1", client)
    bf.backfill_stage("backfill-1", world.store, batch_client=client)
    bf.backfill_discarded("backfill-1", world.store)
    bf.backfill_stage("backfill-2", world.store, from_results="backfill-1")
    assert world.state()["backfill_runs"] == ["backfill-1"]     # a re-check adds nothing
    bf.backfill_publish("backfill-2", world.store, world.live)
    assert world.state()["backfill_runs"] == []                 # source settled too
    world.fmp.dates["AAPL"] = [{"fiscalYear": 2026, "quarter": 1, "date": "2026-11-01"}]
    assert submit(world, "backfill-3", client)["status"] == "submitted"


class KilledWhilePolling(FakeBatch):
    """SIGTERM arrives mid-poll; the CLI's handler turns it into SystemExit."""

    def status(self, batch_id):
        raise SystemExit(143)


def test_sigterm_during_daily_run_releases_the_lock(world):
    world.fmp.report("RY.TO", "2026-11-20", 2026, 4)
    with pytest.raises(SystemExit):
        world.run("earnings-1", KilledWhilePolling())
    assert not world.store.exists(st.LOCK_KEY)
    assert world.state()["pending_batches"][0]["batch_id"] == "batch-1"   # never resubmitted


def test_sigterm_during_backfill_step_releases_the_lock(world):
    backfill_world(world)
    submit(world, "backfill-1", FakeBatch())
    with pytest.raises(SystemExit):
        bf.backfill_check("backfill-1", world.store, batch_client=KilledWhilePolling())
    assert not world.store.exists(st.LOCK_KEY)
