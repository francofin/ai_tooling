from datetime import date
from unittest import mock

import requests
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from analyzer.analyzer_utils import analyst_view as av

TODAY = date(2026, 11, 21)

LOCMEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'index-tools-tests',
    }
}


def _row(d, **kw):
    r = {"symbol": "X", "date": d}
    for k in ("revenue", "eps", "ebitda"):
        r[k + "Low"] = 1.0
        r[k + "Avg"] = 2.0
        r[k + "High"] = 3.0
    r.update(kw)
    return r


class PickUsListingTests(SimpleTestCase):
    def test_pick_us_listing_maps_cnr_to_cni(self):
        v = [
            {"symbol": "CNI", "exchange": "New York Stock Exchange"},
            {"symbol": "CNR.TO", "exchange": "Toronto Stock Exchange"},
        ]
        self.assertEqual(av.pick_us_listing("CNR.TO", v), {"symbol": "CNI", "exchange": "NYSE"})

    def test_pick_us_listing_nasdaq_prefix(self):
        v = [{"symbol": "SHOP", "exchange": "NASDAQ Global Select"}]
        self.assertEqual(av.pick_us_listing("SHOP.TO", v), {"symbol": "SHOP", "exchange": "Nasdaq"})

    def test_pick_us_listing_none_for_tsx_only(self):
        v = [{"symbol": "ABC.TO", "exchange": "Toronto Stock Exchange"}]
        self.assertIsNone(av.pick_us_listing("ABC.TO", v))

    def test_pick_us_listing_none_for_us_symbol(self):
        v = [{"symbol": "AAPL", "exchange": "NASDAQ"}]
        self.assertIsNone(av.pick_us_listing("AAPL", v))


class ShapeEstimatesTests(SimpleTestCase):
    def test_shape_estimates_takes_next_three_ascending(self):
        rows = [_row(d) for d in ("2029-10-31", "2028-10-31", "2027-10-31", "2026-10-31", "2025-10-31")]
        out = av.shape_estimates(rows, "annual", TODAY)
        self.assertEqual([o["date"] for o in out], ["2027-10-31", "2028-10-31", "2029-10-31"])
        self.assertEqual(out[0]["revenue"], {"low": 1.0, "avg": 2.0, "high": 3.0})

    def test_shape_estimates_quarter_takes_four(self):
        rows = [_row("2027-%02d-28" % m) for m in range(12, 0, -1)]
        out = av.shape_estimates(rows, "quarter", TODAY)
        self.assertEqual(len(out), 4)
        self.assertEqual(out[0]["date"], "2027-01-28")

    def test_shape_estimates_keeps_none(self):
        out = av.shape_estimates([_row("2027-10-31", ebitdaLow=None), ], "annual", TODAY)
        self.assertIsNone(out[0]["ebitda"]["low"])
        out = av.shape_estimates([{"date": "2027-10-31"}], "annual", TODAY)
        self.assertIsNone(out[0]["eps"]["avg"])


class ShapeEstimatesTodayTests(SimpleTestCase):
    def test_shape_estimates_includes_row_dated_today(self):
        out = av.shape_estimates([_row("2026-11-21"), _row("2020-01-01")], "annual", TODAY)
        self.assertEqual([r["date"] for r in out], ["2026-11-21"])


class ShapeRatingsTests(SimpleTestCase):
    def test_ratings(self):
        r = av.shape_ratings({"strongBuy": 1, "buy": 2, "hold": 3, "sell": 0, "strongSell": 0, "consensus": "Buy"})
        self.assertEqual(r["total"], 6)
        self.assertEqual(r["consensus"], "Buy")

    def test_ratings_none_and_zero(self):
        self.assertIsNone(av.shape_ratings(None))
        self.assertIsNone(av.shape_ratings({"strongBuy": 0, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0}))


