"""The earnings job: the daily run, the backfill steps, and publishing notes.

Spend safety. Claude is called only when a key is set and `no_claude` is off;
the real client is built in one place (`_claude`) and nowhere else. A batch ID
is saved to state before polling starts, and its notes are skipped while it is
pending, so a crash or a timed-out wait never submits the same notes twice.

Publishing writes the note, then the company index, then latest.json. Daily
notes that pass the checks go live at once; backfill notes are staged under
runs/<id>/notes/ and go live only through backfill_publish (after approve)."""
from __future__ import annotations

import datetime as dt
import time
from contextlib import contextmanager
from dataclasses import asdict

from pipelines.checks import FAIL, PASS, WARN, CheckResult
from pipelines.earnings_checks import SECTION_KEYS, check_note  # noqa: F401 (re-export)
from pipelines.earnings_claude import AnthropicBatchClient, BatchResult, cost_usd, has_key
from pipelines.earnings_fmp import (covered_symbols, fetch_calendar, fetch_transcript,
                                    http_get_json, transcript_dates)
from pipelines.earnings_prompt import NoteJob, build_request, to_stored_note
from pipelines.earnings_state import (LATEST_KEY, WAIT_DAYS, acquire_lock, company_index_key,
                                      expire_waiting, is_written, load_state, mark_handled,
                                      note_key, release_lock, save_state, update_waiting)
from pipelines.notify import earnings_message
from pipelines.report import RunReport, now_iso
from pipelines.results import StageResult, redact
from pipelines.store import run_key

DAILY_CAP = 150
BACKFILL_CAP = 800
MAX_ATTEMPTS = 2
POLL_SECONDS = 300
DAILY_MAX_WAIT_SECONDS = 10800
# A transcript dated this many days before the calendar's report date is an
# older quarter's call, not this report's: keep waiting instead of writing it.
CALL_DATE_SLACK_DAYS = 2
LOCK_HELD = "another earnings run holds the lock"


def _tag(symbol, quarter) -> str:
    return f"{symbol}|{quarter}"


# --- publishing -----------------------------------------------------------------

def _quarter_order(entry) -> tuple:
    return (int(entry["fiscal_year"]), int(entry["fiscal_quarter"]))


def _set_latest(live, symbol, quarters) -> None:
    latest = live.get_json(LATEST_KEY) or {}
    newest = next((q["quarter"] for q in quarters if not q.get("withdrawn")), None)
    if newest:
        latest[symbol] = newest
    else:
        latest.pop(symbol, None)
    live.put_json(LATEST_KEY, latest)


def publish_note(live, note: dict) -> None:
    symbol = note["symbol"]
    quarter = f"{note['fiscal_year']}-Q{note['fiscal_quarter']}"
    live.put_json(note_key(symbol, quarter), note)
    index = live.get_json(company_index_key(symbol)) or {"symbol": symbol, "quarters": []}
    entry = {"quarter": quarter, "fiscal_year": note["fiscal_year"],
             "fiscal_quarter": note["fiscal_quarter"], "report_date": note["report_date"],
             "lean": note["lean"], "headline": note["headline"],
             "key_points": list(note["key_points"]), "withdrawn": False}
    quarters = [q for q in index.get("quarters", []) if q.get("quarter") != quarter] + [entry]
    quarters.sort(key=_quarter_order, reverse=True)
    live.put_json(company_index_key(symbol), {"symbol": symbol, "quarters": quarters})
    _set_latest(live, symbol, quarters)


def pull_note(live, symbol, quarter) -> None:
    index = live.get_json(company_index_key(symbol)) or {}
    quarters = index.get("quarters", [])
    entry = next((q for q in quarters if q.get("quarter") == quarter), None)
    if entry is None:
        raise KeyError(f"{symbol} has no {quarter} note")
    entry["withdrawn"] = True
    live.put_json(company_index_key(symbol), {"symbol": symbol, "quarters": quarters})
    _set_latest(live, symbol, quarters)


def _previous_note(live, symbol, quarter):
    for entry in (live.get_json(company_index_key(symbol)) or {}).get("quarters", []):
        if entry.get("withdrawn") or entry.get("quarter") == quarter:
            continue
        if _quarter_order(entry) < tuple(int(x) for x in quarter.split("-Q")):
            return live.get_json(note_key(symbol, entry["quarter"]))
    return None


# --- shared pieces --------------------------------------------------------------

@contextmanager
def _locked(store, run_id, now, log):
    if not acquire_lock(store, run_id, now, log=log):
        raise RuntimeError(LOCK_HELD)
    try:
        yield
    finally:
        release_lock(store, run_id)


