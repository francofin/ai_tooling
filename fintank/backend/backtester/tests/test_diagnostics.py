"""The seven-sins reality check."""
from types import SimpleNamespace
from unittest import TestCase

import numpy as np
import pandas as pd

from backtester.engine.config import validate_request
from backtester.engine.diagnostics import CODES, build_diagnostics


def _result(**overrides):
    dates = [d.strftime('%Y-%m-%d') for d in pd.bdate_range('2015-01-01', periods=1512)]
    rng = np.random.default_rng(3)
    returns = np.concatenate([[0.0], rng.normal(0.0004, 0.01, 1511)])
    index = np.cumprod(1 + returns)
    weights = pd.DataFrame({'A': 0.5, 'B': 0.5}, index=pd.to_datetime(dates))
    defaults = {
        'dates': dates,
        'nav': index * 10_000,
        'index': index,
        'returns': returns,
        'drawdown': np.minimum(index / np.maximum.accumulate(index) - 1, 0.0),
        'weights_over_time': weights,
        'effective_asset_count': np.full(len(dates), 2),
        'rebalance_events': [],
        'composition_events': [],
        'cash_flows': [(dates[0], -10_000.0), (dates[-1], float(index[-1] * 10_000))],
        'symbols': ['A', 'B'],
        'effective_start': dates[0],
        'effective_end': dates[-1],
        'truncation_cause': None,
        'fallback_dates': [],
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _request(**overrides):
    payload = {'holdings': [{'symbol': 'A'}, {'symbol': 'B'}],
               'rebalance_frequency': 'annual'}
    payload.update(overrides)
    return validate_request(payload)


def _metrics(**overrides):
    defaults = {'cagr': 0.09, 'years': 6.0, 'max_drawdown': -0.28,
                'annualized_volatility': 0.15}
    defaults.update(overrides)
    return defaults


def _codes(findings):
    return [finding['code'] for finding in findings]


class AlwaysFiringTests(TestCase):

    def test_survivorship_bias_always_fires(self):
        findings = build_diagnostics(_result(), _request(), _metrics())

        self.assertIn('survivorship_bias', _codes(findings))

    def test_every_finding_has_the_documented_shape(self):
        findings = build_diagnostics(_result(), _request(), _metrics())

        for finding in findings:
            self.assertEqual(set(finding), {'code', 'severity', 'title', 'detail'})
            self.assertIn(finding['severity'], ('info', 'warning', 'critical'))
            self.assertIn(finding['code'], CODES)
            self.assertTrue(finding['detail'].strip())

    def test_findings_are_ordered_most_severe_first(self):
        findings = build_diagnostics(
            _result(effective_asset_count=np.ones(1512)),
            _request(weighting_scheme='max_sharpe', backtest_mode='fixed'),
            _metrics())

        rank = {'critical': 0, 'warning': 1, 'info': 2}
        severities = [rank[f['severity']] for f in findings]
        self.assertEqual(severities, sorted(severities))


class TruncationAndCoverageTests(TestCase):

    def test_history_truncation_fires_when_the_start_moved(self):
        findings = build_diagnostics(
            _result(truncation_cause='Started 2018-01-02 rather than 2015-01-01: B.'),
            _request(), _metrics())

        finding = next(f for f in findings if f['code'] == 'history_truncation')
        self.assertIn('2018-01-02', finding['detail'])

    def test_composition_coverage_fires_when_half_the_assets_are_missing(self):
        """§10: fewer than half the assets held for more than 25% of the period."""
        counts = np.concatenate([np.ones(1000), np.full(512, 3)])
        findings = build_diagnostics(
            _result(effective_asset_count=counts, symbols=['A', 'B', 'C']),
            _request(holdings=[{'symbol': 'A'}, {'symbol': 'B'}, {'symbol': 'C'}]),
            _metrics())

        finding = next(f for f in findings if f['code'] == 'composition_coverage')
        self.assertEqual(finding['severity'], 'critical')
        self.assertIn('66', finding['detail'])

    def test_composition_coverage_stays_quiet_on_a_fully_populated_portfolio(self):
        findings = build_diagnostics(_result(), _request(), _metrics())

        self.assertNotIn('composition_coverage', _codes(findings))

    def test_single_asset_period_fires_beyond_thirty_trading_days(self):
        counts = np.concatenate([np.ones(40), np.full(1472, 2)])
        findings = build_diagnostics(_result(effective_asset_count=counts),
                                     _request(), _metrics())

        self.assertIn('single_asset_period', _codes(findings))

    def test_a_short_single_asset_span_does_not_fire(self):
        counts = np.concatenate([np.ones(10), np.full(1502, 2)])
        findings = build_diagnostics(_result(effective_asset_count=counts),
                                     _request(), _metrics())

        self.assertNotIn('single_asset_period', _codes(findings))


class OverfittingTests(TestCase):

    def test_in_sample_fit_fires_for_a_fixed_optimizer_run(self):
        findings = build_diagnostics(
            _result(), _request(weighting_scheme='min_variance',
                                backtest_mode='fixed'), _metrics())

        finding = next(f for f in findings if f['code'] == 'in_sample_fit')
        self.assertIn('walk-forward', finding['detail'])

    def test_in_sample_fit_stays_quiet_for_walk_forward(self):
        findings = build_diagnostics(
            _result(), _request(weighting_scheme='min_variance',
                                backtest_mode='walk_forward'), _metrics())

        self.assertNotIn('in_sample_fit', _codes(findings))

    def test_in_sample_fit_stays_quiet_for_equal_weight(self):
        findings = build_diagnostics(_result(), _request(backtest_mode='fixed'),
                                     _metrics())

        self.assertNotIn('in_sample_fit', _codes(findings))

    def test_return_estimation_fires_only_for_max_sharpe(self):
        with_ms = build_diagnostics(_result(),
                                    _request(weighting_scheme='max_sharpe'), _metrics())
        without = build_diagnostics(_result(),
                                    _request(weighting_scheme='min_variance'), _metrics())

        self.assertIn('return_estimation', _codes(with_ms))
        self.assertNotIn('return_estimation', _codes(without))

    def test_short_sample_fires_under_three_years(self):
        findings = build_diagnostics(_result(), _request(), _metrics(years=2.0))

        self.assertIn('short_sample', _codes(findings))

    def test_short_sample_fires_with_too_few_rebalances(self):
        findings = build_diagnostics(_result(), _request(), _metrics(years=8.0))

        # Eight years of annual rebalancing is 8 observations, well under 60.
        self.assertIn('short_sample', _codes(findings))

    def test_short_sample_stays_quiet_with_a_long_monthly_run(self):
        events = [{'date': '2016-01-04', 'turnover': 0.01, 'cost': 0.0,
                   'trigger': 'scheduled', 'weights': {}} for _ in range(80)]
        findings = build_diagnostics(_result(rebalance_events=events), _request(),
                                     _metrics(years=8.0))

        self.assertNotIn('short_sample', _codes(findings))


class CostAndOutlierTests(TestCase):

    def test_cost_sensitivity_fires_when_fees_eat_the_gross_return(self):
        events = [{'date': '2016-01-04', 'turnover': 2.0, 'cost': 0.02,
                   'trigger': 'scheduled', 'weights': {}} for _ in range(6)]
        result = _result(rebalance_events=events)
        result.index = np.linspace(1.0, 1.10, len(result.dates))

        findings = build_diagnostics(result, _request(), _metrics(cagr=0.02))
        self.assertIn('cost_sensitivity', _codes(findings))

    def test_cost_sensitivity_stays_quiet_on_a_cheap_strategy(self):
        findings = build_diagnostics(_result(), _request(), _metrics())

        self.assertNotIn('cost_sensitivity', _codes(findings))

    def test_outlier_dependence_fires_when_five_days_carry_the_return(self):
        dates = [d.strftime('%Y-%m-%d') for d in pd.bdate_range('2015-01-01', periods=800)]
        returns = np.zeros(800)
        returns[[10, 20, 30, 40, 50]] = 0.30      # everything comes from 5 days
        index = np.cumprod(1 + returns)
        result = _result(dates=dates, returns=returns, index=index,
                         nav=index * 10_000,
                         effective_asset_count=np.full(800, 2),
                         weights_over_time=pd.DataFrame(
                             {'A': 0.5, 'B': 0.5}, index=pd.to_datetime(dates)))

        findings = build_diagnostics(result, _request(), _metrics(years=3.2))
        self.assertIn('outlier_dependence', _codes(findings))

    def test_outlier_dependence_stays_quiet_on_a_broad_based_return(self):
        findings = build_diagnostics(_result(), _request(), _metrics())

        self.assertNotIn('outlier_dependence', _codes(findings))


class ConcentrationAndShortingTests(TestCase):

    def test_concentration_fires_above_a_forty_percent_weight(self):
        dates = pd.bdate_range('2015-01-01', periods=1512)
        weights = pd.DataFrame({'A': 0.6, 'B': 0.2, 'C': 0.2}, index=dates)
        findings = build_diagnostics(
            _result(weights_over_time=weights, symbols=['A', 'B', 'C'],
                    effective_asset_count=np.full(1512, 3)),
            _request(holdings=[{'symbol': 'A'}, {'symbol': 'B'}, {'symbol': 'C'}]),
            _metrics())

        self.assertIn('concentration', _codes(findings))

    def test_concentration_fires_on_a_low_effective_n(self):
        findings = build_diagnostics(_result(), _request(), _metrics())

        # 50/50 gives effective N = 2, below the threshold of 3.
        self.assertIn('concentration', _codes(findings))

    def test_concentration_stays_quiet_on_a_well_spread_portfolio(self):
        dates = pd.bdate_range('2015-01-01', periods=1512)
        symbols = [f"S{i}" for i in range(8)]
        weights = pd.DataFrame({s: 1 / 8 for s in symbols}, index=dates)
        findings = build_diagnostics(
            _result(weights_over_time=weights, symbols=symbols,
                    effective_asset_count=np.full(1512, 8)),
            _request(holdings=[{'symbol': s} for s in symbols]),
            _metrics())

        self.assertNotIn('concentration', _codes(findings))

    def test_shorting_unmodelled_fires_when_long_only_is_off(self):
        findings = build_diagnostics(_result(), _request(long_only=False), _metrics())

        finding = next(f for f in findings if f['code'] == 'shorting_unmodelled')
        self.assertIn('borrow', finding['detail'].lower())

    def test_shorting_unmodelled_stays_quiet_by_default(self):
        findings = build_diagnostics(_result(), _request(), _metrics())

        self.assertNotIn('shorting_unmodelled', _codes(findings))


class FallbackAndBenchmarkTests(TestCase):

    def test_optimizer_fallback_lists_the_dates(self):
        findings = build_diagnostics(
            _result(fallback_dates=['2018-01-02', '2019-01-02']),
            _request(weighting_scheme='risk_parity'), _metrics())

        finding = next(f for f in findings if f['code'] == 'optimizer_fallback')
        self.assertEqual(finding['severity'], 'critical')
        self.assertIn('2018-01-02', finding['detail'])

    def test_benchmark_mismatch_fires_on_a_weakly_correlated_benchmark(self):
        rng = np.random.default_rng(9)
        result = _result()
        benchmark = rng.normal(0.0004, 0.01, len(result.dates))

        findings = build_diagnostics(result, _request(), _metrics(),
                                     benchmark_returns=benchmark)
        self.assertIn('benchmark_mismatch', _codes(findings))

    def test_benchmark_mismatch_stays_quiet_when_correlation_is_high(self):
        result = _result()
        benchmark = np.asarray(result.returns) * 0.9

        findings = build_diagnostics(result, _request(), _metrics(),
                                     benchmark_returns=benchmark)
        self.assertNotIn('benchmark_mismatch', _codes(findings))

    def test_no_benchmark_means_no_mismatch_finding(self):
        findings = build_diagnostics(_result(), _request(), _metrics())

        self.assertNotIn('benchmark_mismatch', _codes(findings))


class TwoHoldingCoverageTests(TestCase):
    """Why composition_coverage and single_asset_period both exist.

    §10 defines coverage as holding *fewer than half* the requested assets. With
    two holdings that means holding zero, which never happens - so a 60/40 that
    was really 100% SPY for its first five years cannot trip the coverage rule.
    single_asset_period is what catches it. Verified against live SPY/AGG, where
    the phase-in run fires single_asset_period as critical and coverage not at
    all. Do not "fix" coverage to fire here; the sibling diagnostic covers it.
    """

    def test_a_two_holding_portfolio_never_trips_coverage(self):
        counts = np.concatenate([np.ones(1000), np.full(512, 2)])
        findings = build_diagnostics(_result(effective_asset_count=counts),
                                     _request(), _metrics())

        self.assertNotIn('composition_coverage', _codes(findings))

    def test_but_single_asset_period_catches_the_same_situation(self):
        counts = np.concatenate([np.ones(1000), np.full(512, 2)])
        findings = build_diagnostics(_result(effective_asset_count=counts),
                                     _request(), _metrics())

        finding = next(f for f in findings if f['code'] == 'single_asset_period')
        self.assertEqual(finding['severity'], 'critical')
