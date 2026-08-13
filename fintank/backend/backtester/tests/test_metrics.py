"""Performance metrics. Pure -- hand-computed expectations throughout."""
from unittest import TestCase

import numpy as np
import pandas as pd

from backtester.engine.metrics import (
    beta_alpha,
    calendar_year_returns,
    capture_ratios,
    compute_metrics,
    contribution_to_return,
    contribution_to_risk,
    correlation_matrix,
    drawdown_detail,
    money_weighted_return,
)


class DrawdownDetailTests(TestCase):

    def test_peak_trough_and_recovery_dates_are_identified(self):
        dates = ['2020-01-01', '2020-01-02', '2020-01-03', '2020-01-04', '2020-01-05']
        values = [1.0, 1.25, 1.0, 1.1, 1.3]

        detail = drawdown_detail(values, dates)

        self.assertAlmostEqual(detail['max_drawdown'], 1.0 / 1.25 - 1, places=12)
        self.assertEqual(detail['peak_date'], '2020-01-02')
        self.assertEqual(detail['trough_date'], '2020-01-03')
        self.assertEqual(detail['recovery_date'], '2020-01-05')

    def test_an_unrecovered_drawdown_reports_no_recovery_date(self):
        detail = drawdown_detail([1.0, 1.5, 0.9], ['a', 'b', 'c'])

        self.assertIsNone(detail['recovery_date'])

    def test_a_monotonically_rising_series_has_no_drawdown(self):
        detail = drawdown_detail([1.0, 1.1, 1.2], ['a', 'b', 'c'])

        self.assertAlmostEqual(detail['max_drawdown'], 0.0, places=15)
        self.assertIsNone(detail['peak_date'])


class MoneyWeightedReturnTests(TestCase):
    """§15 -- must match a known XIRR case.

    Day count is actual/365, which is Excel's XIRR convention. That makes the
    spans below leap-year sensitive: 2020-01-01 to 2021-01-01 is 366 days and so
    1.00274 years, and a $10,000 -> $11,000 flow over it returns 9.971%, not a
    round 10%. These cases use 2021-2023 spans, where the arithmetic is exact.
    """

    def test_a_single_year_ten_percent_gain(self):
        flows = [('2021-01-01', -10_000.0), ('2022-01-01', 11_000.0)]

        self.assertAlmostEqual(money_weighted_return(flows), 0.10, places=6)

    def test_a_leap_year_span_is_slightly_longer_than_a_year(self):
        """Documents the convention rather than working around it."""
        flows = [('2020-01-01', -10_000.0), ('2021-01-01', 11_000.0)]

        # 366/365 years, so (1+r)^1.00274 = 1.1
        expected = 1.1 ** (365 / 366) - 1
        self.assertAlmostEqual(money_weighted_return(flows), expected, places=6)

    def test_a_two_year_doubling_is_about_forty_one_percent_annualized(self):
        flows = [('2021-01-01', -10_000.0), ('2023-01-01', 20_000.0)]

        self.assertAlmostEqual(money_weighted_return(flows), 2 ** 0.5 - 1, places=6)

    def test_an_intermediate_deposit_is_time_weighted_by_its_own_date(self):
        flows = [('2021-01-01', -10_000.0),
                 ('2021-07-01', -5_000.0),
                 ('2022-01-01', 16_000.0)]

        rate = money_weighted_return(flows)
        self.assertGreater(rate, 0.0)
        self.assertLess(rate, 0.15)

    def test_a_total_loss_returns_a_negative_rate(self):
        flows = [('2021-01-01', -10_000.0), ('2022-01-01', 5_000.0)]

        self.assertLess(money_weighted_return(flows), -0.4)

    def test_flows_that_never_change_sign_return_none(self):
        self.assertIsNone(money_weighted_return([('2020-01-01', -1_000.0)]))


