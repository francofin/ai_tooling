"""Emails. On AWS they go to the SNS topic (SNS_TOPIC_ARN); locally they print.

Python sends the emails whose content needs run detail — held, published,
news, crashed. The state machines send started / failed / discarded."""
from __future__ import annotations

import os

from pipelines.results import redact
from pipelines.store import REGION, aws_client

SUBJECT_MAX = 100   # SNS limit; subjects must also be plain ASCII (no em dashes)


def report_url(state_bucket, run_id) -> str:
    if not state_bucket:
        return "(dry run — report saved locally)"
    return (f"https://s3.console.aws.amazon.com/s3/object/{state_bucket}"
            f"?region={REGION}&prefix=runs/{run_id}/report.json")


class Notifier:
    def __init__(self, topic_arn=None, client=None, log=print):
        self.topic_arn = os.getenv("SNS_TOPIC_ARN") if topic_arn is None else topic_arn
        self._client = client
        self.log = log

    def send(self, subject: str, message: str) -> None:
        subject = subject[:SUBJECT_MAX]
        if not self.topic_arn:
            self.log(f"[notify] {subject}\n{message}")
            return
        client = self._client or aws_client("sns")
        client.publish(TopicArn=self.topic_arn, Subject=subject, Message=message)


def held_message(report, state_bucket, always_hold) -> tuple[str, str]:
    reason = ("a check did not pass" if report.verdict != "pass"
              else "ALWAYS_HOLD is on (the go-live guard)")
    subject = f"[Fintank] Weekly run {report.run_id} held - {report.verdict.upper()}"
    body = (f"Held for your approval because {reason}.\n\n{report.summary()}\n\n"
            f"Publish:  python -m pipelines approve {report.run_id}\n"
            f"Discard:  python -m pipelines discard {report.run_id}\n"
            "Unanswered runs are discarded automatically after 7 days.\n\n"
            f"Report: {report_url(state_bucket, report.run_id)}")
    return subject, body


def complete_message(report, publish_result, state_bucket) -> tuple[str, str]:
    subject = (f"[Fintank] Weekly run {report.run_id} published - "
               f"{publish_result['published']} files")
    datasets = "\n".join(f"  {name}: {count}"
                         for name, count in publish_result["by_dataset"].items())
    body = (f"Published {publish_result['published']} changed files:\n{datasets}\n\n"
            f"{report.summary()}\n\n"
            f"Undo:    python -m pipelines rollback {report.run_id}\n"
            f"Report:  {report_url(state_bucket, report.run_id)}")
    return subject, body


def news_message(report, uploaded, state_bucket) -> tuple[str, str]:
    subject = (f"[Fintank] News {report.run_id} - {report.verdict.upper()}, "
               f"{uploaded} files updated")
    skipped = next((c["detail"] for c in report.checks
                    if c["name"] == "news.search_topics"), None)
    note = f"Search topics: {skipped}\n\n" if skipped else ""
    return subject, (f"{note}{report.summary()}\n\n"
                     f"Report: {report_url(state_bucket, report.run_id)}")


def crash_message(job, run_id, error_text) -> tuple[str, str]:
    return (f"[Fintank] {job} {run_id} crashed",
            f"The {job} command for {run_id} crashed. Nothing was published by "
            f"this step.\n\n{redact(error_text)}")


def _fmt_list(items, empty="none") -> str:
    return ", ".join(items) if items else empty


