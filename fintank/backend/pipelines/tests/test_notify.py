from pipelines.checks import CheckResult
from pipelines.notify import (Notifier, complete_message, crash_message,
                              held_message, news_message)
from pipelines.report import RunReport


class FakeSns:
    def __init__(self):
        self.published = []

    def publish(self, **kwargs):
        self.published.append(kwargs)


def report(verdict="warn"):
    r = RunReport("lean-20261017-1000", "weekly", "lean", "2026-10-17T10:00:00+00:00")
    r.add_checks([CheckResult("freshness.tsx", verdict, 1, 1, "1 session behind")])
    r.finish()
    return r


def test_without_topic_prints(capsys):
    Notifier(topic_arn="").send("Subject", "Body")
    assert "Subject" in capsys.readouterr().out


def test_with_topic_publishes_and_truncates_subject():
    sns = FakeSns()
    Notifier(topic_arn="arn:topic", client=sns).send("x" * 150, "Body")
    assert sns.published == [{"TopicArn": "arn:topic", "Subject": "x" * 100,
                              "Message": "Body"}]


def test_held_message_has_commands_and_reason():
    subject, body = held_message(report("warn"), "state-bucket", always_hold=False)
    assert subject == "[Fintank] Weekly run lean-20261017-1000 held - WARN"
    assert "python -m pipelines approve lean-20261017-1000" in body
    assert "python -m pipelines discard lean-20261017-1000" in body
    assert "a check did not pass" in body
    _, body = held_message(report("pass"), "state-bucket", always_hold=True)
    assert "ALWAYS_HOLD" in body


def test_complete_message_lists_datasets_and_rollback():
    subject, body = complete_message(
        report("pass"), {"published": 12, "by_dataset": {"stock_prices": 10, "econ": 2}},
        "state-bucket")
    assert subject == "[Fintank] Weekly run lean-20261017-1000 published - 12 files"
    assert "stock_prices: 10" in body
    assert "python -m pipelines rollback lean-20261017-1000" in body


def test_subjects_are_ascii():
    for subject, _ in (held_message(report(), "b", False),
                       complete_message(report("pass"), {"published": 1, "by_dataset": {}}, "b"),
                       crash_message("run", "lean-1", "x")):
        assert subject.isascii(), subject


def test_news_and_crash_messages():
    r = RunReport("news-20261017-0930", "news", "news", "2026-10-17T09:30:00+00:00")
    r.finish(verdict_override="pass")
    subject, _ = news_message(r, 28, "state-bucket")
    assert subject == "[Fintank] News news-20261017-0930 - PASS, 28 files updated"
    subject, body = crash_message("run", "lean-1", "Traceback ... ?apikey=SECRET")
    assert subject == "[Fintank] run lean-1 crashed"
    assert "SECRET" not in body


def test_news_message_mentions_skipped_search_topics():
    r = RunReport("news-20261017-0930", "news", "news", "2026-10-17T09:30:00+00:00")
    r.add_checks([CheckResult("news.search_topics", "pass", 0, None,
                              "skipped today (SerpAPI quota) — next on day 19")])
    r.finish(verdict_override="pass")
    _, body = news_message(r, 4, "state-bucket")
    assert "skipped today (SerpAPI quota)" in body
