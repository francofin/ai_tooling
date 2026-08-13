"""The simulation loop.

Every case here builds a PricePanel by hand, so nothing touches S3, FMP or
Redis and the expected numbers are computable on paper.
"""
from unittest import TestCase

import numpy as np
import pandas as pd

from backtester.engine.backtest import (
    drawdown_series,
    run_backtest,
    schedule_dates,
)
from backtester.engine.config import NoEligibleAssets, validate_request
from backtester.engine.prices import PricePanel


def _panel(prices: dict, dates) -> PricePanel:
    """Build a PricePanel directly. NaN means 'no price on that date'."""
    dates = pd.DatetimeIndex(dates)
    frame = pd.DataFrame(prices, index=dates, dtype=float)
    first = {c: frame[c].first_valid_index() for c in frame.columns}
    last = {c: frame[c].last_valid_index() for c in frame.columns}
    for column in frame.columns:
        span = (frame.index >= first[column]) & (frame.index <= last[column])
        frame.loc[span, column] = frame.loc[span, column].ffill()
    return PricePanel(prices=frame, first_valid=first, last_valid=last,
                      provenance={c: 'test' for c in frame.columns})


def _request(**overrides):
    payload = {'holdings': [{'symbol': 'A'}, {'symbol': 'B'}],
               'rebalance_frequency': 'none', 'min_history_days': 1}
    payload.update(overrides)
    return validate_request(payload)


class GoldenNumbersTests(TestCase):
    """A 2-asset panel with hand-computed expected values (§15)."""

    def setUp(self):
        # A: +10%, +10%, 0.   B: -10%, -10%, 0.
        self.dates = pd.to_datetime(['2021-01-04', '2021-01-05',
                                     '2021-01-06', '2021-01-07'])
        self.panel = _panel({'A': [100.0, 110.0, 121.0, 121.0],
                             'B': [100.0, 90.0, 81.0, 81.0]}, self.dates)

    def test_index_tracks_the_drifted_equal_weight_portfolio(self):
        result = run_backtest(self.panel, _request())

        # day0: seed at 0.5/0.5, index 1.0
        # day1: R = .5(.1) + .5(-.1) = 0        -> index 1.0,   drift .55/.45
        # day2: R = .55(.1) + .45(-.1) = .01    -> index 1.01
        # day3: R = 0                           -> index 1.01
        np.testing.assert_allclose(result.index, [1.0, 1.0, 1.01, 1.01], rtol=1e-12)

    def test_nav_is_the_index_scaled_by_the_initial_amount(self):
        result = run_backtest(self.panel, _request(initial_amount=10_000))

        np.testing.assert_allclose(result.nav, [10_000, 10_000, 10_100, 10_100],
                                   rtol=1e-12)

    def test_returns_are_reported_per_date_with_a_leading_zero(self):
        result = run_backtest(self.panel, _request())

        # atol, not rtol: day 1's return is 0.5(0.1) + 0.5(-0.1), which lands on
        # 5.55e-17 rather than exactly zero, and a relative tolerance against
        # zero is infinite by definition.
        np.testing.assert_allclose(result.returns, [0.0, 0.0, 0.01, 0.0], atol=1e-15)

    def test_dates_are_iso_strings_covering_the_effective_window(self):
        result = run_backtest(self.panel, _request())

        self.assertEqual(result.dates,
                         ['2021-01-04', '2021-01-05', '2021-01-06', '2021-01-07'])
        self.assertEqual(result.effective_start, '2021-01-04')
        self.assertEqual(result.effective_end, '2021-01-07')

    def test_weights_over_time_sums_to_one_on_every_date(self):
        result = run_backtest(self.panel, _request())

        np.testing.assert_allclose(result.weights_over_time.sum(axis=1),
                                   np.ones(4), atol=1e-12)

    def test_cagr_inputs_are_consistent_with_the_index(self):
        result = run_backtest(self.panel, _request())

        self.assertAlmostEqual(float(result.index[-1]),
                               float(np.prod(1 + np.asarray(result.returns))),
                               places=12)


