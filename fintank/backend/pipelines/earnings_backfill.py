"""Earnings backfill steps: one task each in the backfill state machine.

submit -> check (looped) -> stage -> approve gate -> publish | discarded. Each
step holds the run lock. Notes are staged under runs/<id>/notes/ and go live
only through backfill_publish. A quarter already written, in a pending daily
batch, or attempted MAX_ATTEMPTS times is never sent again; re-checking a
discarded backfill goes through `stage --from-results`, which is free, and a
paid submit is refused while an earlier backfill's results are still saved
(state["backfill_runs"]) unless forced.

Backfill notes use the call date as report_date: the backfill has no calendar
row for old quarters, so the transcript's call date is the best report date.

Caps and attempt limits are read from pipelines.earnings at call time."""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict

from pipelines import earnings as core
from pipelines.checks import PASS, WARN
from pipelines.earnings import (_add_usage, _claude, _empty_summary, _finish, _judge,
                                _load_jobs, _locked, _newest_transcript, _numbered,
                                _requests, _save_jobs, _tag, _write_failure,
                                _write_requests, ensure_indexed, pending_tags,
                                publish_note)
from pipelines.earnings_claude import BatchResult, cost_usd
from pipelines.earnings_fmp import covered_symbols, fetch_transcript, http_get_json
from pipelines.earnings_prompt import NoteJob, to_stored_note
from pipelines.earnings_state import is_written, load_state, save_state
from pipelines.notify import backfill_held_message, backfill_refused_message
from pipelines.report import RunReport, now_iso
from pipelines.results import redact
from pipelines.store import run_key

def _status_key(run_id) -> str:
    return run_key(run_id, "backfill-status.json")


def earlier_results(store, state, run_id=None) -> list:
    """Backfill runs whose saved results.json can still be re-checked for free."""
    return [r for r in state.get("backfill_runs") or []
            if r != run_id and store.exists(run_key(r, "results.json"))]


def _backfill_jobs(fmp_key, live, state, covered, get, log) -> list:
    pending, jobs = pending_tags(state), []
    for symbol in sorted(covered):
        if len(jobs) >= core.BACKFILL_CAP:
            break
        try:
            newest = _newest_transcript(fmp_key, symbol, get)
            if newest is None:
                continue
            fy, q, call = newest
            tag = _tag(symbol, f"{fy}-Q{q}")
            if (tag in pending or state["attempts"].get(tag, 0) >= core.MAX_ATTEMPTS
                    or is_written(state, live, symbol, f"{fy}-Q{q}")):
                continue
            content, call_date = fetch_transcript(fmp_key, symbol, fy, q, get=get)
        except Exception as e:  # noqa: BLE001
            log(f"{symbol}: skipped ({redact(str(e))})")
            continue
        info = covered[symbol]
        call_date = call_date or call
        # No calendar row for an old quarter: the call date stands in as report_date.
        jobs.append(NoteJob(symbol=symbol, company_name=info["name"], region=info["region"],
                            fiscal_year=fy, fiscal_quarter=q, report_date=str(call_date)[:10],
                            call_date=call_date, transcript=content,
                            estimates={"eps_estimate": None, "eps_actual": None,
                                       "revenue_estimate": None, "revenue_actual": None},
                            previous_note=None))
    return jobs


def backfill_submit(run_id, fmp_key, anthropic_key, store, live, *, batch_client,
                    no_claude=False, force=False, get=http_get_json, log=print,
                    now=None) -> dict:
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
        client = _claude(anthropic_key, batch_client, no_claude)
        earlier = earlier_results(store, state, run_id)
        if client is not None and earlier and not force:
            raise RuntimeError(backfill_refused_message(earlier))
        jobs = _numbered(_backfill_jobs(fmp_key, live, state, covered_symbols(live.get_json),
                                        get, log))
        if not jobs:
            status = {"status": "nothing_to_do", "batch_id": None, "targets": 0,
                      "estimated_input_tokens": 0}
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
                   notifier=None, state_bucket=None, now=None, log=print) -> dict:
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
            status = batch_client.status(batch_id)
            if status != "ended":
                raise RuntimeError(f"backfill {run_id} batch {batch_id} is {status!r}, "
                                   "not ended; run the check step until it ends")
            results = list(batch_client.results(batch_id))
            store.put_json(run_key(run_id, "results.json"), [asdict(r) for r in results])
            runs = state.setdefault("backfill_runs", [])
            if run_id not in runs:
                runs.append(run_id)               # a later paid submit asks for --force
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
                   "hold": True, "passed": len(staged), "failed": len(summary["failed"]),
                   "results_run": source}
        summary["staged_not_live"] = True
        _finish(report, summary, store, None, None, run_id, verdict["verdict"])
        store.put_json(run_key(run_id, "verdict.json"), verdict)
        if notifier is not None:
            notifier.send(*backfill_held_message(report, summary, verdict, state_bucket,
                                                 results_run_id=source))
        return verdict


def backfill_publish(run_id, store, live, *, now=None, log=print) -> int:
    now = now or dt.datetime.now(dt.timezone.utc)
    with _locked(store, run_id, now, log):
        state = load_state(store)
        if state.get("backfill_pending") != run_id:
            raise RuntimeError(f"backfill {run_id} is not the staged backfill (pending: "
                               f"{state.get('backfill_pending')!r}); nothing was published")
        count = 0
        for key in store.get_json(run_key(run_id, "staged.json")) or []:
            note = store.get_json(key)
            if not isinstance(note, dict):
                raise RuntimeError(f"staged note {key} is missing; nothing more was "
                                   f"published ({count} went live before it)")
            quarter = f"{note['fiscal_year']}-Q{note['fiscal_quarter']}"
            if is_written(state, live, note["symbol"], quarter):
                ensure_indexed(live, note["symbol"], quarter)
                continue                              # never overwrite a live note
            publish_note(live, note)
            state["written"].append(_tag(note["symbol"], quarter))
            count += 1
            save_state(store, state)
        state["backfill_pending"] = None
        source = (store.get_json(run_key(run_id, "verdict.json")) or {}).get("results_run")
        settled = {run_id, source}             # published: nothing left to re-check
        state["backfill_runs"] = [r for r in state.get("backfill_runs") or []
                                  if r not in settled]
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