class ShapeTargetTests(SimpleTestCase):
    CONS = {"targetConsensus": 178.25, "targetMedian": 180.0, "targetLow": 150.0, "targetHigh": 200.0}

    def test_target_hidden_when_fewer_than_three_last_year(self):
        self.assertIsNone(av.shape_target(self.CONS, {"lastYearCount": 1}, from_us=False, usdcad=None))

    def test_target_hidden_when_summary_missing(self):
        self.assertIsNone(av.shape_target(self.CONS, None, from_us=False, usdcad=None))

    def test_target_hidden_when_consensus_missing(self):
        self.assertIsNone(av.shape_target(None, {"lastYearCount": 9}, from_us=False, usdcad=None))

    def test_target_from_us_converts_to_cad(self):
        t = av.shape_target(self.CONS, {"lastYearCount": 5}, from_us=True, usdcad=1.434)
        self.assertEqual(t["currency"], "USD")
        self.assertAlmostEqual(t["cad"]["consensus"], 255.6, places=1)
        self.assertEqual(t["count_last_year"], 5)
        self.assertEqual(t["consensus"], 178.25)
        self.assertEqual(t["high"], 200.0)

    def test_target_from_us_without_fx_keeps_usd(self):
        t = av.shape_target(self.CONS, {"lastYearCount": 5}, from_us=True, usdcad=None)
        self.assertIsNotNone(t)
        self.assertIsNone(t["cad"])
        self.assertEqual(t["currency"], "USD")

    def test_target_hidden_when_last_year_count_null(self):
        self.assertIsNone(av.shape_target(self.CONS, {"lastYearCount": None},
                                          from_us=True, usdcad=1.4))

    def test_target_own_listing(self):
        t = av.shape_target(self.CONS, {"lastYearCount": 3}, from_us=False, usdcad=1.4)
        self.assertIsNone(t["currency"])
        self.assertIsNone(t["cad"])


class BuildPayloadTests(SimpleTestCase):
    def test_build_payload_raises_keyerror_when_nothing(self):
        with self.assertRaises(KeyError):
            av.build_payload("X", estimates_annual=[], ratings=None, target=None,
                             source=None, reporting_currency="USD")

    def test_build_payload_tsx_only_keeps_estimates(self):
        est = av.shape_estimates([_row("2027-10-31")], "annual", TODAY)
        p = av.build_payload("ABC.TO", estimates_annual=est, ratings=None, target=None,
                             source=None, reporting_currency="CAD")
        self.assertIsNone(p["source"])
        self.assertEqual(p["estimates"], {"annual": est})
        self.assertEqual(p["reporting_currency"], "CAD")
        self.assertEqual(p["symbol"], "ABC.TO")


P = "analyzer.analyzer_utils.analyst_view."
VARIANTS = [{"symbol": "RY", "exchange": "New York Stock Exchange"},
            {"symbol": "RY.TO", "exchange": "Toronto Stock Exchange"}]
CONS = {"targetConsensus": 100.0, "targetMedian": 99.0, "targetLow": 80.0, "targetHigh": 120.0}
RATING = {"strongBuy": 5, "buy": 3, "hold": 1, "sell": 0, "strongSell": 0, "consensus": "Buy"}