class DrawdownTests(TestCase):

    def test_drawdown_is_zero_at_a_new_high_and_negative_below_it(self):
        values = np.array([1.0, 1.2, 0.9, 1.3])

        np.testing.assert_allclose(drawdown_series(values),
                                   [0.0, 0.0, 0.9 / 1.2 - 1, 0.0], rtol=1e-12)

    def test_drawdown_never_exceeds_zero(self):
        values = np.cumprod(1 + np.linspace(-0.02, 0.02, 50))

        self.assertLessEqual(drawdown_series(values).max(), 0.0 + 1e-15)


class TurnoverAndCostTests(TestCase):
    """Hand-computed arithmetic across a known rebalance (§15)."""

    def setUp(self):
        # One step across a year boundary, so day1 is a scheduled annual rebalance.
        self.dates = pd.to_datetime(['2020-12-31', '2021-01-04'])
        self.panel = _panel({'A': [100.0, 150.0], 'B': [100.0, 100.0]}, self.dates)

    def test_turnover_is_the_l1_distance_from_drift_to_target(self):
        result = run_backtest(self.panel, _request(rebalance_frequency='annual',
                                                  transaction_cost_bps=10.0))

        # R = .5(.5) + .5(0) = .25 -> drift .6/.4; target back to .5/.5
        # turnover = |.5-.6| + |.5-.4| = 0.2
        self.assertEqual(len(result.rebalance_events), 1)
        event = result.rebalance_events[0]
        self.assertEqual(event['date'], '2021-01-04')
        self.assertAlmostEqual(event['turnover'], 0.2, places=12)
        self.assertAlmostEqual(event['cost'], 0.2 * 10 / 10_000, places=15)
        self.assertEqual(event['trigger'], 'scheduled')

    def test_the_cost_is_charged_against_both_index_and_nav(self):
        result = run_backtest(self.panel, _request(rebalance_frequency='annual',
                                                  transaction_cost_bps=10.0,
                                                  initial_amount=10_000))

        self.assertAlmostEqual(float(result.index[-1]), 1.25 * (1 - 0.0002), places=12)
        self.assertAlmostEqual(float(result.nav[-1]), 10_000 * 1.25 * (1 - 0.0002),
                               places=8)

    def test_zero_cost_bps_leaves_the_index_untouched(self):
        result = run_backtest(self.panel, _request(rebalance_frequency='annual',
                                                  transaction_cost_bps=0.0))

        self.assertAlmostEqual(float(result.index[-1]), 1.25, places=12)

    def test_weights_return_to_target_after_the_rebalance(self):
        result = run_backtest(self.panel, _request(rebalance_frequency='annual'))

        np.testing.assert_allclose(result.weights_over_time.iloc[-1].to_numpy(),
                                   [0.5, 0.5], atol=1e-12)


class ScheduleTests(TestCase):

    def setUp(self):
        self.index = pd.bdate_range('2020-01-01', '2022-12-31')

    def test_none_schedules_nothing(self):
        self.assertEqual(schedule_dates(self.index, 'none'), set())

    def test_annual_fires_on_the_first_trading_day_of_each_new_year(self):
        dates = sorted(schedule_dates(self.index, 'annual'))

        # Whatever the first business day of each new year is on this pandas
        # version, there must be exactly one per year boundary crossed.
        self.assertEqual(len(dates), 2)
        self.assertEqual([d.year for d in dates], [2021, 2022])
        self.assertEqual([d.month for d in dates], [1, 1])

    def test_monthly_fires_once_a_month_and_never_on_the_first_date(self):
        dates = sorted(schedule_dates(self.index, 'monthly'))

        self.assertEqual(len(dates), 35)
        self.assertNotIn(self.index[0], dates)

    def test_quarterly_and_semiannual_fire_four_and_two_times_a_year(self):
        self.assertEqual(len(schedule_dates(self.index, 'quarterly')), 11)
        self.assertEqual(len(schedule_dates(self.index, 'semiannual')), 5)


