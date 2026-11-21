from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase

from utils.fmp_stable import (
    STABLE_BASE,
    adjusted_history,
    analyst_estimates,
    batch_quotes,
    exchange_variants,
    fx_rate,
    grades_consensus,
    index_history,
    price_target_consensus,
    price_target_summary,
    reported_currency,
    split_symbols,
)


def fake_response(payload, error=None):
    resp = MagicMock()
    resp.json.return_value = payload
    if error:
        resp.raise_for_status.side_effect = error
    return resp


class FmpStableTests(SimpleTestCase):
    def test_split_symbols_strips_whitespace_and_empties(self):
        self.assertEqual(split_symbols("A, B,\n   C,,"), ["A", "B", "C"])

    def test_batch_quotes_adds_v3_change_name(self):
        rows = [{"symbol": "^GSPC", "changePercentage": 0.5, "price": 1.0}]
        with patch("utils.fmp_stable.requests.get", return_value=fake_response(rows)):
            out = batch_quotes(["^GSPC"])
        self.assertEqual(out[0]["changesPercentage"], 0.5)
        self.assertEqual(out[0]["changePercentage"], 0.5)

    def test_batch_quotes_sends_symbols_and_key_as_params(self):
        with patch("utils.fmp_stable.requests.get", return_value=fake_response([])) as get:
            batch_quotes(["A", "B"])
        args, kwargs = get.call_args
        self.assertEqual(args[0], STABLE_BASE + "batch-quote")
        self.assertEqual(kwargs["params"]["symbols"], "A,B")
        self.assertIn("apikey", kwargs["params"])
        self.assertNotIn("apikey", args[0])

    def test_index_history_is_oldest_first_with_adjclose(self):
        rows = [
            {"date": "2026-11-19", "close": 2.0, "volume": 1},
            {"date": "2026-11-18", "close": 1.0, "volume": 1},
        ]
        with patch("utils.fmp_stable.requests.get", return_value=fake_response(rows)):
            out = index_history("^GSPC")
        self.assertEqual([r["date"] for r in out], ["2026-11-18", "2026-11-19"])
        for r in out:
            self.assertEqual(r["adjClose"], r["close"])

    def test_adjusted_history_is_oldest_first(self):
        rows = [
            {"date": "2026-11-19", "close": 2.0, "adjClose": 1.9},
            {"date": "2026-11-18", "close": 1.0, "adjClose": 0.9},
        ]
        with patch("utils.fmp_stable.requests.get", return_value=fake_response(rows)):
            out = adjusted_history("AAPL")
        self.assertEqual([r["date"] for r in out], ["2026-11-18", "2026-11-19"])
        self.assertEqual([r["adjClose"] for r in out], [0.9, 1.9])

    def test_adjusted_history_requests_deep_history(self):
        with patch("utils.fmp_stable.requests.get", return_value=fake_response([])) as get:
            adjusted_history("AAPL")
        self.assertEqual(get.call_args.kwargs["params"]["from"], "1990-01-01")

    def test_index_history_drops_rows_without_a_date(self):
        rows = [
            {"date": None, "close": 9.0},
            {"close": 8.0},
            {"date": "", "close": 7.0},
            {"date": "2026-11-18", "close": 1.0},
        ]
        with patch("utils.fmp_stable.requests.get", return_value=fake_response(rows)):
            out = index_history("^GSPC")
        self.assertEqual([r["date"] for r in out], ["2026-11-18"])

    def test_http_error_propagates(self):
        resp = fake_response([], error=requests.HTTPError("403"))
        with patch("utils.fmp_stable.requests.get", return_value=resp):
            with self.assertRaises(requests.HTTPError):
                batch_quotes(["A"])

    def test_non_list_body_raises_value_error(self):
        resp = fake_response({"Error Message": "x"})
        with patch("utils.fmp_stable.requests.get", return_value=resp):
            with self.assertRaises(ValueError):
                batch_quotes(["A"])

    def test_analyst_estimates_sends_period_and_limit(self):
        with patch("utils.fmp_stable.requests.get", return_value=fake_response([])) as get:
            analyst_estimates("ATD.TO", "quarter", limit=12)
        args, kwargs = get.call_args
        self.assertEqual(args[0], STABLE_BASE + "analyst-estimates")
        self.assertEqual(kwargs["params"]["symbol"], "ATD.TO")
        self.assertEqual(kwargs["params"]["period"], "quarter")
        self.assertEqual(kwargs["params"]["limit"], 12)

    def test_analyst_estimates_returns_rows(self):
        rows = [{"date": "2027-04-30", "epsAvg": 3.1}, {"date": "2026-04-30", "epsAvg": 2.9}]
        with patch("utils.fmp_stable.requests.get", return_value=fake_response(rows)):
            out = analyst_estimates("ATD.TO", "annual", limit=5)
        self.assertEqual(out, rows)

    def test_single_row_helpers_return_none_on_empty(self):
        with patch("utils.fmp_stable.requests.get", return_value=fake_response([])):
            self.assertIsNone(grades_consensus("ATD.TO"))
            self.assertIsNone(price_target_consensus("ATD.TO"))
            self.assertIsNone(price_target_summary("ATD.TO"))
            self.assertIsNone(reported_currency("ATD.TO"))
            self.assertIsNone(fx_rate())

    def test_price_target_summary_returns_first_row(self):
        rows = [{"symbol": "ATD.TO", "lastYear": 5}, {"symbol": "ATD.TO", "lastYear": 6}]
        with patch("utils.fmp_stable.requests.get", return_value=fake_response(rows)) as get:
            out = price_target_summary("ATD.TO")
        self.assertEqual(out, {"symbol": "ATD.TO", "lastYear": 5})
        self.assertEqual(get.call_args.args[0], STABLE_BASE + "price-target-summary")

    def test_grades_and_consensus_use_their_endpoints(self):
        with patch("utils.fmp_stable.requests.get", return_value=fake_response([{"strongBuy": 3}])) as get:
            self.assertEqual(grades_consensus("ATD.TO"), {"strongBuy": 3})
            self.assertEqual(get.call_args.args[0], STABLE_BASE + "grades-consensus")
            self.assertEqual(price_target_consensus("ATD.TO"), {"strongBuy": 3})
            self.assertEqual(get.call_args.args[0], STABLE_BASE + "price-target-consensus")

    def test_exchange_variants_returns_all_rows(self):
        rows = [{"symbol": "ATD.TO"}, {"symbol": "ATDRY"}]
        with patch("utils.fmp_stable.requests.get", return_value=fake_response(rows)) as get:
            out = exchange_variants("ATD.TO")
        self.assertEqual(out, rows)
        self.assertEqual(get.call_args.args[0], STABLE_BASE + "search-exchange-variants")
        self.assertEqual(get.call_args.kwargs["params"]["symbol"], "ATD.TO")

    def test_fx_rate_returns_float_price(self):
        body = [{"symbol": "USDCAD", "price": 1.434}]
        with patch("utils.fmp_stable.requests.get", return_value=fake_response(body)) as get:
            out = fx_rate()
        self.assertEqual(out, 1.434)
        self.assertIsInstance(out, float)
        self.assertEqual(get.call_args.args[0], STABLE_BASE + "quote")
        self.assertEqual(get.call_args.kwargs["params"]["symbol"], "USDCAD")

    def test_reported_currency_reads_income_statement(self):
        body = [{"symbol": "ATD.TO", "reportedCurrency": "USD"}]
        with patch("utils.fmp_stable.requests.get", return_value=fake_response(body)) as get:
            out = reported_currency("ATD.TO")
        self.assertEqual(out, "USD")
        args, kwargs = get.call_args
        self.assertTrue(args[0].endswith("income-statement"))
        self.assertEqual(kwargs["params"]["limit"], 1)
        self.assertEqual(kwargs["params"]["symbol"], "ATD.TO")

    def test_new_helpers_propagate_http_errors(self):
        resp = fake_response([], error=requests.HTTPError("403"))
        with patch("utils.fmp_stable.requests.get", return_value=resp):
            with self.assertRaises(requests.HTTPError):
                analyst_estimates("ATD.TO", "annual", limit=1)
            with self.assertRaises(requests.HTTPError):
                fx_rate()