@override_settings(CACHES=LOCMEM_CACHE)
class CachedGetterTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        names = {
            "analyst_estimates": [_row("2027-10-31")],
            "grades_consensus": RATING,
            "price_target_consensus": CONS,
            "price_target_summary": {"lastYearCount": 6},
            "exchange_variants": VARIANTS,
            "reported_currency": "CAD",
            "fx_rate": 1.4,
        }
        self.m = {}
        for n, rv in names.items():
            patcher = mock.patch(P + n, return_value=rv)
            self.m[n] = patcher.start()
            self.addCleanup(patcher.stop)

    def test_second_call_served_from_cache(self):
        av.get_analyst_view("RY.TO")
        av.get_analyst_view("RY.TO")
        for n in ("analyst_estimates", "grades_consensus", "exchange_variants", "fx_rate"):
            self.assertEqual(self.m[n].call_count, 1, n)

    def test_symbol_is_normalized(self):
        a = av.get_analyst_view(" ry.to ")
        av.get_analyst_view("RY.TO")
        self.assertEqual(a["symbol"], "RY.TO")
        self.assertEqual(self.m["analyst_estimates"].call_count, 1)

    def test_interlisted_uses_us_symbol_for_grades_and_targets(self):
        p = av.get_analyst_view("RY.TO")
        self.m["grades_consensus"].assert_called_once_with("RY")
        self.m["price_target_consensus"].assert_called_once_with("RY")
        self.assertEqual(self.m["analyst_estimates"].call_args.args[0], "RY.TO")
        self.assertEqual(p["source"], {"symbol": "RY", "exchange": "NYSE"})
        self.assertEqual(p["target"]["cad"]["consensus"], 140.0)

    def test_non_to_symbol_skips_variants_but_checks_currency(self):
        av.get_analyst_view("AAPL")
        self.m["exchange_variants"].assert_not_called()
        self.m["reported_currency"].assert_called_once_with("AAPL")
        self.m["fx_rate"].assert_not_called()
        self.m["grades_consensus"].assert_called_once_with("AAPL")

    def test_listing_lookup_cached_30_days(self):
        with mock.patch(P + "cache", wraps=cache) as c:
            av.get_analyst_view("RY.TO")
        calls = {call.args[0]: call for call in c.set.call_args_list}
        key = "stock:analyst:listing:RY.TO:v1"
        self.assertEqual(calls[key].kwargs["timeout"], av.LISTING_TTL)
        self.assertEqual(cache.get(key), {"source": {"symbol": "RY", "exchange": "NYSE"},
                                          "reporting_currency": "CAD"})
        self.assertEqual(calls["stock:analyst:RY.TO:v1"].kwargs["timeout"], av.PAYLOAD_TTL)
        self.assertEqual(calls["fx:usdcad:v1"].kwargs["timeout"], av.FX_TTL)

    def test_fmp_error_raises_unavailable_and_caches_no_payload(self):
        self.m["grades_consensus"].side_effect = requests.ConnectionError("boom")
        with self.assertRaises(av.AnalystUnavailable):
            av.get_analyst_view("RY.TO")
        self.assertIsNone(cache.get("stock:analyst:RY.TO:v1"))
        self.assertIsNone(cache.get("stock:analyst:missing:RY.TO:v1"))
        # the listing is an independent 30-day result and stays cached (R7)
        self.assertIsNotNone(cache.get("stock:analyst:listing:RY.TO:v1"))

    def test_value_error_raises_unavailable(self):
        self.m["analyst_estimates"].side_effect = ValueError("bad json")
        with self.assertRaises(av.AnalystUnavailable):
            av.get_analyst_view("RY.TO")

    def test_fx_failure_still_returns_usd_target(self):
        for exc in (requests.ConnectionError("x"), ValueError("x"), TypeError("x")):
            cache.clear()
            self.m["fx_rate"].side_effect = exc
            p = av.get_analyst_view("RY.TO")
            self.assertEqual(p["target"]["currency"], "USD")
            self.assertIsNone(p["target"]["cad"])
            self.assertIsNone(cache.get("fx:usdcad:v1"))

    def test_no_coverage_raises_keyerror_and_caches_missing(self):
        self.m["analyst_estimates"].return_value = []
        self.m["grades_consensus"].return_value = None
        self.m["price_target_consensus"].return_value = None
        self.m["price_target_summary"].return_value = None
        with self.assertRaises(KeyError):
            av.get_analyst_view("ZZZ")
        n = self.m["analyst_estimates"].call_count
        with self.assertRaises(KeyError):
            av.get_analyst_view("ZZZ")
        self.assertEqual(self.m["analyst_estimates"].call_count, n)
        self.assertTrue(cache.get("stock:analyst:missing:ZZZ:v1"))

    def test_quarterly_fetched_separately(self):
        av.get_analyst_view("RY.TO")
        periods = [c.args[1] if len(c.args) > 1 else c.kwargs.get("period")
                   for c in self.m["analyst_estimates"].call_args_list]
        self.assertNotIn("quarter", periods)
        out = av.get_quarterly_estimates(" ry.to ")
        self.assertEqual(out["symbol"], "RY.TO")
        self.assertEqual(len(out["estimates"]["quarter"]), 1)
        self.m["exchange_variants"].assert_called_once()
        av.get_quarterly_estimates("RY.TO")
        self.assertEqual(self.m["analyst_estimates"].call_count, 2)

    def test_quarterly_empty_raises_keyerror(self):
        self.m["analyst_estimates"].return_value = []
        with self.assertRaises(KeyError):
            av.get_quarterly_estimates("RY.TO")


