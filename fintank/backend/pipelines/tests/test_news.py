import datetime as dt
import json

import pytest

from pipelines import news
from pipelines.store import LocalStore, run_key

NOW = dt.datetime(2026, 10, 16, 9, 30, tzinfo=dt.timezone.utc)   # a search day
FRESH = (NOW - dt.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")


def fmp_page(path, page, n=20, date=FRESH):
    return [{"title": f"{path} {page}-{i}", "url": f"https://x/{path}/{page}/{i}",
             "publishedDate": date} for i in range(n)]


def search_results(term, n=5, age="2h"):
    return {"organic_results": [{"title": f"{term} {i}", "link": f"https://y/{term}/{i}",
                                 "date": age} for i in range(n)]}


def make_get(broken=(), pages=3):
    def get(url, params=None):
        params = params or {}
        if url == news.SERPAPI_URL:
            if params["q"] in broken:
                raise ValueError(f"boom for {url}?api_key=SECRET")
            return search_results(params["q"])
        path = url.removeprefix(news.FMP_STABLE + "/")
        if path in broken:
            raise ValueError(f"500 for url {url}?apikey=SECRET")
        return fmp_page(path, params["page"]) if params["page"] < pages else []
    return get


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, subject, message):
        self.sent.append(subject)


def run(tmp_path, get, **kwargs):
    uploads = []
    store = LocalStore(str(tmp_path / "store"))
    report = news.run_news("news-1", "fmp", "serp", str(tmp_path / "out"), store,
                           upload=lambda path, key: uploads.append(key),
                           now=NOW, get=get, log=lambda *a: None, **kwargs)
    return report, uploads, store


def test_catalogue_matches_django_reader():
    assert len(news.FMP_FEEDS) == 4 and len(news.SEARCH_TERMS) == 24
    assert news.file_name("fmp_articles") == "fmp_articles_articles.json"


def test_everything_passes_and_uploads(tmp_path):
    report, uploads, store = run(tmp_path, make_get())
    assert report.verdict == "pass"
    assert len(uploads) == 28
    assert "news_json_articles/econ_articles.json" in uploads
    assert "news_json_articles/stock_articles_articles.json" in uploads
    saved = store.get_json(run_key("news-1", "report.json"))
    assert saved["verdict"] == "pass"
    with open(tmp_path / "out" / "fmp_articles_articles.json") as f:
        assert len(json.load(f)) == 60


def test_one_broken_feed_is_kept_and_warns(tmp_path):
    report, uploads, _ = run(tmp_path, make_get(broken={"news/crypto-latest"}))
    assert report.verdict == "warn"
    assert "news_json_articles/crypto_articles_articles.json" not in uploads
    assert len(uploads) == 27
    failed = next(c for c in report.checks if c["name"] == "news.crypto_articles")
    assert failed["status"] == "fail" and "SECRET" not in failed["detail"]


def test_majority_broken_fails(tmp_path):
    report, uploads, _ = run(tmp_path, make_get(broken=set(news.SEARCH_TERMS.values())))
    assert report.verdict == "fail"
    assert len(uploads) == 4


def test_dry_run_uploads_nothing(tmp_path):
    _, uploads, _ = run(tmp_path, make_get(), dry_run=True)
    assert uploads == []


@pytest.mark.parametrize("notify_all,verdict_broken,emails", [
    (True, set(), 1), (False, set(), 0), (False, {"news/crypto-latest"}, 1)])
def test_notify_modes(tmp_path, notify_all, verdict_broken, emails):
    notifier = FakeNotifier()
    run(tmp_path, make_get(broken=verdict_broken), notifier=notifier, notify_all=notify_all)
    assert len(notifier.sent) == emails


def test_prepare_drops_bad_and_duplicate_articles():
    articles = fmp_page("f", 0, n=60) + [fmp_page("f", 0, n=1)[0], {"title": "no url"}, "junk"]
    kept, check = news.prepare("f", articles, "fmp", NOW)
    assert len(kept) == 60
    assert check.status == "pass" and "3 dropped" in check.detail


