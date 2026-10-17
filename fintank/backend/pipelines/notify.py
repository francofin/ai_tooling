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
