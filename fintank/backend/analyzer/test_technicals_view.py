"""Spec parsing, caching, trimming and view status codes.

The loader is mocked everywhere -- nothing here touches S3. The configured
cache points at Redis db 15, so these run against locmem and clear between
tests, exactly as analyzer/tests.py does.
"""
from unittest.mock import patch

import numpy as np
import pandas as pd
from django.core.cache import cache
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


def price_frame(n, start='2020-01-02', base=100.0, step=0.5):
    """Stand-in for a per-symbol daily parquet, before back-adjustment."""
    dates = pd.bdate_range(start, periods=n)
    closes = np.array([base + step * i for i in range(n)])
    return pd.DataFrame({
        'date': [d.strftime('%Y-%m-%d') for d in dates],
        'open': closes - 0.2,
        'high': closes + 1.0,
        'low': closes - 1.0,
        'close': closes,
        'adjClose': closes,               # no split unless a test says so
        'volume': np.full(n, 1_000_000.0),
    })


@override_settings(CACHES=LOCMEM_CACHE)
class LoaderHygieneTests(SimpleTestCase):

    def setUp(self):
        cache.clear()

    def _load(self, frame):
        with patch.object(technicals.data_getter, 'load_stock_prices',
                          return_value=frame):
            return technicals._load_adjusted_frame('AAPL')

    def test_column_projection_is_pushed_into_the_parquet_reader(self):
        with patch.object(technicals.data_getter, 'load_stock_prices',
                          return_value=price_frame(10)) as loader:
            technicals._load_adjusted_frame('AAPL')
        self.assertEqual(loader.call_args.kwargs['columns'], technicals.PRICE_COLUMNS)
        self.assertIn('adjClose', loader.call_args.kwargs['columns'])

    def test_out_of_order_rows_are_sorted(self):
        """Every rolling and ewm operation downstream is positional, not
        date-aware, so an unsorted row silently corrupts every indicator."""
        frame = price_frame(10).iloc[::-1].reset_index(drop=True)
        loaded = self._load(frame)
        self.assertEqual(loaded['date'].tolist(), sorted(loaded['date'].tolist()))

    def test_duplicate_dates_keep_the_last_row(self):
        frame = price_frame(5)
        duplicate = frame.iloc[[4]].copy()
        duplicate['close'] = 999.0
        duplicate['adjClose'] = 999.0
        loaded = self._load(pd.concat([frame, duplicate], ignore_index=True))
        self.assertEqual(len(loaded), 5)
        self.assertAlmostEqual(loaded['close'].iloc[-1], 999.0)

    def test_all_four_price_columns_are_back_adjusted_by_the_same_ratio(self):
        """An adjusted overlay drawn over raw candle bodies floats off the bars
        around a split, so open/high/low move with close."""
        frame = price_frame(10)
        frame.loc[:4, 'adjClose'] = frame.loc[:4, 'close'] / 2.0   # 2:1 split
        loaded = self._load(frame)
        for i in range(5):
            ratio = 0.5
            self.assertAlmostEqual(loaded['open'].iloc[i], frame['open'].iloc[i] * ratio)
            self.assertAlmostEqual(loaded['high'].iloc[i], frame['high'].iloc[i] * ratio)
            self.assertAlmostEqual(loaded['low'].iloc[i], frame['low'].iloc[i] * ratio)
            self.assertAlmostEqual(loaded['close'].iloc[i], frame['adjClose'].iloc[i])

    def test_volume_is_left_unadjusted(self):
        frame = price_frame(10)
        frame.loc[:4, 'adjClose'] = frame.loc[:4, 'close'] / 2.0
        loaded = self._load(frame)
        self.assertTrue((loaded['volume'] == 1_000_000.0).all())

    def test_a_split_leaves_no_discontinuity_in_a_recursive_indicator(self):
        from analyzer.analyzer_utils import technical_indicators as ti
        frame = price_frame(120)
        frame.loc[:59, 'adjClose'] = frame.loc[:59, 'close'] / 2.0
        loaded = self._load(frame)
        series = ti.ema(loaded, 12)['series']
        jumps = series.diff().abs().iloc[61:]
        self.assertLess(float(jumps.max()), 5.0)

    def test_every_flavour_of_missing_parquet_becomes_a_key_error(self):
        for error in (FileNotFoundError('gone'), OSError('s3'), KeyError('nope')):
            with self.subTest(error=type(error).__name__):
                with patch.object(technicals.data_getter, 'load_stock_prices',
                                  side_effect=error):
                    with self.assertRaises(KeyError):
                        technicals._load_adjusted_frame('XYZ')

    def test_an_empty_frame_is_a_key_error(self):
        with self.assertRaises(KeyError):
            self._load(pd.DataFrame())

    def test_an_all_nan_close_column_is_a_key_error(self):
        frame = price_frame(10)
        frame['close'] = np.nan
        frame['adjClose'] = np.nan
        with self.assertRaises(KeyError):
            self._load(frame)