def _claude(anthropic_key, batch_client, no_claude):
    """The batch client, or None when Claude must not be called. The real client
    is only ever built here, and only with a key."""
    if no_claude or not has_key(anthropic_key):
        return None
    return batch_client if batch_client is not None else AnthropicBatchClient(anthropic_key)


def _save_jobs(store, run_id, jobs) -> str:
    key = run_key(run_id, "jobs.json")
    store.put_json(key, [{"custom_id": cid, "job": asdict(job)} for cid, job in jobs])
    return key


def _load_jobs(store, key) -> dict:
    return {row["custom_id"]: NoteJob(**row["job"]) for row in store.get_json(key) or []}


def _requests(jobs) -> list:
    return [build_request(job, i) for i, (_, job) in enumerate(jobs)]


def _numbered(jobs) -> list:
    """[(custom_id, job)] in batch order; custom IDs never carry the symbol."""
    return [(build_request(job, i)["custom_id"], job) for i, job in enumerate(jobs)]


def _write_requests(store, run_id, jobs) -> int:
    """No-Claude path: save what would be sent. Returns estimated input tokens."""
    requests = _requests(jobs)
    ids = {cid: {"symbol": job.symbol, "quarter": job.quarter} for cid, job in jobs}
    store.put_json(run_key(run_id, "requests.json"), {"requests": requests, "ids": ids})
    text = sum(len(r["params"]["system"]) + len(r["params"]["messages"][0]["content"])
               for r in requests)
    return text // 4


def _add_usage(totals, usage) -> None:
    for k in ("input_tokens", "output_tokens"):
        totals[k] = totals.get(k, 0) + int((usage or {}).get(k) or 0)


def _judge(job, result: BatchResult) -> list:
    """Failure reasons for one batch result; empty means it may publish."""
    if result.kind != "succeeded" or result.output is None:
        return [f"batch result {result.kind}" + (f": {result.error}" if result.error else "")]
    return check_note(result.output, job.transcript, job.estimates, job.previous_note)


def _write_failure(store, run_id, job, result, reasons) -> dict:
    item = {"symbol": job.symbol, "quarter": job.quarter, "reasons": reasons}
    store.put_json(run_key(run_id, f"failed/{job.symbol}_{job.quarter}.json"),
                   dict(item, kind=result.kind, error=result.error, output=result.output))
    return item


def _newest_transcript(fmp_key, symbol, get):
    dates = transcript_dates(fmp_key, symbol, get=get)
    return dates[0] if dates else None


def _call_matches_report(call_date, report_date) -> bool:
    try:
        call = dt.date.fromisoformat(str(call_date)[:10])
        report = dt.date.fromisoformat(str(report_date)[:10])
    except ValueError:
        return False
    return call >= report - dt.timedelta(days=CALL_DATE_SLACK_DAYS)


def _empty_summary(no_claude=False) -> dict:
    return {"published": [], "failed": [], "waiting": [], "dropped": [],
            "pending_batches": [], "usage": {}, "cost_usd": 0.0, "no_claude": no_claude}


# --- daily run --------------------------------------------------------------------

def _collect(batch, client, store, live, state, run_id, summary, now, log) -> None:
    """Check and publish one ended batch; record failures; drop it from pending."""
    jobs = _load_jobs(store, batch["jobs_key"])
    results = list(client.results(batch["batch_id"]))
    store.put_json(run_key(batch["run_id"], "results.json"), [asdict(r) for r in results])
    generated_at = now.isoformat(timespec="seconds")
    for result in results:
        job = jobs.get(result.custom_id)
        if job is None:
            log(f"batch {batch['batch_id']}: unknown custom_id {result.custom_id}")
            continue
        tag = _tag(job.symbol, job.quarter)
        _add_usage(summary["usage"], result.usage)
        state["attempts"][tag] = state["attempts"].get(tag, 0) + 1
        reasons = _judge(job, result)
        if not reasons:
            if not is_written(state, live, job.symbol, job.quarter):
                publish_note(live, to_stored_note(job, result.output, generated_at))
                state["written"].append(tag)
                summary["published"].append({"symbol": job.symbol, "quarter": job.quarter,
                                             "lean": result.output["lean"]})
            mark_handled(state, job.symbol, job.report_date, "published")
            _unwait(state, job)
            continue
        summary["failed"].append(_write_failure(store, run_id, job, result, reasons))
        if state["attempts"][tag] >= MAX_ATTEMPTS:
            mark_handled(state, job.symbol, job.report_date, "max_attempts")
            _unwait(state, job)
    state["pending_batches"] = [b for b in state["pending_batches"]
                                if b["batch_id"] != batch["batch_id"]]


