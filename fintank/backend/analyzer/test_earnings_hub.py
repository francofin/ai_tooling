import io
import json
from datetime import date, timedelta
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from analyzer import views
from analyzer.analyzer_utils import earnings_hub as eh

TODAY = date(2026, 11, 21)   # the Toronto date every test runs on

LOCMEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'earnings-hub-tests',
    }
}

CAL = "/api/earnings-calendar/"
NOTES = "/api/earnings-notes/{}/"
NOTE = "/api/earnings-notes/{}/{}/"

TSX = [{"asset": "RY.TO", "name": "Royal Bank of Canada"}, {"asset": "DUAL.TO", "name": "Dual Canada"}]
SP = [{"asset": "AAPL", "name": "Apple Inc."}, {"asset": "DUAL.TO", "name": "Dual US"}]


def _fmp(symbol, d="2026-11-19"):
    return {"symbol": symbol, "date": d, "epsActual": 1.5, "epsEstimated": 1.4,
            "revenueActual": 100, "revenueEstimated": 90}


class FakeS3:
    """Stands in for data_getter: constituents plus a dict of s3 key -> JSON object."""

    def __init__(self, objects=None, tsx=TSX, sp=SP):
        self.objects = objects or {}
        self.consts = {"tsx": tsx, "sp500": sp}
        self.opened = []
        self.fs = mock.Mock()
        self.fs.open.side_effect = self._open

    def get_index_constituents(self, index):
        return self.consts[index]

    def _open(self, path):
        self.opened.append(path)
        key = path.removeprefix("s3://thetradingfloor/")
        if key not in self.objects:
            raise FileNotFoundError(path)
        return io.BytesIO(json.dumps(self.objects[key]).encode())


def _entry(q, withdrawn=False):
    fy, fq = q.split("-Q")
    return {"quarter": q, "fiscal_year": int(fy), "fiscal_quarter": int(fq),
            "report_date": "2026-11-19", "lean": "neutral", "headline": "h",
            "key_points": ["k"], "withdrawn": withdrawn}


def _note(q):
    fy, fq = q.split("-Q")
    return {"symbol": "RY.TO", "fiscal_year": int(fy), "fiscal_quarter": int(fq),
            "headline": "h", "key_points": ["k"], "sections": []}