@override_settings(CACHES=LOCMEM_CACHE)
class GetTechnicalsTests(SimpleTestCase):

    def setUp(self):
        cache.clear()

    def _run(self, frame, spec='rsi:14', symbol='AAPL'):
        with patch.object(technicals, '_load_adjusted_frame',
                          return_value=technicals._adjust(frame)):
            return technicals.get_technicals(symbol, spec)

    def _payload(self, n=400, spec='rsi:14'):
        return self._run(price_frame(n), spec)

    def test_the_payload_carries_every_key_the_frontend_reads(self):
        payload = self._payload()
        self.assertEqual(set(payload), {
            'symbol', 'dates', 'candle', 'volume', 'average_volume',
            'indicators', 'warnings'})
        self.assertEqual(payload['symbol'], 'AAPL')

    def test_candle_entries_are_x_and_a_four_element_ohlc_y(self):
        candle = self._payload()['candle'][0]
        self.assertEqual(set(candle), {'x', 'y'})
        self.assertEqual(len(candle['y']), 4)

    def test_every_series_is_the_same_length_as_dates(self):
        payload = self._payload(spec='sma:50,macd:12:26:9,adl')
        expected = len(payload['dates'])
        self.assertEqual(len(payload['candle']), expected)
        self.assertEqual(len(payload['volume']), expected)
        for token, entry in payload['indicators'].items():
            for key in ('series', 'macd', 'signal', 'hist'):
                if key in entry:
                    with self.subTest(token=token, plot=key):
                        self.assertEqual(len(entry[key]), expected)

    def test_the_window_is_the_trailing_two_hundred_and_fifty_rows(self):
        self.assertEqual(len(self._payload(n=600)['dates']), 250)

    def test_a_short_history_returns_everything_it_has_without_padding(self):
        payload = self._payload(n=120, spec='sma:50')
        self.assertEqual(len(payload['dates']), 120)

    def test_compute_then_trim_leaves_no_leading_nulls_on_a_long_window(self):
        """The regression that trimming before computing would introduce:
        sma:200 on a 250-row slice yields 199 nulls and 51 usable points."""
        payload = self._payload(n=600, spec='sma:200')
        series = payload['indicators']['sma:200']['series']
        self.assertEqual(len(series), 250)
        self.assertEqual(sum(1 for v in series if v is None), 0)

    def test_adl_deltas_survive_trimming_even_though_its_level_does_not(self):
        """A/D Line is a plain cumulative sum with no warm-up, so full-history
        computation does not fix a padding problem -- it shifts the absolute
        *level* by the constant sum of everything before the window. The shape,
        which is the only thing ADL is read for, is identical either way.

        This is why its chart must autoscale and must never anchor at zero.
        """
        from analyzer.analyzer_utils import technical_indicators as ti

        full = technicals._adjust(price_frame(600))
        payload = self._run(price_frame(600), spec='adl')
        trimmed_first = ti.adl(full.tail(250).reset_index(drop=True))['series'].tolist()
        returned = payload['indicators']['adl']['series']

        self.assertEqual(len(returned), 250)
        # Deltas match to floating-point noise ...
        for i in range(1, 250):
            self.assertAlmostEqual(returned[i] - returned[i - 1],
                                   trimmed_first[i] - trimmed_first[i - 1], places=6)
        # ... while the levels are offset by a constant.
        offsets = {round(returned[i] - trimmed_first[i], 6) for i in range(250)}
        self.assertEqual(len(offsets), 1)
        self.assertNotAlmostEqual(offsets.pop(), 0.0)

    def test_kind_comes_from_the_registry_not_from_the_frontend(self):
        payload = self._payload(spec='sma:50,rsi:14')
        self.assertEqual(payload['indicators']['sma:50']['kind'], 'overlay')
        self.assertEqual(payload['indicators']['rsi:14']['kind'], 'oscillator')

    def test_bands_travel_with_the_indicators_that_have_them(self):
        payload = self._payload(spec='rsi:14,sma:50')
        self.assertEqual(payload['indicators']['rsi:14']['bands'], [30, 70])
        self.assertNotIn('bands', payload['indicators']['sma:50'])

    def test_macd_carries_three_named_plots_not_one_series(self):
        entry = self._payload(spec='macd:12:26:9')['indicators']['macd:12:26:9']
        self.assertEqual(set(entry) - {'kind'}, {'macd', 'signal', 'hist'})

    def test_values_are_json_numbers_and_nulls_never_strings(self):
        series = self._payload(spec='sma:50')['indicators']['sma:50']['series']
        for value in series:
            self.assertTrue(value is None or isinstance(value, float))

    def test_average_volume_is_the_mean_of_the_returned_window(self):
        frame = price_frame(600)
        frame.loc[:349, 'volume'] = 9_999_999.0      # outside the trailing 250
        payload = self._run(frame, spec='sma:50')
        self.assertAlmostEqual(payload['average_volume'], 1_000_000.0)

    def test_a_missing_spec_returns_a_candle_only_payload(self):
        """A freshly added ticker must render its price chart before anything
        is toggled -- the hook does not gate its key on the spec."""
        with patch.object(technicals, '_load_adjusted_frame',
                          return_value=technicals._adjust(price_frame(300))):
            payload = technicals.get_technicals('AAPL', None)
        self.assertEqual(payload['indicators'], {})
        self.assertEqual(payload['warnings'], [])
        self.assertEqual(len(payload['candle']), 250)


