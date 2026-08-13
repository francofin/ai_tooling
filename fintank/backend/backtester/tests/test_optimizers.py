"""The six weighting schemes. Pure numpy + scipy."""
from unittest import TestCase
from unittest.mock import patch

import numpy as np

from backtester.engine import optimizers
from backtester.engine.config import OptimizerConfig
from backtester.engine.covariance import estimate_covariance
from backtester.engine.optimizers import (
    OPTIMIZERS,
    optimize,
    relative_risk_contribution,
)

SCHEMES = ('equal', 'custom', 'inverse_vol', 'min_variance', 'risk_parity', 'max_sharpe')


def _returns(T=252, N=5, seed=1):
    rng = np.random.default_rng(seed)
    loadings = rng.normal(size=(N, 2))
    factors = rng.normal(size=(T, 2)) * 0.01
    scale = np.linspace(0.003, 0.012, N)          # deliberately unequal vols
    return factors @ loadings.T + rng.normal(size=(T, N)) * scale


def _config(**overrides):
    defaults = {'long_only': True, 'covariance_method': 'ledoit_wolf'}
    defaults.update(overrides)
    return OptimizerConfig(**defaults)


class RegistryTests(TestCase):

    def test_every_scheme_is_registered(self):
        self.assertEqual(set(OPTIMIZERS), set(SCHEMES))

    def test_unknown_scheme_raises(self):
        with self.assertRaises(ValueError):
            optimize(_returns(), _config(), 'wishful')


class ContractTests(TestCase):
    """§15 property tests -- these hold for every scheme."""

    def setUp(self):
        self.returns = _returns()
        self.custom = _config().with_custom_weights([0.4, 0.3, 0.2, 0.05, 0.05])

    def _config_for(self, scheme):
        return self.custom if scheme == 'custom' else _config()

    def test_weights_sum_to_one(self):
        for scheme in SCHEMES:
            with self.subTest(scheme=scheme):
                outcome = optimize(self.returns, self._config_for(scheme), scheme)
                self.assertAlmostEqual(outcome.weights.sum(), 1.0, delta=1e-9)

    def test_weights_are_non_negative_under_long_only(self):
        for scheme in SCHEMES:
            with self.subTest(scheme=scheme):
                outcome = optimize(self.returns, self._config_for(scheme), scheme)
                self.assertGreaterEqual(outcome.weights.min(), -1e-9)

    def test_weight_vector_length_matches_the_asset_count(self):
        for scheme in SCHEMES:
            with self.subTest(scheme=scheme):
                outcome = optimize(self.returns, self._config_for(scheme), scheme)
                self.assertEqual(outcome.weights.shape, (5,))

    def test_max_weight_is_respected(self):
        for scheme in ('min_variance', 'risk_parity', 'max_sharpe'):
            with self.subTest(scheme=scheme):
                outcome = optimize(self.returns, _config(max_weight=0.30), scheme)
                self.assertLessEqual(outcome.weights.max(), 0.30 + 1e-6)

    def test_min_weight_is_respected(self):
        for scheme in ('min_variance', 'risk_parity', 'max_sharpe'):
            with self.subTest(scheme=scheme):
                outcome = optimize(self.returns, _config(min_weight=0.10), scheme)
                self.assertGreaterEqual(outcome.weights.min(), 0.10 - 1e-6)

    def test_a_single_asset_gets_all_of_it(self):
        for scheme in SCHEMES:
            with self.subTest(scheme=scheme):
                config = (_config().with_custom_weights([1.0]) if scheme == 'custom'
                          else _config())
                outcome = optimize(_returns(T=60, N=1), config, scheme)
                np.testing.assert_allclose(outcome.weights, [1.0], atol=1e-9)


class ClosedFormTests(TestCase):

    def test_equal_weight_is_one_over_n(self):
        outcome = optimize(_returns(N=4), _config(), 'equal')

        np.testing.assert_allclose(outcome.weights, np.full(4, 0.25), atol=1e-12)

    def test_custom_uses_the_supplied_weights_renormalized(self):
        config = _config().with_custom_weights([2.0, 1.0, 1.0])
        outcome = optimize(_returns(N=3), config, 'custom')

        np.testing.assert_allclose(outcome.weights, [0.5, 0.25, 0.25], atol=1e-12)

    def test_custom_without_weights_falls_back_to_equal(self):
        outcome = optimize(_returns(N=4), _config(), 'custom')

        np.testing.assert_allclose(outcome.weights, np.full(4, 0.25), atol=1e-12)

    def test_inverse_vol_weights_are_proportional_to_one_over_sigma(self):
        returns = _returns(N=3, seed=7)
        cov = estimate_covariance(returns, 'ledoit_wolf')
        expected = 1.0 / np.sqrt(np.diag(cov))
        expected = expected / expected.sum()

        outcome = optimize(returns, _config(), 'inverse_vol')
        np.testing.assert_allclose(outcome.weights, expected, atol=1e-9)

    def test_inverse_vol_gives_the_least_volatile_asset_the_largest_weight(self):
        returns = _returns(N=5, seed=11)
        cov = estimate_covariance(returns, 'ledoit_wolf')

        outcome = optimize(returns, _config(), 'inverse_vol')
        self.assertEqual(int(np.argmax(outcome.weights)), int(np.argmin(np.diag(cov))))


