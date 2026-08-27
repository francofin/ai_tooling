"""Pure indicator arithmetic. No Django, no S3, no Redis -- hand-built frames
and numbers checkable on paper, following the backtester/tests/ convention."""
from unittest import TestCase

import numpy as np
import pandas as pd

from analyzer.analyzer_utils import technical_indicators as ti


def frame(closes, highs=None, lows=None, volumes=None):
    """Minimal OHLCV frame. Defaults keep high/low a fixed band around close."""
    closes = [float(c) for c in closes]
    n = len(closes)
    return pd.DataFrame({
        'date': [d.strftime('%Y-%m-%d') for d in pd.bdate_range('2024-01-01', periods=n)],
        'open': closes,
        'high': [float(h) for h in (highs if highs is not None else [c + 1 for c in closes])],
        'low': [float(l) for l in (lows if lows is not None else [c - 1 for c in closes])],
        'close': closes,
        'volume': [float(v) for v in (volumes if volumes is not None else [1000.0] * n)],
    })


class RegistryTests(TestCase):

    def test_every_indicator_declares_the_fields_the_orchestrator_reads(self):
        for name, spec in ti.INDICATORS.items():
            with self.subTest(indicator=name):
                self.assertIn(spec.kind, ('overlay', 'oscillator'))
                self.assertIsInstance(spec.arity, int)
                self.assertTrue(callable(spec.fn))
                self.assertTrue(callable(spec.min_rows))
                self.assertTrue(spec.plots)

    def test_registry_covers_exactly_the_eleven_contract_names(self):
        self.assertEqual(set(ti.INDICATORS), {
            'sma', 'ema', 'wma', 'dema', 'tema', 'rsi',
            'adx', 'williams', 'stddev', 'macd', 'adl'})

    def test_every_function_returns_one_full_length_series_per_plot(self):
        df = frame(list(range(1, 61)))
        params = {'macd': (12, 26, 9), 'adl': ()}
        for name, spec in ti.INDICATORS.items():
            with self.subTest(indicator=name):
                result = spec.fn(df, *params.get(name, (5,)))
                self.assertEqual(set(result), set(spec.plots))
                for key, series in result.items():
                    self.assertEqual(len(series), len(df), f"{name}.{key}")

    def test_min_rows_matches_the_contract_table(self):
        self.assertEqual(ti.INDICATORS['sma'].min_rows((50,)), 50)
        self.assertEqual(ti.INDICATORS['rsi'].min_rows((14,)), 15)
        self.assertEqual(ti.INDICATORS['dema'].min_rows((20,)), 40)
        self.assertEqual(ti.INDICATORS['tema'].min_rows((20,)), 60)
        self.assertEqual(ti.INDICATORS['adx'].min_rows((14,)), 29)
        self.assertEqual(ti.INDICATORS['macd'].min_rows((12, 26, 9)), 35)
        self.assertEqual(ti.INDICATORS['adl'].min_rows(()), 1)


class WindowIndicatorTests(TestCase):

    def test_sma_matches_a_hand_computed_window(self):
        series = ti.sma(frame([1, 2, 3, 4, 5, 6]), 3)['series']
        self.assertTrue(np.isnan(series.iloc[0]))
        self.assertTrue(np.isnan(series.iloc[1]))
        self.assertAlmostEqual(series.iloc[2], 2.0)
        self.assertAlmostEqual(series.iloc[5], 5.0)

    def test_wma_weights_the_most_recent_bar_heaviest(self):
        # (1*1 + 2*2 + 3*3) / 6 == 2.3333...
        series = ti.wma(frame([1, 2, 3, 4]), 3)['series']
        self.assertAlmostEqual(series.iloc[2], 14 / 6)

    def test_stddev_uses_the_sample_denominator(self):
        series = ti.stddev(frame([1, 2, 3, 4, 5]), 3)['series']
        self.assertAlmostEqual(series.iloc[2], 1.0)

    def test_warm_up_is_exactly_n_minus_one_nulls(self):
        series = ti.sma(frame(list(range(60))), 50)['series']
        self.assertEqual(int(series.isna().sum()), 49)