@override_settings(CACHES=LOCMEM_CACHE)
class DegradationTests(SimpleTestCase):
    """Insufficient history degrades with a warning; it never 500s."""

    def setUp(self):
        cache.clear()

    def _run(self, n, spec):
        with patch.object(technicals, '_load_adjusted_frame',
                          return_value=technicals._adjust(price_frame(n))):
            return technicals.get_technicals('AAPL', spec)

    def test_a_window_indicator_longer_than_the_history_is_skipped(self):
        payload = self._run(14, 'sma:200')
        self.assertNotIn('sma:200', payload['indicators'])
        self.assertEqual(len(payload['warnings']), 1)
        self.assertIn('sma:200', payload['warnings'][0])

    def test_a_recursive_indicator_longer_than_the_history_is_also_skipped(self):
        """The real regression case. ewm returns confident numbers from two
        rows, so the sma version above passes even with no min-rows check."""
        payload = self._run(14, 'rsi:200')
        self.assertNotIn('rsi:200', payload['indicators'])
        self.assertIn('rsi:200', payload['warnings'][0])

    def test_dema_and_tema_need_two_and_three_times_their_period(self):
        payload = self._run(30, 'dema:20,tema:20')
        self.assertEqual(payload['indicators'], {})
        self.assertEqual(len(payload['warnings']), 2)

    def test_survivors_still_render_alongside_the_skipped_one(self):
        payload = self._run(60, 'sma:20,sma:200')
        self.assertIn('sma:20', payload['indicators'])
        self.assertNotIn('sma:200', payload['indicators'])

    def test_a_one_row_symbol_returns_two_hundred_with_warnings(self):
        payload = self._run(1, 'rsi:14,adl')
        self.assertEqual(len(payload['dates']), 1)
        self.assertIn('adl', payload['indicators'])
        self.assertIn('rsi:14', payload['warnings'][0])

    def test_an_all_nan_volume_column_skips_adl_and_leaves_the_rest(self):
        frame = price_frame(300)
        frame['volume'] = np.nan
        with patch.object(technicals, '_load_adjusted_frame',
                          return_value=technicals._adjust(frame)):
            payload = technicals.get_technicals('AAPL', 'adl,sma:50')
        self.assertNotIn('adl', payload['indicators'])
        self.assertIn('sma:50', payload['indicators'])
        self.assertTrue(any('adl' in w for w in payload['warnings']))


