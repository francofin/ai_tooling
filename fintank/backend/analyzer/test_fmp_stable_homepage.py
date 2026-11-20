import gzip
import io
import json
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import TestCase, override_settings

from analyzer.analyzer_utils import CorePerformanceTools as cpt

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def fake_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


def decompress(blob):
    return json.loads(gzip.decompress(blob).decode("utf-8"))


@override_settings(CACHES=LOCMEM)
class HomepageStableTests(TestCase):
    def setUp(self):
        cache.clear()
        p = patch(
            "analyzer.analyzer_utils.CorePerformanceTools.is_market_open_now",
            return_value=True,
        )
        p.start()
        self.addCleanup(p.stop)

    def test_index_performance_is_one_batch_call_with_v3_field(self):
        rows = [{"symbol": "^GSPC", "changePercentage": 0.5}]
        with patch("utils.fmp_stable.requests.get", return_value=fake_response(rows)) as get:
            result = cpt.get_index_performance()
        self.assertEqual(get.call_count, 1)
        symbols = get.call_args.kwargs["params"]["symbols"]
        self.assertIn("^GSPTSE", symbols.split(","))
        self.assertIn("TX60.TS", symbols.split(","))
        self.assertFalse(any(c.isspace() for c in symbols))
        self.assertEqual(result["data"][0]["changesPercentage"], 0.5)

    def test_etf_and_crypto_symbol_lists_have_no_whitespace(self):
        for fn, expected in ((cpt.get_etf_performance, "EWC"), (cpt.get_crypto_performance, "BTCUSD")):
            with patch("utils.fmp_stable.requests.get", return_value=fake_response([])) as get:
                fn()
            symbols = get.call_args.kwargs["params"]["symbols"]
            self.assertNotIn(" ", symbols)
            self.assertNotIn("\n", symbols)
            self.assertIn(expected, symbols.split(","))

    def test_index_charts_cache_each_index_oldest_first(self):
        rows = [
            {"date": "2026-11-19", "close": 2.0},
            {"date": "2026-11-18", "close": 1.0},
        ]
        with patch("utils.fmp_stable.requests.get", return_value=fake_response(rows)) as get:
            self.assertEqual(cpt.get_index_charts(), "ok")
        self.assertEqual(get.call_count, 15)
        blob = decompress(cache.get("home:index_chart:sp500:v1"))
        self.assertEqual(blob["name"], "S&P 500")
        self.assertEqual([r["date"] for r in blob["data"]], ["2026-11-18", "2026-11-19"])
        self.assertIn("adjClose", blob["data"][0])

    def test_index_charts_empty_series_is_not_cached(self):
        rows = [{"date": "2026-11-18", "close": 1.0}]
        cache.set("home:index_chart:nik:v1", b"previous-good", timeout=60)

        def fake_get(url, params=None, timeout=None):
            return fake_response([] if params["symbol"] == "^N225" else rows)

        buf = io.StringIO()
        with patch("utils.fmp_stable.requests.get", side_effect=fake_get), redirect_stdout(buf):
            self.assertEqual(cpt.get_index_charts(), "ok")
        self.assertEqual(cache.get("home:index_chart:nik:v1"), b"previous-good")
        self.assertIsNotNone(cache.get("home:index_chart:sp500:v1"))
        self.assertIn("nik failed: empty", buf.getvalue())

    def test_index_charts_raise_when_nothing_cached(self):
        with patch("utils.fmp_stable.requests.get", return_value=fake_response([])), \
                redirect_stdout(io.StringIO()):
            with self.assertRaisesMessage(RuntimeError, "index_charts: no charts cached"):
                cpt.get_index_charts()

    def test_index_charts_skip_a_failing_symbol(self):
        rows = [{"date": "2026-11-18", "close": 1.0}]

        def fake_get(url, params=None, timeout=None):
            if params["symbol"] == "^N225":
                raise requests.HTTPError("403 for https://x/stable?apikey=SECRET")
            return fake_response(rows)

        buf = io.StringIO()
        with patch("utils.fmp_stable.requests.get", side_effect=fake_get), redirect_stdout(buf):
            result = cpt.get_index_charts()
        self.assertEqual(result, "ok")
        self.assertIsNone(cache.get("home:index_chart:nik:v1"))
        self.assertIsNotNone(cache.get("home:index_chart:sp500:v1"))
        self.assertIn("HTTPError", buf.getvalue())
        self.assertNotIn("http", buf.getvalue())
        self.assertNotIn("SECRET", buf.getvalue())


@override_settings(CACHES=LOCMEM)
class IndexChartViewColdCacheTests(TestCase):
    """A cold cache costs the visitor one FMP call for their chart, not 15."""

    ROWS = [
        {"date": "2026-11-19", "close": 2.0, "volume": 10},
        {"date": "2026-11-18", "close": 1.0, "volume": 5},
    ]

    def setUp(self):
        cache.clear()

    def test_cold_cache_fetches_only_the_requested_index(self):
        with patch("utils.fmp_stable.requests.get", return_value=fake_response(self.ROWS)) as get:
            response = self.client.get("/api/index-history/nik/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.kwargs["params"]["symbol"], "^N225")
        self.assertEqual(response.json()["data"]["prices"], [1.0, 2.0])
        self.assertIsNone(cache.get("home:index_chart:sp500:v1"))

    def test_unknown_index_makes_no_fmp_call(self):
        with patch("utils.fmp_stable.requests.get") as get:
            response = self.client.get("/api/index-history/not_an_index/")
        self.assertEqual(response.status_code, 404)
        get.assert_not_called()

    def test_failed_fetch_returns_404_without_caching(self):
        with patch("utils.fmp_stable.requests.get", side_effect=requests.ConnectionError("x")), \
                redirect_stdout(io.StringIO()):
            response = self.client.get("/api/index-history/nik/")
        self.assertEqual(response.status_code, 404)
        self.assertIsNone(cache.get("home:index_chart:nik:v1"))