def earnings_message(report, summary: dict, state_bucket) -> tuple[str, str]:
    published, failed = summary.get("published", []), summary.get("failed", [])
    subject = (f"[Fintank] Earnings {report.run_id} - {len(published)} published, "
               f"{len(failed)} failed")
    lines = []
    if summary.get("message"):
        lines += [f"Nothing was done: {summary['message']}.", ""]
    if summary.get("no_key"):
        lines += ["Spend guard: no Claude key, nothing was generated "
                  "(ANTHROPIC_API_KEY is unset).", ""]
    elif summary.get("no_claude"):
        lines += ["Test mode (--no-claude): nothing was sent to Claude.", ""]
    if summary.get("unrecorded_submits"):
        lines += ["WARNING: a submit may have happened without a recorded batch id; check "
                  "the Anthropic console. These notes are skipped (never resubmitted) until "
                  "the entry with batch_id null is removed from earnings/state.json "
                  "pending_batches: " + ", ".join(summary["unrecorded_submits"]), ""]
    if summary.get("staged_not_live"):
        lines += ["Backfill notes are staged, not live: approve or discard the run.", ""]
    lines.append(f"Published: {len(published)}")
    lines += [f"  {p['symbol']} {p['quarter']} ({p.get('lean', '?')})" for p in published]
    lines.append(f"Failed: {len(failed)}")
    for f in failed:
        lines.append(f"  {f['symbol']} {f['quarter']}: {'; '.join(f['reasons'])}")
    lines += [f"Still waiting for a transcript: {_fmt_list(summary.get('waiting', []))}",
              f"Dropped after 7 days: {_fmt_list(summary.get('dropped', []))}",
              f"Batches still running: {_fmt_list(summary.get('pending_batches', []))}"]
    usage = summary.get("usage") or {}
    if "estimated_input_tokens" in usage:
        lines.append(f"Requests written: {summary.get('requests', 0)}, about "
                     f"{usage['estimated_input_tokens']:,} input tokens "
                     f"(estimated input cost ${summary.get('cost_usd', 0):.2f})")
    else:
        lines.append(f"Tokens: {usage.get('input_tokens', 0):,} in, "
                     f"{usage.get('output_tokens', 0):,} out; estimated cost "
                     f"${summary.get('cost_usd', 0):.2f}")
    lines += ["", report.summary(), "",
              "Pull a note:  python -m pipelines pull-note <SYMBOL> <FY>-Q<n>",
              f"Report: {report_url(state_bucket, report.run_id)}"]
    return subject, "\n".join(lines)


BACKFILL_FAILED_LISTED = 25   # the rest are in runs/<id>/failed/


def backfill_held_message(report, summary: dict, verdict: dict, state_bucket,
                          results_run_id=None) -> tuple[str, str]:
    """Backfill notes are staged, not live: approve or discard (like held_message).

    `results_run_id` is the run whose saved results these notes came from (the
    run itself, or the one `--from-results` named); re-checking it is free."""
    run_id = report.run_id
    source = results_run_id or run_id
    failed = summary.get("failed", [])
    usage = summary.get("usage") or {}
    subject = (f"[Fintank] Earnings backfill {run_id} held - {verdict['verdict'].upper()}, "
               f"{verdict['passed']} staged, {verdict['failed']} failed")
    lines = ["Held for your approval: the backfill notes are staged, not live.", "",
             f"Staged (passed the checks): {verdict['passed']}",
             f"Failed: {verdict['failed']}"]
    for f in failed[:BACKFILL_FAILED_LISTED]:
        lines.append(f"  {f['symbol']} {f['quarter']}: {'; '.join(f['reasons'])}")
    if len(failed) > BACKFILL_FAILED_LISTED:
        lines.append(f"  ... and {len(failed) - BACKFILL_FAILED_LISTED} more "
                     f"(runs/{run_id}/failed/)")
    rechecked = bool(results_run_id) and results_run_id != run_id
    paid = f" (paid once, by {results_run_id}; nothing new was spent)" if rechecked else ""
    lines += ["", f"Tokens: {usage.get('input_tokens', 0):,} in, "
                  f"{usage.get('output_tokens', 0):,} out; cost "
                  f"${summary.get('cost_usd', 0):.2f}{paid}", ""]
    if rechecked:
        # Staged by hand: no state machine holds an approval token for this run.
        lines += [f"Re-checked from {results_run_id}'s saved results (no Claude call). "
                  "No state machine is waiting on this run, so:",
                  f"Publish:  python -m pipelines earnings-backfill publish --run-id {run_id}",
                  f"Discard:  python -m pipelines earnings-backfill discarded --run-id {run_id}"]
    else:
        lines += [f"Publish:  python -m pipelines approve {run_id}",
                  f"Discard:  python -m pipelines discard {run_id}",
                  "Unanswered runs are discarded automatically after 7 days."]
    lines += ["Re-check the saved results later, free (no Claude call):",
              f"  python -m pipelines earnings-backfill stage --run-id <new-id> "
              f"--from-results {source}",
              "", report.summary(), "",
              f"Report: {report_url(state_bucket, run_id)}"]
    return subject, "\n".join(lines)


def backfill_refused_message(earlier) -> str:
    """Why a paid backfill submit is refused while saved results exist."""
    return (f"earlier backfill results are saved ({', '.join(earlier)}); re-check them "
            "for free with `python -m pipelines earnings-backfill stage --run-id <new-id> "
            f"--from-results {earlier[-1]}`, or pass --force to pay for a new batch")