def _unwait(state, job) -> None:
    waiting = state["waiting"].get(job.symbol)
    if waiting and waiting.get("report_date") == job.report_date:
        del state["waiting"][job.symbol]


def _daily_jobs(fmp_key, live, state, covered, get, log) -> list:
    pending = {t for b in state["pending_batches"] for t in b.get("tags", [])}
    jobs = []
    for symbol in sorted(state["waiting"], key=lambda s: (state["waiting"][s]["first_seen"], s)):
        if len(jobs) >= DAILY_CAP:
            break
        wait = state["waiting"][symbol]
        try:
            newest = _newest_transcript(fmp_key, symbol, get)
            if newest is None or not _call_matches_report(newest[2], wait["report_date"]):
                continue                                    # transcript not out yet
            fy, q, _ = newest
            quarter = f"{fy}-Q{q}"
            tag = _tag(symbol, quarter)
            if tag in pending:
                continue
            if is_written(state, live, symbol, quarter):
                mark_handled(state, symbol, wait["report_date"], "published")
                del state["waiting"][symbol]
                continue
            if state["attempts"].get(tag, 0) >= MAX_ATTEMPTS:
                mark_handled(state, symbol, wait["report_date"], "max_attempts")
                del state["waiting"][symbol]
                continue
            content, call_date = fetch_transcript(fmp_key, symbol, fy, q, get=get)
        except Exception as e:  # noqa: BLE001 — one symbol must not stop the run
            log(f"{symbol}: transcript not ready ({redact(str(e))})")
            continue
        info = covered.get(symbol, {"region": "", "name": symbol})
        jobs.append(NoteJob(symbol=symbol, company_name=info["name"], region=info["region"],
                            fiscal_year=fy, fiscal_quarter=q, report_date=wait["report_date"],
                            call_date=call_date or newest[2], transcript=content,
                            estimates=wait.get("estimates") or {},
                            previous_note=_previous_note(live, symbol, quarter)))
    return jobs


def _finish(report, summary, store, notifier, state_bucket, run_id, verdict) -> RunReport:
    summary["waiting"] = summary.get("waiting") or []
    summary["cost_usd"] = round(summary["cost_usd"] or cost_usd(summary["usage"]), 4)
    stage = StageResult("earnings.notes", attempted=len(summary["published"]) + len(summary["failed"]),
                        saved=len(summary["published"]), failed=len(summary["failed"]),
                        failed_items=[f"{f['symbol']} {f['quarter']}" for f in summary["failed"]])
    report.add_stage(stage, 0)
    report.counts = {"published": len(summary["published"]), "failed": len(summary["failed"]),
                     "waiting": len(summary["waiting"]), "dropped": len(summary["dropped"])}
    report.finish(verdict_override=verdict)
    store.put_json(run_key(run_id, "summary.json"), summary)
    store.put_json(run_key(run_id, "report.json"), report.to_dict())
    if notifier is not None:
        notifier.send(*earnings_message(report, summary, state_bucket))
    return report


def _refuse(report, summary, store, notifier, state_bucket, run_id, why, write=True):
    summary["message"] = why
    report.add_checks([CheckResult("earnings.run", FAIL, None, None, why)])
    if not write:   # lock held: another run owns the run folder and state
        report.finish(verdict_override=FAIL)
        if notifier is not None:
            notifier.send(*earnings_message(report, summary, state_bucket))
        return report
    return _finish(report, summary, store, notifier, state_bucket, run_id, FAIL)