ROUTE = "/api/analyst-view/{}/"
QROUTE = "/api/analyst-view/{}/quarterly/"


class AnalystViewEndpointTests(SimpleTestCase):
    def test_view_200(self):
        payload = {"symbol": "RY.TO", "estimates": {"annual": []}}
        with mock.patch("analyzer.analyzer_utils.analyst_view.get_analyst_view",
                        return_value=payload) as m:
            r = self.client.get(ROUTE.format("RY.TO"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), payload)
        m.assert_called_once_with("RY.TO")

    def test_view_404_on_keyerror(self):
        with mock.patch("analyzer.analyzer_utils.analyst_view.get_analyst_view",
                        side_effect=KeyError("ZZZ")):
            r = self.client.get(ROUTE.format("ZZZ"))
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json(), {"detail": "No analyst data for 'ZZZ'"})

    def test_view_502_on_unavailable(self):
        boom = "https://financialmodelingprep.com/stable/grades-consensus?symbol=RY&apikey=SECRET123"
        with mock.patch("analyzer.analyzer_utils.analyst_view.get_analyst_view",
                        side_effect=av.AnalystUnavailable(boom)):
            r = self.client.get(ROUTE.format("RY"))
        self.assertEqual(r.status_code, 502)
        self.assertIn("detail", r.json())
        body = r.content.decode()
        self.assertNotIn("financialmodelingprep", body)
        self.assertNotIn("apikey", body)
        self.assertNotIn("SECRET123", body)

    def test_view_502_logs_cause_class_only(self):
        cause = requests.ConnectionError("https://x/stable/y?apikey=SECRET123")
        err = av.AnalystUnavailable("RY")
        err.__cause__ = cause
        with mock.patch("analyzer.analyzer_utils.analyst_view.get_analyst_view", side_effect=err):
            with self.assertLogs("analyzer.views", level="WARNING") as logs:
                self.client.get(ROUTE.format("RY"))
        out = "\n".join(logs.output)
        self.assertIn("analyst view upstream failed for RY: ConnectionError", out)
        self.assertNotIn("apikey", out)
        self.assertNotIn("SECRET123", out)

    def test_view_500_hides_unexpected_error(self):
        with mock.patch("analyzer.analyzer_utils.analyst_view.get_analyst_view",
                        side_effect=RuntimeError("apikey=SECRET123")):
            r = self.client.get(ROUTE.format("RY"))
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("SECRET123", r.content.decode())

    def test_quarterly_route_200(self):
        payload = {"symbol": "RY.TO", "estimates": {"quarter": []}}
        with mock.patch("analyzer.analyzer_utils.analyst_view.get_quarterly_estimates",
                        return_value=payload) as m:
            r = self.client.get(QROUTE.format("RY.TO"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), payload)
        m.assert_called_once_with("RY.TO")

    def test_quarterly_404_and_502(self):
        with mock.patch("analyzer.analyzer_utils.analyst_view.get_quarterly_estimates",
                        side_effect=KeyError("ZZZ")):
            r = self.client.get(QROUTE.format("ZZZ"))
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json(), {"detail": "No analyst data for 'ZZZ'"})
        with mock.patch("analyzer.analyzer_utils.analyst_view.get_quarterly_estimates",
                        side_effect=av.AnalystUnavailable("RY")):
            r = self.client.get(QROUTE.format("RY"))
        self.assertEqual(r.status_code, 502)
