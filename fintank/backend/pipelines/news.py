"""The daily news job: 4 FMP news feeds and 24 SerpAPI news searches, one JSON
file each under news_json_articles/ in the live bucket. Django's news app reads
those exact keys (news/getNews.py), so names and article shapes are unchanged
from news_updater.ipynb.

A file is uploaded only when it passes its checks; a failing file keeps
yesterday's version live. Search results carry relative ages ("7h", "1d") that
Django anchors to the S3 write time, so files are uploaded right after fetch."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time

import requests

from pipelines import thresholds as t
from pipelines.checks import FAIL, PASS, WARN, CheckResult
from pipelines.notify import news_message
from pipelines.report import RunReport, now_iso
from pipelines.results import StageResult, redact
from pipelines.store import run_key

FMP_STABLE = "https://financialmodelingprep.com/stable"
SERPAPI_URL = "https://serpapi.com/search.json"
NEWS_PREFIX = "news_json_articles"
FMP_PAGES, FMP_PAGE_SIZE = 15, 20

FMP_FEEDS = {
    "fmp_articles": "fmp-articles",
    "stock_articles": "news/stock-latest",
    "crypto_articles": "news/crypto-latest",
    "forex_articles": "news/forex-latest",
}
SEARCH_TERMS = {
    "econ": "Economic news updates", "global_news": "News on Global Markets",
    "tech": "Technology news", "macro": "Macroeconomic news",
    "politics": "Political news", "energy": "Energy", "oil": "Oil",
    "mid_east": "Middle East", "south_america": "South America markets",
    "us_stock": "US stock market", "japan_stock": "Japan stock market",
    "china_stock": "China stock market", "canadian_stock": "Canadian stock market",
    "eu_markets": "EU markets", "africa_economy": "Africa economy",
    "basic_materials": "Basic Materials", "industrials": "Industrials",
    "utilities": "Utilities Sector", "pharmaceuticals": "Pharmaceuticals",
    "consumer_trends": "Consumer trends", "financials": "Financials",
    "real_estate": "Real Estate", "communications": "Communications Industry",
    "digital_assets": "Digital Assets",
}

# The 24 search topics cost one SerpAPI search each; the FMP feeds cost none.
# On a 250-search plan the topics run only on these days of the month (10 runs,
# 240 searches); the FMP feeds run daily. Widen this after a plan upgrade.
SEARCH_DAYS = (1, 4, 7, 10, 13, 16, 19, 22, 25, 28)


def search_due(day: dt.date) -> bool:
    return day.day in SEARCH_DAYS


def next_search_day(day: dt.date) -> dt.date:
    """The first search day after `day`."""
    later = [d for d in SEARCH_DAYS if d > day.day]
    if later:
        return day.replace(day=later[0])
    first_of_next = (day.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    return first_of_next.replace(day=SEARCH_DAYS[0])


# Each tuple lists alternative field names; an article needs one of each.
REQUIRED_FIELDS = {
    "fmp": (("title",), ("url", "link"), ("publishedDate", "date")),
    "search": (("title",), ("link",), ("date",)),
}
_RELATIVE_AGE = re.compile(r"^\s*(\d+)\s*(mo|min|sec|hr|s|m|h|d|w|y)", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "hr": 3600,
                 "d": 86400, "w": 604800, "mo": 2592000, "y": 31536000}


def file_name(name: str) -> str:
    return f"{name}_articles.json"


def http_get_json(url, params=None, timeout=30, retries=1):
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as e:
            if attempt == retries:
                if isinstance(e, requests.RequestException):
                    # requests puts the full URL — apikey included — in the message
                    raise RuntimeError(redact(str(e))) from None
                raise
            time.sleep(2)


def fetch_fmp_feed(path, api_key, get=http_get_json) -> list:
    articles = []
    for page in range(FMP_PAGES):
        batch = get(f"{FMP_STABLE}/{path}",
                    params={"page": page, "limit": FMP_PAGE_SIZE, "apikey": api_key})
        if not isinstance(batch, list):
            raise ValueError(f"unexpected FMP payload: {str(batch)[:200]}")
        if not batch:
            break
        articles.extend(batch)
    return articles


def fetch_search(term, api_key, get=http_get_json) -> list:
    data = get(SERPAPI_URL, params={
        "engine": "bing_news", "q": term, "api_key": api_key, "device": "desktop",
        "qft": 'interval="7"', "count": "20", "safeSearch": "strict"})
    if "error" in data:
        raise ValueError(data["error"])
    return data.get("organic_results", [])


def _age_days(article, source, now):
    raw = article.get("publishedDate") or article.get("date")
    if not isinstance(raw, str) or not raw.strip():
        return None
    if source == "fmp":
        try:
            published = dt.datetime.strptime(raw.strip()[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
        return (now.replace(tzinfo=None) - published).total_seconds() / 86400
    match = _RELATIVE_AGE.match(raw)
    if not match:
        return None
    return int(match.group(1)) * _UNIT_SECONDS[match.group(2).lower()] / 86400


def prepare(name, articles, source, now) -> tuple[list, CheckResult]:
    """Drop malformed and duplicate articles, then check what is left."""
    kept, seen, dropped = [], set(), 0
    for article in articles:
        if not isinstance(article, dict) or not all(
                any(article.get(f) for f in alternatives)
                for alternatives in REQUIRED_FIELDS[source]):
            dropped += 1
            continue
        url = article.get("url") or article.get("link")
        if url in seen:
            dropped += 1
            continue
        seen.add(url)
        kept.append(article)

    minimum, max_age = t.NEWS_MIN_ARTICLES[source], t.NEWS_MAX_AGE_DAYS[source]
    ages = [a for a in (_age_days(x, source, now) for x in kept) if a is not None]
    newest = min(ages) if ages else None
    detail = (f"{len(kept)} articles ({dropped} dropped), newest "
              + (f"{newest:.1f} days old" if newest is not None else "of unknown age"))
    if len(kept) < minimum:
        status, detail = FAIL, f"only {len(kept)} articles (need {minimum}); {detail}"
    elif newest is not None and newest > max_age:
        status, detail = FAIL, f"newest article older than {max_age} days; {detail}"
    else:
        status = PASS
    return kept, CheckResult(f"news.{name}", status, len(kept), minimum, detail)


def run_news(run_id, fmp_key, serp_key, out_dir, store, upload=None, notifier=None,
             notify_all=True, now=None, get=http_get_json, log=print,
             state_bucket=None, dry_run=False, search=None) -> RunReport:
    """search: True/False forces the SerpAPI topics on/off; None decides by
    SEARCH_DAYS. Skipped topics keep their last file and are not failures."""
    now = now or dt.datetime.now(dt.timezone.utc)
    report = RunReport(run_id, "news", "news", now_iso(), dry_run=dry_run)
    os.makedirs(out_dir, exist_ok=True)
    if search is None:
        search = search_due(now.date())

    jobs = [(name, "fmp", lambda path=path: fetch_fmp_feed(path, fmp_key, get))
            for name, path in FMP_FEEDS.items()]
    if search:
        jobs += [(name, "search", lambda term=term: fetch_search(term, serp_key, get))
                 for name, term in SEARCH_TERMS.items()]
    else:
        nxt = next_search_day(now.date())
        log(f"search topics skipped today (SerpAPI quota) — next on day {nxt.day}")

    results, uploaded = [], 0
    for name, source, fetch in jobs:
        started = time.time()
        try:
            kept, check = prepare(name, fetch(), source, now)
        except Exception as e:  # noqa: BLE001 — one bad feed must not stop the rest
            kept, check = [], CheckResult(f"news.{name}", FAIL, 0, None,
                                          f"fetch failed: {redact(str(e))}")
        stage = StageResult(f"news.{name}")
        stage.record(check.status == PASS, None if check.status == PASS else name)
        stage.detail["articles"] = len(kept)
        report.add_stage(stage, time.time() - started)
        results.append(check)
        if check.status != PASS:
            log(f"{name}: kept yesterday's file — {check.detail}")
            continue
        path = os.path.join(out_dir, file_name(name))
        with open(path, "w") as f:
            json.dump(kept, f)
        if not dry_run and upload is not None:
            upload(path, f"{NEWS_PREFIX}/{file_name(name)}")
            uploaded += 1

    failed = sum(r.status == FAIL for r in results)
    if failed / len(results) > t.NEWS_FAILED_SHARE_FAIL:
        overall = FAIL
    elif failed:
        overall = WARN
    else:
        overall = PASS
    results.append(CheckResult("news.overall", overall, failed, t.NEWS_FAILED_SHARE_FAIL,
                               f"{failed} of {len(jobs)} files failed checks and "
                               "were not uploaded"))
    if not search:
        results.append(CheckResult(
            "news.search_topics", PASS, 0, None,
            f"skipped today (SerpAPI quota) — next on day {nxt.day}; "
            "the topic pages keep their last files"))
    report.staged_files = uploaded
    report.add_checks(results)
    report.finish(verdict_override=overall)
    store.put_json(run_key(run_id, "report.json"), report.to_dict())
    if notifier is not None and (notify_all or overall != PASS):
        notifier.send(*news_message(report, uploaded, state_bucket))
    return report