@override_settings(CACHES=LOCMEM_CACHE)
class EarningsHubBase(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.addCleanup(cache.clear)
        today = mock.patch.object(views, "_toronto_today", return_value=TODAY)
        today.start()
        self.addCleanup(today.stop)

    def patch(self, s3, rows=None, side_effect=None):
        p1 = mock.patch.object(eh, "data_getter", s3)
        p2 = mock.patch("analyzer.analyzer_utils.earnings_hub.earnings_calendar",
                        return_value=rows or [], side_effect=side_effect)
        p1.start()
        self.fmp = p2.start()
        self.addCleanup(mock.patch.stopall)


class CalendarTests(EarningsHubBase):
    def test_calendar_keeps_only_covered_symbols_and_labels_region(self):
        self.patch(FakeS3(), [_fmp("RY.TO"), _fmp("AAPL"), _fmp("GMG.V")])
        r = self.client.get(CAL, {"week": "2026-11-16"})
        self.assertEqual(r.status_code, 200)
        rows = r.json()["rows"]
        self.assertEqual([(x["symbol"], x["region"]) for x in rows], [("AAPL", "us"), ("RY.TO", "ca")])
        ry = rows[1]
        self.assertEqual(ry["name"], "Royal Bank of Canada")
        self.assertEqual(ry["eps_estimate"], 1.4)
        self.assertEqual(ry["eps_actual"], 1.5)
        self.assertEqual(ry["revenue_estimate"], 90)
        self.assertEqual(ry["revenue_actual"], 100)

    def test_calendar_week_param_normalises_to_monday(self):
        self.patch(FakeS3())
        r = self.client.get(CAL, {"week": "2026-11-19"})
        self.assertEqual(r.json()["week_start"], "2026-11-16")
        (start, end), _ = self.fmp.call_args
        self.assertEqual((start.isoformat(), end.isoformat()), ("2026-11-16", "2026-11-20"))

    def test_calendar_bad_week_is_400(self):
        self.patch(FakeS3())
        self.assertEqual(self.client.get(CAL, {"week": "nope"}).status_code, 400)
        self.assertEqual(self.client.get(CAL, {"week": "2026-13-40"}).status_code, 400)
        self.fmp.assert_not_called()

    def test_calendar_week_more_than_a_year_away_is_400(self):
        self.patch(FakeS3())
        for week in ("0001-01-01", "9999-12-31", (TODAY - timedelta(days=366)).isoformat(),
                     (TODAY + timedelta(days=366)).isoformat()):
            self.assertEqual(self.client.get(CAL, {"week": week}).status_code, 400, week)
        self.fmp.assert_not_called()

    def test_calendar_week_within_a_year_is_200(self):
        self.patch(FakeS3())
        for week in ((TODAY - timedelta(days=364)).isoformat(),
                     (TODAY + timedelta(days=364)).isoformat()):
            self.assertEqual(self.client.get(CAL, {"week": week}).status_code, 200, week)

    def test_calendar_default_week_is_the_toronto_today(self):
        self.patch(FakeS3())
        self.assertEqual(self.client.get(CAL).json()["week_start"], "2026-11-16")

    def test_calendar_drops_weekends_and_sorts_by_date_then_symbol(self):
        self.patch(FakeS3(), [_fmp("RY.TO", "2026-11-19"), _fmp("AAPL", "2026-11-21"),
                              _fmp("AAPL", "2026-11-18"), _fmp("DUAL.TO", "2026-11-19")])
        rows = self.client.get(CAL, {"week": "2026-11-16"}).json()["rows"]
        self.assertEqual([(x["date"], x["symbol"]) for x in rows],
                         [("2026-11-18", "AAPL"), ("2026-11-19", "DUAL.TO"), ("2026-11-19", "RY.TO")])

    def test_calendar_adds_note_quarter_from_latest(self):
        s3 = FakeS3({"earnings_notes/latest.json": {"RY.TO": "2026-Q3"}})
        self.patch(s3, [_fmp("RY.TO"), _fmp("AAPL")])
        rows = {x["symbol"]: x for x in self.client.get(CAL, {"week": "2026-11-16"}).json()["rows"]}
        self.assertEqual(rows["RY.TO"]["note_quarter"], "2026-Q3")
        self.assertIsNone(rows["AAPL"]["note_quarter"])

    def test_calendar_cached_6h(self):
        self.patch(FakeS3(), [_fmp("RY.TO")])
        with mock.patch.object(cache, "set", wraps=cache.set) as spy:
            self.client.get(CAL, {"week": "2026-11-16"})
        keys = {c.args[0]: c.kwargs.get("timeout", c.args[2] if len(c.args) > 2 else None)
                for c in spy.call_args_list}
        self.assertEqual(keys["home:earnings:calendar:2026-11-16:v1"], 21600)
        self.client.get(CAL, {"week": "2026-11-18"})
        self.assertEqual(self.fmp.call_count, 1)

    def test_symbol_in_both_lists_is_ca(self):
        covered = FakeS3()
        self.patch(covered)
        out = eh.get_covered_symbols()
        self.assertEqual(out["DUAL.TO"], {"region": "ca", "name": "Dual Canada"})
        self.assertEqual(out["AAPL"]["region"], "us")


class NotesTests(EarningsHubBase):
    def test_notes_404_when_none(self):
        self.patch(FakeS3())
        self.assertEqual(self.client.get(NOTES.format("RY.TO")).status_code, 404)

    def test_notes_404_when_all_withdrawn(self):
        s3 = FakeS3({"earnings_notes/RY.TO/index.json": {"quarters": [_entry("2026-Q3", True)]}})
        self.patch(s3)
        self.assertEqual(self.client.get(NOTES.format("RY.TO")).status_code, 404)

    def test_notes_skip_withdrawn_latest(self):
        s3 = FakeS3({
            "earnings_notes/RY.TO/index.json": {"quarters": [_entry("2026-Q3", True), _entry("2026-Q2")]},
            "earnings_notes/RY.TO/2026-Q2.json": _note("2026-Q2"),
            "earnings_notes/RY.TO/2026-Q3.json": _note("2026-Q3"),
        })
        self.patch(s3)
        body = self.client.get(NOTES.format("RY.TO")).json()
        self.assertEqual(body["latest"]["fiscal_quarter"], 2)
        self.assertEqual([q["quarter"] for q in body["quarters"]], ["2026-Q2"])

    def test_note_404_for_withdrawn_missing_and_malformed_quarter(self):
        s3 = FakeS3({
            "earnings_notes/RY.TO/index.json": {"quarters": [_entry("2026-Q3", True)]},
            "earnings_notes/RY.TO/2026-Q3.json": _note("2026-Q3"),
        })
        self.patch(s3)
        for q in ("2026-Q3", "2026-Q1"):
            self.assertEqual(self.client.get(NOTE.format("RY.TO", q)).status_code, 404, q)
        self.assertEqual(self.client.get(NOTE.format("RY.TO", "2026-Q9")).status_code, 404)
        with self.assertRaises(KeyError):
            eh.get_note("RY.TO", "../x")
        self.assertEqual(s3.opened, ["s3://thetradingfloor/earnings_notes/RY.TO/index.json",
                                     "s3://thetradingfloor/earnings_notes/RY.TO/index.json"])

    def test_note_symbol_with_dash_and_dot(self):
        s3 = FakeS3({
            "earnings_notes/BBD-B.TO/index.json": {"quarters": [_entry("2026-Q3")]},
            "earnings_notes/BBD-B.TO/2026-Q3.json": _note("2026-Q3"),
        })
        self.patch(s3)
        r = self.client.get(NOTE.format("bbd-b.to", "2026-Q3"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("s3://thetradingfloor/earnings_notes/BBD-B.TO/2026-Q3.json", s3.opened)

    def test_note_cached(self):
        s3 = FakeS3({
            "earnings_notes/RY.TO/index.json": {"quarters": [_entry("2026-Q3")]},
            "earnings_notes/RY.TO/2026-Q3.json": _note("2026-Q3"),
        })
        self.patch(s3)
        self.client.get(NOTE.format("RY.TO", "2026-Q3"))
        n = len(s3.opened)
        self.client.get(NOTE.format("RY.TO", "2026-Q3"))
        self.assertEqual(len(s3.opened), n)


class FailureTests(EarningsHubBase):
    def test_fmp_failure_is_502(self):
        import requests
        self.patch(FakeS3(), side_effect=requests.ConnectionError("apikey=SECRET123"))
        r = self.client.get(CAL, {"week": "2026-11-16"})
        self.assertEqual(r.status_code, 502)
        self.assertNotIn("SECRET123", r.content.decode())

    def test_s3_failure_is_502(self):
        s3 = FakeS3()
        s3.fs.open.side_effect = OSError("boom")
        self.patch(s3)
        self.assertEqual(self.client.get(NOTES.format("RY.TO")).status_code, 502)

    def test_unexpected_error_is_500(self):
        self.patch(FakeS3(), side_effect=RuntimeError("apikey=SECRET123"))
        r = self.client.get(CAL, {"week": "2026-11-16"})
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("SECRET123", r.content.decode())


class FmpHelperTests(SimpleTestCase):
    def test_earnings_calendar_requests_from_to(self):
        from datetime import date
        from utils import fmp_stable
        with mock.patch.object(fmp_stable, "_get_list", return_value=[]) as m:
            fmp_stable.earnings_calendar(date(2026, 11, 16), date(2026, 11, 20))
        m.assert_called_once_with("earnings-calendar", {"from": "2026-11-16", "to": "2026-11-20"}, 20)