class EmaTests(TestCase):

    def test_ema_uses_adjust_false_recursion_seeded_at_the_first_close(self):
        closes = [1, 2, 3, 4, 5]
        series = ti.ema(frame(closes), 5)['series']
        expected = pd.Series([float(c) for c in closes]).ewm(span=5, adjust=False).mean()
        self.assertAlmostEqual(series.iloc[0], 1.0)
        for i in range(len(closes)):
            self.assertAlmostEqual(series.iloc[i], expected.iloc[i])

    def test_ema_emits_numbers_from_row_zero_which_is_why_min_rows_exists(self):
        """ewm defaults to min_periods=0, so it never NaNs out for short
        history. The orchestrator's len(df) check is the only guard."""
        series = ti.ema(frame([10, 11]), 200)['series']
        self.assertFalse(series.isna().any())

    def test_dema_and_tema_are_the_standard_combinations(self):
        df = frame(list(range(1, 41)))
        close = df['close']
        e1 = close.ewm(span=10, adjust=False).mean()
        e2 = e1.ewm(span=10, adjust=False).mean()
        e3 = e2.ewm(span=10, adjust=False).mean()
        self.assertAlmostEqual(ti.dema(df, 10)['series'].iloc[-1], (2 * e1 - e2).iloc[-1])
        self.assertAlmostEqual(ti.tema(df, 10)['series'].iloc[-1],
                               (3 * e1 - 3 * e2 + e3).iloc[-1])

    def test_a_mid_series_nan_does_not_poison_the_rest_of_the_recursion(self):
        """Asserted empirically rather than reasoned from the recursion: ewm
        treats NaN as missing and carries the prior state forward -- the
        output at the NaN position equals the prior EMA, not NaN itself --
        then resumes the ordinary recursion on the next real close."""
        closes = [10.0, 11.0, float('nan'), 12.0, 13.0]
        series = ti.ema(frame(closes), 3)['series']
        self.assertAlmostEqual(series.iloc[2], series.iloc[1])
        self.assertFalse(np.isnan(series.iloc[4]))


class RsiTests(TestCase):

    def test_a_monotonic_rally_pins_rsi_at_one_hundred(self):
        series = ti.rsi(frame(list(range(1, 40))), 14)['series']
        self.assertAlmostEqual(series.iloc[-1], 100.0, places=6)

    def test_a_monotonic_selloff_pins_rsi_at_zero(self):
        series = ti.rsi(frame(list(range(40, 1, -1))), 14)['series']
        self.assertAlmostEqual(series.iloc[-1], 0.0, places=6)

    def test_a_perfectly_flat_market_reads_fifty_not_nan(self):
        """avg_gain == avg_loss == 0 makes RS a 0/0 NaN. Neutral is 50."""
        series = ti.rsi(frame([100.0] * 40), 14)['series']
        self.assertFalse(np.isnan(series.iloc[-1]))
        self.assertAlmostEqual(series.iloc[-1], 50.0)

    def test_wilder_smoothing_not_a_plain_rolling_mean(self):
        closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
                  45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00]
        series = ti.rsi(frame(closes), 14)['series']
        # Wilder's own worked example: the first defined reading is ~70.46.
        self.assertAlmostEqual(series.iloc[14], 70.46, places=1)


