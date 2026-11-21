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
            "last_run": None, "backfill_pending": None}


def load_state(store) -> dict:
    state = _default_state()
    state.update(store.get_json(STATE_KEY) or {})
    return state


def save_state(store, state) -> None:
    store.put_json(STATE_KEY, state)


def _parse(ts):
    t = dt.datetime.fromisoformat(ts)
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def acquire_lock(store, run_id, now) -> bool:
    body = {"run_id": run_id, "taken_at": now.isoformat()}
    if store.put_json_if_absent(LOCK_KEY, body):
        return True
    held = store.get_json(LOCK_KEY)
    if held is None:                       # released between our two calls
        return store.put_json_if_absent(LOCK_KEY, body)
    try:
        age = now - _parse(held["taken_at"])
    except (KeyError, ValueError, TypeError):
        return False
    if age <= dt.timedelta(hours=LOCK_STALE_HOURS):
        return False
    store.delete(LOCK_KEY)
    return store.put_json_if_absent(LOCK_KEY, body)


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


def update_waiting(state, calendar_rows, covered, today) -> None:
    for row in calendar_rows:
        symbol, date = row.get("symbol"), row.get("date")
        if symbol not in covered or symbol in state["waiting"] or not date:
            continue
        if dt.date.fromisoformat(str(date)[:10]) > today:
            continue
        state["waiting"][symbol] = {
            "report_date": str(date)[:10],
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
        del state["waiting"][s]
    return dropped
