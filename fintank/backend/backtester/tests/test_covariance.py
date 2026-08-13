"""Covariance estimators. Pure numpy -- no Django needed."""
from unittest import TestCase

import numpy as np

from backtester.engine.covariance import (
    estimate_covariance,
    ledoit_wolf_covariance,
    sample_covariance,
)


def _returns(T=252, N=8, seed=0):
    rng = np.random.default_rng(seed)
    loadings = rng.normal(size=(N, 2))
    factors = rng.normal(size=(T, 2)) * 0.01
    noise = rng.normal(size=(T, N)) * 0.004
    return factors @ loadings.T + noise


class SampleCovarianceTests(TestCase):

    def test_matches_numpy_cov(self):
        returns = _returns()

        np.testing.assert_allclose(sample_covariance(returns),
                                   np.cov(returns, rowvar=False, ddof=1))

    def test_shape_is_n_by_n(self):
        self.assertEqual(sample_covariance(_returns(T=50, N=5)).shape, (5, 5))

    def test_single_asset_returns_a_one_by_one_matrix(self):
        returns = _returns(T=40, N=1)

        cov = sample_covariance(returns)
        self.assertEqual(cov.shape, (1, 1))
        self.assertGreater(cov[0, 0], 0.0)


class LedoitWolfTests(TestCase):

    def test_the_vectorized_b2_matches_a_brute_force_loop(self):
        """Guards the einsum expansion of Sigma_t ||x x' - S||_F^2."""
        returns = _returns(T=60, N=10, seed=2)
        X = returns - returns.mean(axis=0)
        T, N = X.shape
        S = X.T @ X / T
        brute = sum(np.sum((np.outer(x, x) - S) ** 2) for x in X) / (T ** 2) / N

        squared_norms = np.einsum('ij,ij->i', X, X)
        vectorized = (float(np.sum(squared_norms ** 2))
                      - T * float(np.sum(S * S))) / (T ** 2) / N

        self.assertAlmostEqual(brute, vectorized, places=12)

    def test_output_is_symmetric(self):
        cov = ledoit_wolf_covariance(_returns())

        np.testing.assert_allclose(cov, cov.T, atol=1e-15)

    def test_output_is_positive_semi_definite(self):
        eigenvalues = np.linalg.eigvalsh(ledoit_wolf_covariance(_returns()))

        self.assertGreaterEqual(eigenvalues.min(), -1e-14)

    def test_condition_number_is_no_worse_than_the_sample_estimator(self):
        """The whole point of shrinkage: a better-conditioned matrix to invert."""
        returns = _returns(T=60, N=40, seed=3)   # T < N: sample is singular

        shrunk = np.linalg.cond(ledoit_wolf_covariance(returns))
        plain = np.linalg.cond(sample_covariance(returns))
        self.assertLess(shrunk, plain)

    def test_shrinkage_contracts_the_spread_of_variances_and_covariances(self):
        returns = _returns(T=60, N=30, seed=5)

        shrunk = ledoit_wolf_covariance(returns)
        plain = sample_covariance(returns)
        # Off-diagonals move toward zero; the spread of variances contracts.
        self.assertLess(np.std(np.diag(shrunk)), np.std(np.diag(plain)))
        self.assertLess(np.abs(shrunk[np.triu_indices_from(shrunk, 1)]).mean(),
                        np.abs(plain[np.triu_indices_from(plain, 1)]).mean())

    def test_a_single_asset_is_returned_unshrunk(self):
        returns = _returns(T=40, N=1)

        np.testing.assert_allclose(ledoit_wolf_covariance(returns),
                                   sample_covariance(returns), rtol=1e-9)


class EstimateCovarianceTests(TestCase):

    def test_dispatches_on_method(self):
        returns = _returns(T=80, N=6)

        np.testing.assert_allclose(estimate_covariance(returns, 'sample'),
                                   sample_covariance(returns))
        np.testing.assert_allclose(estimate_covariance(returns, 'ledoit_wolf'),
                                   ledoit_wolf_covariance(returns))

    def test_default_method_is_ledoit_wolf(self):
        returns = _returns(T=80, N=6)

        np.testing.assert_allclose(estimate_covariance(returns),
                                   ledoit_wolf_covariance(returns))

    def test_unknown_method_raises(self):
        with self.assertRaises(ValueError):
            estimate_covariance(_returns(T=30, N=3), 'wishful')

    def test_too_few_observations_raises(self):
        with self.assertRaises(ValueError):
            estimate_covariance(np.zeros((1, 3)), 'sample')