class AdxTests(TestCase):
    """The most-botched indicator on the page. Each stage gets its own case."""

    def test_true_range_takes_each_of_the_three_branches(self):
        df = frame(closes=[10, 12, 8], highs=[11, 20, 9], lows=[9, 11, 2])
        tr = ti._true_range(df)
        self.assertAlmostEqual(tr.iloc[0], 2.0)    # high - low
        self.assertAlmostEqual(tr.iloc[1], 10.0)   # |high - prev_close|
        self.assertAlmostEqual(tr.iloc[2], 10.0)   # |low  - prev_close|

    def test_directional_movement_zeroes_the_smaller_of_two_positive_moves(self):
        """The exclusivity rule. An outside bar has both moves positive; only
        the larger one counts, and the smaller is set to 0 -- not capped."""
        df = frame(closes=[10, 10], highs=[11, 15], lows=[9, 2])
        plus_dm, minus_dm = ti._directional_movement(df)
        # up_move = 4, down_move = 7 -> down wins outright
        self.assertAlmostEqual(plus_dm.iloc[1], 0.0)
        self.assertAlmostEqual(minus_dm.iloc[1], 7.0)

    def test_directional_movement_the_other_way_round(self):
        df = frame(closes=[10, 10], highs=[11, 20], lows=[9, 8])
        plus_dm, minus_dm = ti._directional_movement(df)
        # up_move = 9, down_move = 1 -> up wins outright
        self.assertAlmostEqual(plus_dm.iloc[1], 9.0)
        self.assertAlmostEqual(minus_dm.iloc[1], 0.0)

    def test_an_inside_bar_produces_no_directional_movement_at_all(self):
        df = frame(closes=[10, 10], highs=[20, 15], lows=[2, 8])
        plus_dm, minus_dm = ti._directional_movement(df)
        self.assertAlmostEqual(plus_dm.iloc[1], 0.0)
        self.assertAlmostEqual(minus_dm.iloc[1], 0.0)

    def test_a_non_directional_market_gives_zero_not_infinity(self):
        """+DI + -DI == 0 is a real 0/0. DX must be 0."""
        df = frame([100.0] * 40, highs=[101.0] * 40, lows=[99.0] * 40)
        series = ti.adx(df, 14)['series']
        self.assertTrue(np.isfinite(series.iloc[-1]))
        self.assertAlmostEqual(series.iloc[-1], 0.0)

    def test_a_clean_uptrend_produces_a_strong_adx_reading(self):
        closes = [100 + i for i in range(60)]
        series = ti.adx(frame(closes), 14)['series']
        self.assertGreater(series.iloc[-1], 40.0)
        self.assertLessEqual(series.iloc[-1], 100.0)

    def test_the_third_smoothing_pass_actually_runs(self):
        """ADX is a Wilder pass over DX, so it must lag DX, not equal it."""
        closes = [100 + i for i in range(60)]
        df = frame(closes)
        self.assertNotAlmostEqual(ti.adx(df, 14)['series'].iloc[20],
                                  ti._dx(df, 14).iloc[20], places=4)


class MacdTests(TestCase):

    def test_histogram_is_macd_minus_signal_at_every_index(self):
        df = frame(list(range(1, 121)))
        result = ti.macd(df, 12, 26, 9)
        diff = (result['macd'] - result['signal'] - result['hist']).abs()
        self.assertLess(float(diff.max()), 1e-9)

    def test_signal_is_an_ema_of_the_macd_line_itself(self):
        df = frame(list(range(1, 121)))
        result = ti.macd(df, 12, 26, 9)
        expected = result['macd'].ewm(span=9, adjust=False).mean()
        self.assertAlmostEqual(result['signal'].iloc[-1], expected.iloc[-1])


class ZeroDivisorTests(TestCase):

    def test_adl_survives_a_bar_where_high_equals_low(self):
        df = frame(closes=[10, 10, 10], highs=[11, 10, 12], lows=[9, 10, 8])
        series = ti.adl(df)['series']
        self.assertTrue(np.isfinite(series).all())

    def test_adl_is_a_cumulative_sum_so_deltas_are_what_matter(self):
        # close == high on every bar puts the money-flow multiplier at a
        # constant +1, so each bar's contribution is strictly positive and
        # the running sum must strictly increase.
        df = frame(closes=[10, 11, 12], highs=[10, 11, 12], lows=[8, 9, 10])
        series = ti.adl(df)['series']
        self.assertGreater(series.iloc[2], series.iloc[1])

    def test_williams_reads_minus_fifty_on_a_perfectly_flat_window(self):
        """highest_high == lowest_low is a 0/0. Midpoint of -100..0 is -50."""
        df = frame([100.0] * 20, highs=[100.0] * 20, lows=[100.0] * 20)
        series = ti.williams(df, 14)['series']
        self.assertTrue(np.isfinite(series.iloc[-1]))
        self.assertAlmostEqual(series.iloc[-1], -50.0)

    def test_williams_is_zero_at_the_top_of_its_range_and_minus_hundred_at_the_bottom(self):
        # frame()'s default +-1 band would keep every bar's own high/low a
        # fixed distance from its own close, so the window extreme could
        # never land exactly on the current close. Pin high (low) to close
        # so the rolling extreme is reachable exactly.
        rising_closes = list(range(1, 30))
        rising = frame(rising_closes, highs=rising_closes)
        self.assertAlmostEqual(ti.williams(rising, 14)['series'].iloc[-1], 0.0, places=6)
        falling_closes = list(range(30, 1, -1))
        falling = frame(falling_closes, lows=falling_closes)
        self.assertAlmostEqual(ti.williams(falling, 14)['series'].iloc[-1], -100.0, places=6)
