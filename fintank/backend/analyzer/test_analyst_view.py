from datetime import date

from django.test import SimpleTestCase

from analyzer.analyzer_utils import analyst_view as av

TODAY = date(2026, 11, 21)


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