@override_settings(CACHES=LOCMEM_CACHE)
class CacheTests(SimpleTestCase):

    def setUp(self):
        cache.clear()

    def _loader(self, n=300):
        return patch.object(technicals, '_load_adjusted_frame',
                            return_value=technicals._adjust(price_frame(n)))

    def test_an_identical_second_call_does_not_touch_the_loader(self):
        with self._loader() as loader:
            technicals.get_technicals('AAPL', 'rsi:14')
            technicals.get_technicals('AAPL', 'rsi:14')
        self.assertEqual(loader.call_count, 1)

    def test_reordering_the_spec_still_hits_the_payload_cache(self):
        with self._loader() as loader:
            technicals.get_technicals('AAPL', 'rsi:14,sma:50')
            technicals.get_technicals('AAPL', 'sma:50,rsi:14')
        self.assertEqual(loader.call_count, 1)

    def test_changing_a_period_reuses_the_ohlcv_layer_but_not_the_payload(self):
        """The whole point of the two layers: a period change costs pandas,
        not another partial parquet read."""
        with self._loader() as loader:
            first = technicals.get_technicals('AAPL', 'rsi:14')
            second = technicals.get_technicals('AAPL', 'rsi:21')
        self.assertEqual(loader.call_count, 1)
        self.assertIn('rsi:21', second['indicators'])
        self.assertNotEqual(first['indicators']['rsi:14']['series'][-1],
                            second['indicators']['rsi:21']['series'][-1])

    def test_a_new_trading_day_invalidates_both_layers_and_changes_the_data(self):
        """Asserting call counts alone does not prove freshness -- a warm
        payload keyed without the date would keep serving yesterday's window
        even after the parquet was rewritten."""
        with patch.object(technicals, '_market_date', return_value='2026-08-25'), \
             self._loader(n=300):
            monday = technicals.get_technicals('AAPL', 'sma:50')

        with patch.object(technicals, '_market_date', return_value='2026-08-26'), \
             self._loader(n=301) as loader:
            tuesday = technicals.get_technicals('AAPL', 'sma:50')

        self.assertEqual(loader.call_count, 1)
        self.assertNotEqual(monday['dates'][-1], tuesday['dates'][-1])

    def test_a_poisoned_cache_entry_heals_on_read(self):
        """json.dumps writes Infinity and json.loads reads it straight back, so
        an entry written before json_safe existed stays poisoned for its full
        TTL. _load_cached_json re-normalises on the way out."""
        import gzip as _gzip
        import json as _json
        from rest_framework.renderers import JSONRenderer

        key = f"stock:technicals:AAPL:{technicals._market_date()}:poison:v1"
        cache.set(key, _gzip.compress(
            _json.dumps({'symbol': 'AAPL', 'average_volume': float('inf')}).encode()))
        with patch.object(technicals, 'canonical_key', return_value='poison'), \
             self._loader():
            payload = technicals.get_technicals('AAPL', 'sma:50')
        self.assertIsNone(payload['average_volume'])
        JSONRenderer().render(payload)

    def test_an_infinite_value_is_stored_as_null_not_as_infinity(self):
        import gzip as _gzip
        with self._loader():
            technicals.get_technicals('AAPL', 'sma:50')
        stored = cache.get(
            f"stock:ohlcv:AAPL:{technicals._market_date()}:v1")
        self.assertNotIn(b'Infinity', _gzip.decompress(stored))
        self.assertNotIn(b'NaN', _gzip.decompress(stored))
