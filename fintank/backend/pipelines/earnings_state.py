"""Run bookkeeping for the earnings job: state file, run lock, S3 key names."""
from __future__ import annotations

import datetime as dt

LOCK_STALE_HOURS = 30
WAIT_DAYS = 7
STATE_KEY = "earnings/state.json"
LOCK_KEY = "earnings/lock.json"
LATEST_KEY = "earnings_notes/latest.json"


def note_key(symbol, quarter):
    return f"earnings_notes/{symbol}/{quarter}.json"


def company_index_key(symbol):
    return f"earnings_notes/{symbol}/index.json"


def _default_state():
    return {"waiting": {}, "pending_batches": [], "written": [], "attempts": {},
            "last_run": None, "backfill_pending": None,
            "handled": {}}


def load_state(store) -> dict:
    state = _default_state()
    state.update(store.get_json(STATE_KEY) or {})
    return state


def save_state(store, state) -> None:
    store.put_json(STATE_KEY, state)


def _parse(ts):
    t = dt.datetime.fromisoformat(ts)
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def acquire_lock(store, run_id, now, log=print) -> bool:
    """Take the run lock. A lock older than LOCK_STALE_HOURS is taken over.

    Residual risk: S3 has no compare-and-delete, so two runs that both judge the
    same stale lock stale can still interleave between our re-read and delete.
    We re-read before deleting and verify ownership after creating, which makes
    that window tiny but not zero; runs are daily and 30 hours apart in practice."""
    body = {"run_id": run_id, "taken_at": now.isoformat()}
    if store.put_json_if_absent(LOCK_KEY, body):
        return True
    held = store.get_json(LOCK_KEY)
    if held is None:                       # released between our two calls
        return store.put_json_if_absent(LOCK_KEY, body)
    try:
        age = now - _parse(held["taken_at"])
        held["run_id"]
    except (KeyError, ValueError, TypeError):
        log("earnings lock is malformed; delete earnings/lock.json by hand")
        return False
    if age <= dt.timedelta(hours=LOCK_STALE_HOURS):
        return False
    if store.get_json(LOCK_KEY) != held:   # someone else replaced it meanwhile
        return False
    store.delete(LOCK_KEY)
    if not store.put_json_if_absent(LOCK_KEY, body):
        return False
    after = store.get_json(LOCK_KEY)
    return bool(after) and after.get("run_id") == run_id


def release_lock(store, run_id) -> None:
    held = store.get_json(LOCK_KEY)
    if held and held.get("run_id") == run_id:
        store.delete(LOCK_KEY)


def is_written(state, live, symbol, quarter) -> bool:
    tag = f"{symbol}|{quarter}"
    if tag in state["written"]:
        return True
    if live.exists(note_key(symbol, quarter)):
        state["written"].append(tag)       # repair: state lagged the live object
        return True
    return False


def mark_handled(state, symbol, report_date, reason) -> None:
    """Remember a (symbol, report date) so the calendar window can't re-add it."""
    state.setdefault("handled", {})[f"{symbol}|{report_date}"] = reason


def update_waiting(state, calendar_rows, covered, today) -> None:
    handled = state.get("handled", {})
    oldest = today - dt.timedelta(days=WAIT_DAYS)
    for row in calendar_rows:
        symbol = row.get("symbol")
        if symbol not in covered or symbol in state["waiting"]:
            continue
        try:
            date = dt.date.fromisoformat(str(row.get("date"))[:10])
        except ValueError:
            continue
        if date > today or date < oldest or f"{symbol}|{date.isoformat()}" in handled:
            continue
        state["waiting"][symbol] = {
            "report_date": date.isoformat(),
            "first_seen": today.isoformat(),
            "estimates": {"eps_estimate": row.get("epsEstimated"),
                          "eps_actual": row.get("epsActual"),
                          "revenue_estimate": row.get("revenueEstimated"),
                          "revenue_actual": row.get("revenueActual")},
        }


def expire_waiting(state, today) -> list:
    dropped = [s for s, w in state["waiting"].items()
               if (today - dt.date.fromisoformat(w["first_seen"])).days > WAIT_DAYS]
    for s in dropped:
        mark_handled(state, s, state["waiting"][s].get("report_date"), "dropped")
        del state["waiting"][s]
    return dropped