class MinVarianceTests(TestCase):

    def test_variance_is_no_worse_than_equal_weight(self):
        """§15 property test."""
        returns = _returns(N=6, seed=13)
        cov = estimate_covariance(returns, 'ledoit_wolf')

        w_min = optimize(returns, _config(), 'min_variance').weights
        w_eq = np.full(6, 1 / 6)
        self.assertLessEqual(w_min @ cov @ w_min, w_eq @ cov @ w_eq + 1e-12)

    def test_unconstrained_solution_matches_the_closed_form(self):
        """With no bounds the analytic Σ⁻¹1 / 1ᵀΣ⁻¹1 is exact and is used."""
        returns = _returns(N=4, seed=17)
        cov = estimate_covariance(returns, 'ledoit_wolf')
        inv_ones = np.linalg.solve(cov, np.ones(4))
        expected = inv_ones / inv_ones.sum()

        config = OptimizerConfig(long_only=False, covariance_method='ledoit_wolf')
        outcome = optimize(returns, config, 'min_variance')
        np.testing.assert_allclose(outcome.weights, expected, atol=1e-9)


class RiskParityTests(TestCase):

    def test_relative_risk_contributions_sum_to_one(self):
        returns = _returns(N=5, seed=19)
        cov = estimate_covariance(returns, 'ledoit_wolf')
        weights = np.full(5, 0.2)

        self.assertAlmostEqual(relative_risk_contribution(weights, cov).sum(), 1.0,
                               delta=1e-12)

    def test_risk_contributions_are_equal_within_tolerance(self):
        """§15 property test -- the defining property of the scheme."""
        returns = _returns(N=5, seed=23)
        cov = estimate_covariance(returns, 'ledoit_wolf')

        weights = optimize(returns, _config(), 'risk_parity').weights
        contributions = relative_risk_contribution(weights, cov)
        self.assertLess(contributions.max() - contributions.min(), 1e-4)

    def test_risk_parity_and_inverse_vol_coincide_for_two_assets(self):
        """Not a coincidence: with N=2 the equal-risk-contribution portfolio *is*
        the inverse-volatility portfolio, whatever the correlation. Confirmed
        against live SPY/AGG data in class_files/backtester_portfolio.ipynb."""
        returns = _returns(N=2, seed=29)

        rp = optimize(returns, _config(), 'risk_parity').weights
        iv = optimize(returns, _config(), 'inverse_vol').weights
        np.testing.assert_allclose(rp, iv, atol=1e-6)

    def test_risk_parity_sits_between_equal_weight_and_min_variance(self):
        """Maillard, Roncalli & Teiletche (2010): the ERC portfolio's
        concentration falls between 1/N and minimum variance.

        Note what is *not* asserted: that the lowest-variance asset gets the
        largest weight. With three or more assets ERC depends on correlations as
        well as variances, so a low-variance asset that moves with everything
        else can legitimately be underweighted.
        """
        returns = _returns(N=6, seed=29)

        def effective_n(w):
            return 1.0 / float(np.sum(np.asarray(w) ** 2))

        equal = effective_n(np.full(6, 1 / 6))
        parity = effective_n(optimize(returns, _config(), 'risk_parity').weights)
        minimum = effective_n(optimize(returns, _config(), 'min_variance').weights)

        self.assertLessEqual(parity, equal + 1e-9)
        self.assertGreaterEqual(parity, minimum - 1e-9)


class MaxSharpeTests(TestCase):

    def test_it_beats_equal_weight_on_in_sample_sharpe(self):
        returns = _returns(N=5, seed=31)
        cov = estimate_covariance(returns, 'ledoit_wolf')
        mu = returns.mean(axis=0)

        def sharpe(w):
            return (w @ mu) / np.sqrt(w @ cov @ w)

        w_ms = optimize(returns, _config(), 'max_sharpe').weights
        self.assertGreaterEqual(sharpe(w_ms), sharpe(np.full(5, 0.2)) - 1e-9)

    def test_the_risk_free_rate_changes_the_solution(self):
        """r_f is an annual figure; the objective works in daily units."""
        returns = _returns(N=4, seed=37)

        zero = optimize(returns, _config(risk_free_rate=0.0), 'max_sharpe').weights
        high = optimize(returns, _config(risk_free_rate=0.05), 'max_sharpe').weights
        self.assertFalse(np.allclose(zero, high, atol=1e-6))


class FallbackTests(TestCase):
    """A backtest must never silently substitute a different strategy (§7)."""

    def test_non_convergence_falls_back_to_inverse_vol_and_says_so(self):
        returns = _returns(N=5, seed=41)
        expected = optimize(returns, _config(), 'inverse_vol').weights

        class Failed:
            x = np.full(5, np.nan)
            success = False
            message = 'forced'

        with patch.object(optimizers, 'minimize', return_value=Failed()):
            outcome = optimize(returns, _config(), 'risk_parity')

        self.assertFalse(outcome.converged)
        self.assertEqual(outcome.fallback_from, 'risk_parity')
        np.testing.assert_allclose(outcome.weights, expected, atol=1e-9)

    def test_a_converged_solve_reports_no_fallback(self):
        outcome = optimize(_returns(N=5, seed=43), _config(), 'min_variance')

        self.assertTrue(outcome.converged)
        self.assertIsNone(outcome.fallback_from)