def run_daily(run_id, fmp_key, anthropic_key, store, live, *, batch_client=None,
              no_claude=False, notifier=None, now=None, get=http_get_json,
              sleep=time.sleep, log=print, state_bucket=None) -> RunReport:
    now = now or dt.datetime.now(dt.timezone.utc)
    today = now.date()
    report = RunReport(run_id, "earnings", "daily", now_iso())
    summary = _empty_summary(no_claude)
    if not acquire_lock(store, run_id, now, log=log):
        return _refuse(report, summary, store, notifier, state_bucket, run_id,
                       LOCK_HELD, write=False)
    try:
        state = load_state(store)
        if state.get("backfill_pending"):
            return _refuse(report, summary, store, notifier, state_bucket, run_id,
                           f"backfill {state['backfill_pending']} is staged and waiting for "
                           "approve/discard; the daily run will not start until it is "
                           "settled")
        client = _claude(anthropic_key, batch_client, no_claude)
        if client is None and not no_claude:
            summary["no_key"] = True
        if client is not None:
            for batch in list(state["pending_batches"]):
                if client.status(batch["batch_id"]) == "ended":
                    _collect(batch, client, store, live, state, run_id, summary, now, log)
            save_state(store, state)

        covered = covered_symbols(live.get_json)
        start = (dt.date.fromisoformat(state["last_run"]) if state.get("last_run")
                 else today - dt.timedelta(days=WAIT_DAYS))
        update_waiting(state, fetch_calendar(fmp_key, start, today, get=get), covered, today)
        summary["dropped"] = expire_waiting(state, today)
        jobs = _numbered(_daily_jobs(fmp_key, live, state, covered, get, log))
        state["last_run"] = today.isoformat()

        if jobs and client is None:
            tokens = _write_requests(store, run_id, jobs)
            summary["usage"] = {"estimated_input_tokens": tokens}
            summary["cost_usd"] = cost_usd({"input_tokens": tokens})
            summary["requests"] = len(jobs)
        elif jobs:
            jobs_key = _save_jobs(store, run_id, jobs)
            batch_id = client.submit(_requests(jobs))
            batch = {"batch_id": batch_id, "run_id": run_id, "jobs_key": jobs_key,
                     "submitted_at": now.isoformat(),
                     "tags": [_tag(j.symbol, j.quarter) for _, j in jobs]}
            state["pending_batches"].append(batch)
            save_state(store, state)                  # before polling: never resubmit
            waited, status = 0, client.status(batch_id)
            while status != "ended" and waited < DAILY_MAX_WAIT_SECONDS:
                sleep(POLL_SECONDS)
                waited += POLL_SECONDS
                status = client.status(batch_id)
            if status == "ended":
                _collect(batch, client, store, live, state, run_id, summary, now, log)
            else:
                log(f"batch {batch_id} still {status}; the next run collects it")
        save_state(store, state)
        summary["waiting"] = sorted(state["waiting"])
        summary["pending_batches"] = [b["batch_id"] for b in state["pending_batches"]]
        verdict = WARN if summary["failed"] else PASS
        return _finish(report, summary, store, notifier, state_bucket, run_id, verdict)
    finally:
        release_lock(store, run_id)


# --- backfill steps -------------------------------------------------------------

def _status_key(run_id) -> str:
    return run_key(run_id, "backfill-status.json")


def _backfill_jobs(fmp_key, live, state, covered, get, log) -> list:
    jobs = []
    for symbol in sorted(covered):
        if len(jobs) >= BACKFILL_CAP:
            break
        try:
            newest = _newest_transcript(fmp_key, symbol, get)
            if newest is None:
                continue
            fy, q, call = newest
            if is_written(state, live, symbol, f"{fy}-Q{q}"):
                continue
            content, call_date = fetch_transcript(fmp_key, symbol, fy, q, get=get)
        except Exception as e:  # noqa: BLE001
            log(f"{symbol}: skipped ({redact(str(e))})")
            continue
        info = covered[symbol]
        call_date = call_date or call
        jobs.append(NoteJob(symbol=symbol, company_name=info["name"], region=info["region"],
                            fiscal_year=fy, fiscal_quarter=q, report_date=str(call_date)[:10],
                            call_date=call_date, transcript=content,
                            estimates={"eps_estimate": None, "eps_actual": None,
                                       "revenue_estimate": None, "revenue_actual": None},
                            previous_note=None))
    return jobs