class LookAheadRegressionTests(TestCase):
    """REQUIRED (§15). These must fail loudly if the loop is ever reordered.

    Verified to fail against a deliberately reordered loop -- see the plan's
    Task 7 Step 8. A guardrail nobody has watched fail is decoration.
    """

    def setUp(self):
        self.dates = pd.bdate_range('2021-01-01', periods=40)

    def test_the_optimizer_never_sees_data_at_or_after_the_rebalance_date(self):
        """The window handed to a scheme ends at t - 1 - gap_days."""
        from unittest.mock import patch

        from backtester.engine import backtest as backtest_module

        panel = _panel({'A': np.linspace(100, 140, 40),
                        'B': np.linspace(100, 120, 40)}, self.dates)
        request = _request(weighting_scheme='min_variance', min_history_days=5,
                           lookback_days=5, gap_days=1,
                           rebalance_frequency='monthly',
                           backtest_mode='walk_forward')

        real_optimize = backtest_module.optimize
        seen = []

        def spy(window, config, scheme):
            seen.append(window.shape[0])
            return real_optimize(window, config, scheme)

        with patch.object(backtest_module, 'optimize', side_effect=spy):
            run_backtest(panel, request)

        self.assertTrue(seen)
        self.assertTrue(all(0 < rows <= 5 for rows in seen), seen)

    def test_a_strategy_that_would_profit_from_same_day_alignment_earns_nothing(self):
        """Asset B's future is knowable: it jumps +50% on one known date.

        The stub strategy sits in A and switches to 100% B at the rebalance that
        lands exactly on the spike date. That switch is the only thing under test.

        Under the correct w_{t-1}' r_t alignment the +50% is realized against the
        *old* all-A weights, so the portfolio earns nothing and the new position
        only takes effect the next day, when B is flat again. A loop that
        multiplied w_t by r_t would bank the whole +50%.

        The switch has to happen at the spike, not before it: a stub that holds B
        from the start captures the jump legitimately - it was simply long B -
        and the test would prove nothing. That was the first version of this
        test, and it failed against a correct loop for exactly that reason.
        """
        from unittest.mock import patch

        from backtester.engine import backtest as backtest_module
        from backtester.engine.optimizers import OptimizerOutcome

        prices_a = np.full(40, 100.0)
        prices_b = np.full(40, 100.0)
        prices_b[20:] = 150.0            # +50% on date index 20, flat after
        panel = _panel({'A': prices_a, 'B': prices_b}, self.dates)
        # Seed lands at index 4 (min_history_days=5), then these two rebalances.
        rebalances = {self.dates[10], self.dates[20]}

        request = _request(weighting_scheme='min_variance', min_history_days=5,
                           lookback_days=5, gap_days=1,
                           rebalance_frequency='monthly',
                           backtest_mode='walk_forward',
                           transaction_cost_bps=0.0)

        calls = {'n': 0}

        def switches_into_b_at_the_spike(window, config, scheme):
            calls['n'] += 1
            # Calls 1 and 2 are the seed and the index-10 rebalance; call 3 is
            # the rebalance on the spike date itself.
            weights = np.array([0.0, 1.0]) if calls['n'] >= 3 else np.array([1.0, 0.0])
            return OptimizerOutcome(weights=weights)

        with patch.object(backtest_module, 'optimize',
                          side_effect=switches_into_b_at_the_spike), \
             patch.object(backtest_module, 'schedule_dates',
                          side_effect=lambda index, frequency: (
                              set(rebalances) if frequency == 'monthly' else set())):
            result = run_backtest(panel, request)

        self.assertEqual(calls['n'], 3, 'stub was not called at both rebalances')
        # Held 100% A through the spike, so the honest answer is exactly 1.0.
        self.assertAlmostEqual(float(result.index[-1]), 1.0, places=9)
        self.assertNotAlmostEqual(float(result.index[-1]), 1.5, places=3)

    def test_the_return_on_a_rebalance_date_uses_yesterdays_weights(self):
        """Exact arithmetic check of R_t = w_{t-1}' r_t at a rebalance."""
        dates = pd.to_datetime(['2020-12-30', '2020-12-31', '2021-01-04'])
        # On 2021-01-04 (the annual rebalance) A returns 0 and B returns +20%.
        panel = _panel({'A': [100.0, 100.0, 100.0],
                        'B': [100.0, 100.0, 120.0]}, dates)

        result = run_backtest(panel, _request(rebalance_frequency='annual',
                                             transaction_cost_bps=0.0))

        # Weights entering 2021-01-04 are still 0.5/0.5, so R = 0.5 x 0.20 = 0.10.
        # A loop that rebalanced first and then applied the new weights would
        # produce a different number.
        self.assertAlmostEqual(float(result.returns[-1]), 0.10, places=12)
        self.assertAlmostEqual(float(result.index[-1]), 1.10, places=12)
