"""Spec parsing, caching, trimming and view status codes.

The loader is mocked everywhere -- nothing here touches S3. The configured
cache points at Redis db 15, so these run against locmem and clear between
tests, exactly as analyzer/tests.py does.
"""
from unittest.mock import patch

import numpy as np
import pandas as pd
from django.test import SimpleTestCase, override_settings

from analyzer.analyzer_utils import technicals

LOCMEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'technicals-tests',
    }
}


class ParseSpecTests(SimpleTestCase):

    def test_a_full_spec_round_trips_to_names_and_integer_params(self):
        self.assertEqual(
            technicals.parse_spec('rsi:14,macd:12:26:9,adl'),
            [('rsi', (14,)), ('macd', (12, 26, 9)), ('adl', ())])

    def test_a_missing_parameter_is_an_empty_spec_not_an_error(self):
        """The candle-only path: a freshly added ticker with nothing toggled."""
        self.assertEqual(technicals.parse_spec(None), [])

    def test_names_are_case_insensitive_and_whitespace_is_tolerated(self):
        self.assertEqual(technicals.parse_spec(' RSI:14 , SMA:50 '),
                         [('rsi', (14,)), ('sma', (50,))])

    def test_an_unknown_name_names_itself_in_the_message(self):
        with self.assertRaisesRegex(ValueError, "unknown indicator 'foo'"):
            technicals.parse_spec('foo:14')

    def test_a_non_integer_period_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'rsi:abc'):
            technicals.parse_spec('rsi:abc')

    def test_periods_outside_the_bounds_are_rejected(self):
        with self.assertRaisesRegex(ValueError, '2..500'):
            technicals.parse_spec('sma:1')
        with self.assertRaisesRegex(ValueError, '2..500'):
            technicals.parse_spec('sma:501')

    def test_wrong_arity_names_the_token_and_the_expectation(self):
        with self.assertRaisesRegex(ValueError, 'macd:12'):
            technicals.parse_spec('macd:12')
        with self.assertRaisesRegex(ValueError, 'adl:14'):
            technicals.parse_spec('adl:14')

    def test_macd_requires_a_fast_period_below_the_slow_one(self):
        with self.assertRaisesRegex(ValueError, 'fast'):
            technicals.parse_spec('macd:26:12:9')
        with self.assertRaisesRegex(ValueError, 'fast'):
            technicals.parse_spec('macd:12:12:9')

    def test_an_empty_but_present_parameter_lists_the_valid_names(self):
        with self.assertRaisesRegex(ValueError, 'rsi'):
            technicals.parse_spec('')

    def test_duplicates_collapse_before_the_cap_is_applied(self):
        self.assertEqual(technicals.parse_spec('sma:50,sma:50'), [('sma', (50,))])
        # 13 tokens, one of them repeated -> 12 distinct, which is allowed.
        spec = ','.join([f'sma:{n}' for n in range(10, 22)] + ['sma:10'])
        self.assertEqual(len(technicals.parse_spec(spec)), 12)

    def test_more_than_twelve_distinct_indicators_is_rejected(self):
        spec = ','.join(f'sma:{n}' for n in range(10, 23))
        with self.assertRaisesRegex(ValueError, 'at most 12'):
            technicals.parse_spec(spec)

    def test_two_instances_of_one_indicator_are_two_entries(self):
        """SMA(50) against SMA(200) is the point of the dual-period control."""
        self.assertEqual(technicals.parse_spec('sma:50,sma:200'),
                         [('sma', (50,)), ('sma', (200,))])


class CanonicalKeyTests(SimpleTestCase):

    def test_order_does_not_change_the_hash(self):
        a = technicals.canonical_key(technicals.parse_spec('rsi:14,sma:50'))
        b = technicals.canonical_key(technicals.parse_spec('sma:50,rsi:14'))
        self.assertEqual(a, b)

    def test_different_parameters_change_the_hash(self):
        a = technicals.canonical_key(technicals.parse_spec('rsi:14'))
        b = technicals.canonical_key(technicals.parse_spec('rsi:21'))
        self.assertNotEqual(a, b)

    def test_the_hash_is_sixteen_hex_characters(self):
        key = technicals.canonical_key(technicals.parse_spec('rsi:14'))
        self.assertEqual(len(key), 16)
        int(key, 16)

    def test_token_for_omits_the_colon_when_there_are_no_parameters(self):
        self.assertEqual(technicals.token_for('adl', ()), 'adl')
        self.assertEqual(technicals.token_for('macd', (12, 26, 9)), 'macd:12:26:9')