class CalendarYearTests(TestCase):

    def test_each_year_reports_its_own_growth(self):
        dates = ['2020-06-01', '2020-12-31', '2021-06-01', '2021-12-31']
        values = [1.0, 1.2, 1.2, 0.96]

        years = calendar_year_returns(values, dates)

        self.assertAlmostEqual(years['2020'], 0.2, places=12)
        self.assertAlmostEqual(years['2021'], -0.2, places=12)


class BetaAlphaTests(TestCase):

    def test_a_portfolio_identical_to_the_benchmark_has_beta_one_alpha_zero(self):
        rng = np.random.default_rng(3)
        benchmark = rng.normal(0.0004, 0.01, 500)

        beta, alpha = beta_alpha(benchmark, benchmark, 0.0)
        self.assertAlmostEqual(beta, 1.0, places=9)
        self.assertAlmostEqual(alpha, 0.0, places=9)

    def test_a_levered_portfolio_has_beta_two(self):
        rng = np.random.default_rng(5)
        benchmark = rng.normal(0.0004, 0.01, 500)

        beta, _ = beta_alpha(2 * benchmark, benchmark, 0.0)
        self.assertAlmostEqual(beta, 2.0, places=9)

    def test_alpha_is_annualized(self):
        rng = np.random.default_rng(11)
        benchmark = rng.normal(0.0, 0.01, 500)
        portfolio = benchmark + 0.001            # +0.1%/day

        _, alpha = beta_alpha(portfolio, benchmark, 0.0)
        self.assertAlmostEqual(alpha, 0.001 * 252, places=6)

    def test_too_few_observations_returns_none(self):
        self.assertEqual(beta_alpha([0.01], [0.01], 0.0), (None, None))


class CaptureRatioTests(TestCase):

    def test_a_half_beta_portfolio_captures_half_of_each_direction(self):
        benchmark = np.array([0.02, -0.02, 0.03, -0.01])
        portfolio = benchmark * 0.5

        up, down = capture_ratios(portfolio, benchmark)
        self.assertAlmostEqual(up, 0.5, places=12)
        self.assertAlmostEqual(down, 0.5, places=12)

    def test_a_benchmark_with_no_down_periods_reports_no_down_capture(self):
        up, down = capture_ratios(np.array([0.01, 0.02]), np.array([0.02, 0.03]))

        self.assertIsNotNone(up)
        self.assertIsNone(down)


class ContributionTests(TestCase):

    def test_contribution_to_return_sums_to_one(self):
        dates = pd.bdate_range('2020-01-01', periods=10)
        weights = pd.DataFrame({'A': 0.6, 'B': 0.4}, index=dates)
        returns = pd.DataFrame({'A': np.linspace(0.001, 0.01, 10),
                                'B': np.linspace(0.002, 0.004, 10)}, index=dates)

        shares = contribution_to_return(weights, returns)
        self.assertAlmostEqual(sum(shares.values()), 1.0, places=12)

    def test_contribution_to_risk_sums_to_one_and_matches_the_shared_definition(self):
        from backtester.engine.optimizers import relative_risk_contribution

        cov = np.array([[0.04, 0.01], [0.01, 0.09]])
        weights = np.array([0.7, 0.3])

        shares = contribution_to_risk(weights, cov, ['A', 'B'])
        self.assertAlmostEqual(sum(shares.values()), 1.0, places=12)
        np.testing.assert_allclose(list(shares.values()),
                                   relative_risk_contribution(weights, cov),
                                   rtol=1e-12)

    def test_correlation_matrix_is_symmetric_with_a_unit_diagonal(self):
        dates = pd.bdate_range('2020-01-01', periods=50)
        rng = np.random.default_rng(13)
        returns = pd.DataFrame(rng.normal(0, 0.01, (50, 3)),
                               index=dates, columns=['A', 'B', 'C'])

        matrix = correlation_matrix(returns)

        self.assertEqual(matrix['symbols'], ['A', 'B', 'C'])
        for i, row in enumerate(matrix['values']):
            self.assertAlmostEqual(row[i], 1.0, places=12)
            for j, value in enumerate(row):
                self.assertAlmostEqual(value, matrix['values'][j][i], places=12)