def backfill_submit(run_id, fmp_key, anthropic_key, store, live, *, batch_client,
                    no_claude=False, get=http_get_json, log=print, now=None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    with _locked(store, run_id, now, log):
        state = load_state(store)
        pending = state.get("backfill_pending")
        if pending == run_id:
            saved = store.get_json(_status_key(run_id)) or {}
            if saved.get("status") == "submitted":
                return saved                          # a retried task: never resubmit
            raise RuntimeError(f"backfill {run_id} may already have submitted a batch "
                               f"(status {saved.get('status')!r}); check the Anthropic "
                               "console before doing anything else")
        if pending:
            raise RuntimeError(f"backfill {pending} is still waiting for approve/discard")
        jobs = _numbered(_backfill_jobs(fmp_key, live, state, covered_symbols(live.get_json),
                                        get, log))
        client = _claude(anthropic_key, batch_client, no_claude)
        if not jobs:
            status = {"status": "nothing_to_do", "batch_id": None, "targets": 0}
        elif client is None:
            tokens = _write_requests(store, run_id, jobs)
            status = {"status": "no_claude", "batch_id": None, "targets": len(jobs),
                      "estimated_input_tokens": tokens,
                      "estimated_input_usd": round(cost_usd({"input_tokens": tokens}), 2),
                      "no_key": not no_claude}
        else:
            _save_jobs(store, run_id, jobs)
            store.put_json(_status_key(run_id), {"status": "submitting", "batch_id": None})
            state["backfill_pending"] = run_id
            save_state(store, state)                  # blocks the daily run and a resubmit
            batch_id = client.submit(_requests(jobs))
            status = {"status": "submitted", "batch_id": batch_id, "targets": len(jobs)}
            store.put_json(_status_key(run_id), status)
            for _, job in jobs:                       # the paid attempt counts now
                tag = _tag(job.symbol, job.quarter)
                state["attempts"][tag] = state["attempts"].get(tag, 0) + 1
            save_state(store, state)
            return status
        store.put_json(_status_key(run_id), status)
        return status


def backfill_check(run_id, store, *, batch_client, now=None, log=print) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    with _locked(store, run_id, now, log):
        saved = store.get_json(_status_key(run_id)) or {}
        if not saved.get("batch_id"):
            raise RuntimeError(f"backfill {run_id} has no submitted batch")
        raw = batch_client.status(saved["batch_id"])
        status = dict(saved, status="ended" if raw == "ended" else "in_progress")
        store.put_json(_status_key(run_id), status)
        return status


def backfill_stage(run_id, store, *, batch_client=None, from_results: str | None = None,
                   now=None, log=print) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    with _locked(store, run_id, now, log):
        state = load_state(store)
        pending = state.get("backfill_pending")
        if pending and pending != run_id:
            raise RuntimeError(f"backfill {pending} is still waiting for approve/discard")
        source = from_results or run_id
        jobs = _load_jobs(store, run_key(source, "jobs.json"))
        if from_results:                              # re-check saved results: no Claude
            results = [BatchResult(**r) for r in
                       store.get_json(run_key(from_results, "results.json")) or []]
        else:
            if batch_client is None:
                raise ValueError("backfill_stage needs a batch client or from_results")
            batch_id = (store.get_json(_status_key(run_id)) or {}).get("batch_id")
            if not batch_id:
                raise RuntimeError(f"backfill {run_id} has no submitted batch")
            results = list(batch_client.results(batch_id))
            store.put_json(run_key(run_id, "results.json"), [asdict(r) for r in results])
        report = RunReport(run_id, "earnings", "backfill", now_iso())
        summary = _empty_summary()
        staged, generated_at = [], now.isoformat(timespec="seconds")
        for result in results:
            job = jobs.get(result.custom_id)
            if job is None:
                log(f"unknown custom_id {result.custom_id}")
                continue
            _add_usage(summary["usage"], result.usage)
            reasons = _judge(job, result)
            if reasons:
                summary["failed"].append(_write_failure(store, run_id, job, result, reasons))
                continue
            key = run_key(run_id, f"notes/{job.symbol}_{job.quarter}.json")
            store.put_json(key, to_stored_note(job, result.output, generated_at))
            staged.append(key)
            summary["published"].append({"symbol": job.symbol, "quarter": job.quarter,
                                         "lean": result.output["lean"]})
        store.put_json(run_key(run_id, "staged.json"), staged)
        state["backfill_pending"] = run_id
        save_state(store, state)
        verdict = {"run_id": run_id, "verdict": WARN if summary["failed"] else PASS,
                   "hold": True, "passed": len(staged), "failed": len(summary["failed"])}
        summary["staged_not_live"] = True
        _finish(report, summary, store, None, None, run_id, verdict["verdict"])
        store.put_json(run_key(run_id, "verdict.json"), verdict)
        return verdict


def backfill_publish(run_id, store, live, *, now=None, log=print) -> int:
    now = now or dt.datetime.now(dt.timezone.utc)
    with _locked(store, run_id, now, log):
        state = load_state(store)
        count = 0
        for key in store.get_json(run_key(run_id, "staged.json")) or []:
            note = store.get_json(key)
            quarter = f"{note['fiscal_year']}-Q{note['fiscal_quarter']}"
            if is_written(state, live, note["symbol"], quarter):
                continue                              # never overwrite a live note
            publish_note(live, note)
            state["written"].append(_tag(note["symbol"], quarter))
            count += 1
            save_state(store, state)
        if state.get("backfill_pending") == run_id:
            state["backfill_pending"] = None
        save_state(store, state)
        return count


def backfill_discarded(run_id, store, *, now=None, log=print) -> None:
    """Nothing goes live; runs/<id>/results.json stays for --from-results."""
    now = now or dt.datetime.now(dt.timezone.utc)
    with _locked(store, run_id, now, log):
        state = load_state(store)
        if state.get("backfill_pending") == run_id:
            state["backfill_pending"] = None
            save_state(store, state)