def test_prepare_fails_stale_and_thin_files():
    stale = fmp_page("f", 0, n=60, date="2026-10-01 00:00:00")
    assert news.prepare("f", stale, "fmp", NOW)[1].status == "fail"
    thin = search_results("t", n=2)["organic_results"]
    assert news.prepare("t", thin, "search", NOW)[1].status == "fail"
    old = search_results("t", n=5, age="3w")["organic_results"]
    assert news.prepare("t", old, "search", NOW)[1].status == "fail"
    unknown = search_results("t", n=5, age="Oct 3")["organic_results"]
    assert news.prepare("t", unknown, "search", NOW)[1].status == "pass"


def test_http_get_json_never_leaks_the_api_key(monkeypatch, capsys):
    import requests

    class Failing:
        def raise_for_status(self):
            raise requests.HTTPError("403 Client Error for url: https://f/x?apikey=SECRET")

    monkeypatch.setattr(news.requests, "get", lambda *a, **kw: Failing())
    monkeypatch.setattr(news.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError) as info:
        news.http_get_json("https://f/x", params={"apikey": "SECRET"})
    assert "SECRET" not in str(info.value)
    assert info.value.__cause__ is None and info.value.__suppress_context__
    assert "SECRET" not in capsys.readouterr().out


def test_search_days_fit_the_serpapi_quota():
    assert news.SEARCH_DAYS == (1, 4, 7, 10, 13, 16, 19, 22, 25, 28)
    assert len(news.SEARCH_DAYS) * len(news.SEARCH_TERMS) <= 250
    assert news.search_due(dt.date(2026, 10, 16)) is True
    assert news.search_due(dt.date(2026, 10, 17)) is False


def test_off_day_runs_only_the_fmp_feeds(tmp_path):
    off_day = dt.datetime(2026, 10, 17, 9, 30, tzinfo=dt.timezone.utc)
    calls = []

    def counting_get(url, params=None):
        calls.append(url)
        return make_get()(url, params)

    uploads, store = [], LocalStore(str(tmp_path / "store"))
    report = news.run_news("news-1", "fmp", "serp", str(tmp_path / "out"), store,
                           upload=lambda path, key: uploads.append(key),
                           now=off_day, get=counting_get, log=lambda *a: None)
    assert report.verdict == "pass"
    assert len(uploads) == 4
    assert news.SERPAPI_URL not in calls
    skipped = next(c for c in report.checks if c["name"] == "news.search_topics")
    assert skipped["status"] == "pass"
    assert "next on day 19" in skipped["detail"]
    overall = next(c for c in report.checks if c["name"] == "news.overall")
    assert "0 of 4 files" in overall["detail"]


def test_search_override_forces_or_skips_topics(tmp_path):
    off_day = dt.datetime(2026, 10, 17, 9, 30, tzinfo=dt.timezone.utc)
    on_day = dt.datetime(2026, 10, 16, 9, 30, tzinfo=dt.timezone.utc)
    for now, search, expected in ((off_day, True, 28), (on_day, False, 4)):
        uploads = []
        news.run_news("news-1", "fmp", "serp", str(tmp_path / "out"),
                      LocalStore(str(tmp_path / "store")),
                      upload=lambda path, key: uploads.append(key), now=now,
                      get=make_get(), log=lambda *a: None, search=search)
        assert len(uploads) == expected


def test_last_search_day_of_the_month_points_to_next_month():
    assert news.next_search_day(dt.date(2026, 10, 29)) == dt.date(2026, 11, 1)
    assert news.next_search_day(dt.date(2026, 10, 28)) == dt.date(2026, 11, 1)
    assert news.next_search_day(dt.date(2026, 10, 2)) == dt.date(2026, 10, 4)