class ComputeMetricsTests(TestCase):
    """The full §9 table, driven off a real BacktestResult."""

    def setUp(self):
        from backtester.engine.backtest import run_backtest
        from backtester.engine.config import validate_request
        from backtester.engine.prices import PricePanel

        dates = pd.bdate_range('2018-01-01', periods=756)   # ~3 years
        rng = np.random.default_rng(17)
        path_a = 100 * np.cumprod(1 + rng.normal(0.0005, 0.011, 756))
        path_b = 100 * np.cumprod(1 + rng.normal(0.0003, 0.007, 756))
        frame = pd.DataFrame({'A': path_a, 'B': path_b}, index=dates)
        panel = PricePanel(
            prices=frame,
            first_valid={c: frame.index[0] for c in frame.columns},
            last_valid={c: frame.index[-1] for c in frame.columns},
            provenance={c: 'test' for c in frame.columns},
        )
        self.request = validate_request({
            'holdings': [{'symbol': 'A'}, {'symbol': 'B'}],
            'rebalance_frequency': 'annual', 'min_history_days': 1,
        })
        self.result = run_backtest(panel, self.request)
        self.returns_frame = panel.returns()
        self.benchmark_returns = rng.normal(0.0004, 0.010, len(self.result.dates))

    def _metrics(self, benchmark=False):
        return compute_metrics(
            self.result, self.request, returns_frame=self.returns_frame,
            benchmark_returns=self.benchmark_returns if benchmark else None)

    def test_every_documented_metric_is_present(self):
        expected = {
            'cagr', 'annualized_return', 'annualized_volatility', 'sharpe',
            'sortino', 'max_drawdown', 'max_drawdown_peak_date',
            'max_drawdown_trough_date', 'max_drawdown_recovery_date', 'calmar',
            'var_95', 'cvar_95', 'best_year', 'worst_year', 'calendar_year_returns',
            'beta', 'alpha', 'up_capture', 'down_capture', 'annual_turnover',
            'total_costs_paid', 'total_costs_annualized_bps', 'correlation_matrix',
            'contribution_to_return', 'contribution_to_risk', 'ending_balance',
            'total_contributed', 'total_gain', 'money_weighted_return', 'years',
        }
        metrics = self._metrics(benchmark=True)
        self.assertTrue(expected.issubset(metrics), expected - set(metrics))

    def test_cagr_is_derived_from_the_index_not_the_nav(self):
        metrics = self._metrics()

        years = len(self.result.dates) / 252
        expected = (self.result.index[-1] / self.result.index[0]) ** (1 / years) - 1
        self.assertAlmostEqual(metrics['cagr'], expected, places=12)

    def test_volatility_is_annualized_with_252_days(self):
        metrics = self._metrics()

        expected = float(np.std(self.result.returns[1:], ddof=1) * np.sqrt(252))
        self.assertAlmostEqual(metrics['annualized_volatility'], expected, places=12)

    def test_cvar_is_no_greater_than_var(self):
        self.assertLessEqual(self._metrics()['cvar_95'], self._metrics()['var_95'])

    def test_beta_is_omitted_without_a_benchmark(self):
        self.assertIsNone(self._metrics()['beta'])

    def test_beta_is_present_with_a_benchmark(self):
        self.assertIsNotNone(self._metrics(benchmark=True)['beta'])

    def test_every_value_is_json_serializable(self):
        import json

        json.dumps(self._metrics(benchmark=True))

    def test_balances_come_from_nav(self):
        metrics = self._metrics()

        self.assertAlmostEqual(metrics['ending_balance'], float(self.result.nav[-1]),
                               places=6)
        self.assertAlmostEqual(metrics['total_contributed'], 10_000.0, places=6)
        self.assertAlmostEqual(metrics['total_gain'],
                               float(self.result.nav[-1]) - 10_000.0, places=6)

    def test_contribution_shares_cover_every_holding(self):
        metrics = self._metrics()

        self.assertEqual(set(metrics['contribution_to_return']), {'A', 'B'})
        self.assertEqual(set(metrics['contribution_to_risk']), {'A', 'B'})
