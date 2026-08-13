"""Efficient frontier sampling."""
from unittest import TestCase

import numpy as np

from backtester.engine.config import OptimizerConfig
from backtester.engine.frontier import sample_frontier


def _returns(T=504, N=4, seed=2):
    rng = np.random.default_rng(seed)
    loadings = rng.normal(size=(N, 2))
    factors = rng.normal(size=(T, 2)) * 0.01
    return factors @ loadings.T + rng.normal(size=(T, N)) * np.linspace(0.004, 0.011, N)


class FrontierTests(TestCase):

    def setUp(self):
        self.returns = _returns()
        self.symbols = ['A', 'B', 'C', 'D']
        self.config = OptimizerConfig(long_only=True, covariance_method='ledoit_wolf')
        self.result = sample_frontier(self.returns, self.symbols, self.config,
                                      portfolio_weights=[0.25] * 4,
                                      samples=300, grid=20, seed=1)

    def test_the_payload_carries_every_documented_key(self):
        self.assertEqual(set(self.result),
                         {'scatter', 'frontier', 'gmvp', 'tangency', 'portfolio',
                          'symbols', 'annualized'})

    def test_the_scatter_has_the_requested_number_of_samples(self):
        self.assertEqual(len(self.result['scatter']['volatility']), 300)
        self.assertEqual(len(self.result['scatter']['return']), 300)

    def test_the_frontier_curve_is_monotonically_increasing_in_return(self):
        returns = self.result['frontier']['return']

        self.assertTrue(all(b >= a - 1e-12 for a, b in zip(returns, returns[1:])))

    def test_the_gmvp_has_the_lowest_volatility_on_the_frontier(self):
        gmvp_volatility = self.result['gmvp']['volatility']

        self.assertLessEqual(gmvp_volatility,
                             min(self.result['frontier']['volatility']) + 1e-9)

    def test_no_random_sample_beats_the_frontier(self):
        """For each random portfolio, the frontier at that same expected return
        must be no more volatile than the random portfolio itself.

        Stated this way rather than "no scatter point sits above the curve",
        because the returned curve is a 20-point sample. A scatter point lands
        between grid nodes and would be compared against the nearest lower node,
        whose return is below the true frontier there - which reads as a
        violation and is only a discretization artifact. Solving exactly at each
        point's own return level is grid-independent.
        """
        from backtester.engine.covariance import estimate_covariance
        from backtester.engine.frontier import TRADING_DAYS, _min_variance_at

        cov = estimate_covariance(self.returns, 'ledoit_wolf')
        mu = self.returns.mean(axis=0)

        volatilities = self.result['scatter']['volatility']
        returns = self.result['scatter']['return']
        # Every 15th sample: the solve is exact but not free.
        for volatility, annual_return in list(zip(volatilities, returns))[::15]:
            weights = _min_variance_at(annual_return / TRADING_DAYS, mu, cov,
                                       self.config)
            if weights is None:
                continue
            frontier_volatility = float(
                np.sqrt(weights @ cov @ weights) * np.sqrt(TRADING_DAYS))
            self.assertLessEqual(frontier_volatility, volatility + 1e-6)

    def test_the_tangency_point_has_the_best_sharpe_on_the_frontier(self):
        tangency = self.result['tangency']
        best = tangency['return'] / tangency['volatility']

        for volatility, portfolio_return in zip(self.result['frontier']['volatility'],
                                                self.result['frontier']['return']):
            if volatility > 0:
                self.assertLessEqual(portfolio_return / volatility, best + 1e-6)

    def test_the_users_portfolio_is_marked_on_the_same_axes(self):
        portfolio = self.result['portfolio']

        self.assertGreater(portfolio['volatility'], 0.0)
        self.assertEqual(portfolio['weights'], dict(zip(self.symbols, [0.25] * 4)))

    def test_omitting_the_users_portfolio_leaves_it_null(self):
        result = sample_frontier(self.returns, self.symbols, self.config,
                                 samples=50, grid=10, seed=1)

        self.assertIsNone(result['portfolio'])

    def test_values_are_annualized(self):
        self.assertTrue(self.result['annualized'])
        # Daily vols are ~1%; annualized they are well above 2%.
        self.assertGreater(max(self.result['scatter']['volatility']), 0.02)

    def test_the_payload_is_json_serializable(self):
        import json

        json.dumps(self.result)

    def test_the_gmvp_variance_is_no_worse_than_equal_weight(self):
        equal = sample_frontier(self.returns, self.symbols, self.config,
                                portfolio_weights=[0.25] * 4,
                                samples=10, grid=5, seed=1)['portfolio']

        self.assertLessEqual(self.result['gmvp']['volatility'],
                             equal['volatility'] + 1e-9)

    def test_a_single_asset_degrades_gracefully(self):
        result = sample_frontier(_returns(N=1), ['A'], self.config,
                                 samples=20, grid=5, seed=1)

        self.assertEqual(len(result['frontier']['volatility']), 1)
        self.assertEqual(result['gmvp']['weights'], {'A': 1.0})

    def test_a_max_weight_constraint_is_respected_on_the_curve(self):
        capped = OptimizerConfig(long_only=True, covariance_method='ledoit_wolf',
                                 max_weight=0.4)
        result = sample_frontier(self.returns, self.symbols, capped,
                                 samples=20, grid=10, seed=1)

        self.assertLessEqual(max(result['gmvp']['weights'].values()), 0.4 + 1e-6)
