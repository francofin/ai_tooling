from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase

from utils.fmp_stable import (
    STABLE_BASE,
    adjusted_history,
    batch_quotes,
    index_history,
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
