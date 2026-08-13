"""Covariance estimation for the optimizers.

Ledoit-Wolf is implemented directly rather than imported: it is ~30 lines, and
adding scikit-learn to the backend for one estimator is not warranted (§6).
"""
from __future__ import annotations

import numpy as np

METHODS = ('sample', 'ledoit_wolf')


def _validated(returns) -> np.ndarray:
    returns = np.asarray(returns, dtype=float)
    if returns.ndim != 2:
        raise ValueError('returns must be a T x N matrix')
    if returns.shape[0] < 2:
        raise ValueError('covariance needs at least 2 observations')
    return returns


def sample_covariance(returns) -> np.ndarray:
    returns = _validated(returns)
    cov = np.cov(returns, rowvar=False, ddof=1)
    return np.atleast_2d(cov)


def ledoit_wolf_covariance(returns) -> np.ndarray:
    """Ledoit-Wolf (2004) well-conditioned estimator: shrink the sample
    covariance toward a scaled identity, with the shrinkage intensity chosen to
    minimize expected squared Frobenius error.

    Notation follows §6: S is the (biased, /T) sample covariance of the demeaned
    block, m its average variance, d² its squared distance from m·I, and b̄² the
    average squared deviation of the per-observation outer products from S.

    Default for a reason: with 252 daily observations and 10-30 assets the sample
    covariance is poorly conditioned, and both min-variance and max-Sharpe invert
    it. That is precisely the regime where shrinkage matters most, and a
    documented driver of the "optimizers underperform 1/N" result.
    """
    returns = _validated(returns)
    T, N = returns.shape
    if N == 1:
        # Nothing to shrink toward: a scaled identity *is* the sample estimate.
        return sample_covariance(returns)

    X = returns - returns.mean(axis=0)
    S = X.T @ X / T

    m = np.trace(S) / N
    d2 = np.sum((S - m * np.eye(N)) ** 2) / N
    if d2 <= 0:
        return sample_covariance(returns)

    # Σ_t ‖x_t x_tᵀ − S‖²_F expanded so no T x N x N array is materialized.
    # ‖x xᵀ‖²_F = (xᵀx)², and Σ_t <x_t x_tᵀ, S> = <T·S, S> = T‖S‖²_F, so the
    # whole sum collapses to  Σ_t (x_tᵀ x_t)² − T‖S‖²_F.
    squared_norms = np.einsum('ij,ij->i', X, X)
    total = float(np.sum(squared_norms ** 2)) - T * float(np.sum(S * S))
    b2_bar = total / (T ** 2) / N

    b2 = min(max(b2_bar, 0.0), d2)
    a2 = d2 - b2

    shrunk = (b2 / d2) * m * np.eye(N) + (a2 / d2) * S
    return (shrunk + shrunk.T) / 2.0   # kill float asymmetry


def estimate_covariance(returns, method: str = 'ledoit_wolf') -> np.ndarray:
    if method == 'sample':
        return sample_covariance(returns)
    if method == 'ledoit_wolf':
        return ledoit_wolf_covariance(returns)
    raise ValueError(f"Unknown covariance method {method!r}; expected one of {METHODS}")
