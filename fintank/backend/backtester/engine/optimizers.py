"""The six weighting schemes of §7.

Every scheme has the same signature -- (returns, config) -> weights -- borrowed
from the portfolioBacktest package's design. The backtest loop never learns
which one it called, which is what makes walk-forward nearly free and lets a
phase-2 scheme drop in as one registry entry.

All six are reachable with scipy.optimize, which is already a backend
dependency. No cvxpy, no riskfolio-lib.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from .config import OptimizerConfig
from .covariance import estimate_covariance

SOLVER_OPTIONS = {'maxiter': 500, 'ftol': 1e-12}


class SolverFailure(RuntimeError):
    """SLSQP failed to converge at one rebalance. Handled by `optimize`."""


@dataclass(frozen=True)
class OptimizerOutcome:
    """Weights plus enough provenance for the `optimizer_fallback` diagnostic."""
    weights: np.ndarray
    converged: bool = True
    fallback_from: str | None = None


def relative_risk_contribution(weights, cov) -> np.ndarray:
    """wᵢ(Σw)ᵢ / (wᵀΣw) -- the fraction of portfolio variance asset i carries.

    Sums to 1 by construction, which is what makes 1/N the right risk-parity
    target. This is the single shared definition: §7's risk-parity objective and
    §9's contribution-to-risk metric are the same computation, and
    engine/metrics.py imports this rather than restating it.

    Note: `create_index_contr_to_var()` in class_files/stock_data_getter_v2.ipynb
    computes the same quantity for index_data/contr_to_var/. Consolidating the
    notebook onto this function is deferred -- that notebook is outside this
    build's file allowlist.
    """
    weights = np.asarray(weights, dtype=float)
    cov = np.asarray(cov, dtype=float)
    portfolio_variance = float(weights @ cov @ weights)
    if portfolio_variance <= 0:
        return np.full(weights.shape, 1.0 / max(weights.size, 1))
    return weights * (cov @ weights) / portfolio_variance


def _bounds(n, config: OptimizerConfig):
    lower = 0.0 if config.long_only else -1.0
    if config.min_weight is not None:
        lower = max(lower, float(config.min_weight))
    upper = 1.0 if config.max_weight is None else float(config.max_weight)
    return [(lower, upper)] * n


def _unconstrained(n, config: OptimizerConfig) -> bool:
    """True when the only restriction is the budget constraint, so a closed form
    is exact and there is no reason to run a solver."""
    return (not config.long_only
            and config.max_weight is None
            and config.min_weight is None)


def _solve(objective, n, config: OptimizerConfig):
    """SLSQP warm-started from equal weight. Returns (weights, converged)."""
    start = np.full(n, 1.0 / n)
    result = minimize(
        objective, start, method='SLSQP',
        bounds=_bounds(n, config),
        constraints=({'type': 'eq', 'fun': lambda w: float(np.sum(w)) - 1.0},),
        options=SOLVER_OPTIONS,
    )
    weights = np.asarray(result.x, dtype=float)
    converged = bool(result.success) and np.all(np.isfinite(weights))
    if converged:
        total = weights.sum()
        # SLSQP satisfies the equality to ~1e-10; normalize so the caller's
        # sum-to-one assertion is exact.
        weights = weights / total if abs(total) > 1e-12 else np.full(n, 1.0 / n)
    return weights, converged


def _cov(returns, config: OptimizerConfig) -> np.ndarray:
    return estimate_covariance(returns, config.covariance_method)


def equal_weight(returns, config: OptimizerConfig) -> np.ndarray:
    n = np.asarray(returns).shape[1]
    return np.full(n, 1.0 / n)


def custom_weight(returns, config: OptimizerConfig) -> np.ndarray:
    """The user's targets for the eligible subset, renormalized over it (§5).

    Falls back to equal weight when no targets are attached, which is what the
    request contract guarantees for every scheme but `custom`.
    """
    n = np.asarray(returns).shape[1]
    if config.custom_weights is None:
        return np.full(n, 1.0 / n)
    weights = np.asarray(config.custom_weights, dtype=float)
    if weights.size != n:
        raise ValueError(
            f"custom_weights has {weights.size} entries for {n} eligible assets")
    total = weights.sum()
    if abs(total) < 1e-12:
        return np.full(n, 1.0 / n)
    return weights / total


def inverse_volatility(returns, config: OptimizerConfig) -> np.ndarray:
    variances = np.diag(_cov(returns, config))
    inverse = 1.0 / np.sqrt(np.maximum(variances, 1e-18))
    return inverse / inverse.sum()


def minimum_variance(returns, config: OptimizerConfig) -> np.ndarray:
    cov = _cov(returns, config)
    n = cov.shape[0]
    if n == 1:
        return np.ones(1)
    if _unconstrained(n, config):
        inv_ones = np.linalg.solve(cov, np.ones(n))
        return inv_ones / inv_ones.sum()
    weights, converged = _solve(lambda w: float(w @ cov @ w), n, config)
    if not converged:
        raise SolverFailure('min_variance did not converge')
    return weights


def risk_parity(returns, config: OptimizerConfig) -> np.ndarray:
    """Equalize relative risk contributions.

    The objective targets wᵢ(Σw)ᵢ/(wᵀΣw) = 1/N. §7's table writes the numerator
    over √(wᵀΣw), which sums to σ_p rather than 1 and would trade equality off
    against scaling σ_p toward 1; the relative form is what §9 defines and what
    makes the equal-contribution property exact.
    """
    cov = _cov(returns, config)
    n = cov.shape[0]
    if n == 1:
        return np.ones(1)
    target = 1.0 / n

    def objective(w):
        return float(np.sum((relative_risk_contribution(w, cov) - target) ** 2))

    weights, converged = _solve(objective, n, config)
    if not converged:
        raise SolverFailure('risk_parity did not converge')
    return weights


def maximum_sharpe(returns, config: OptimizerConfig) -> np.ndarray:
    """Maximize (wᵀμ − r_f) / √(wᵀΣw).

    μ is the sample mean of the lookback window -- a deliberately noisy
    estimate. The `return_estimation` diagnostic (§10) says so to the user.
    """
    returns = np.asarray(returns, dtype=float)
    cov = _cov(returns, config)
    n = cov.shape[0]
    if n == 1:
        return np.ones(1)
    mu = returns.mean(axis=0)
    daily_rf = float(config.risk_free_rate) / 252.0

    def objective(w):
        variance = float(w @ cov @ w)
        if variance <= 0:
            return 0.0
        return -(float(w @ mu) - daily_rf) / np.sqrt(variance)

    weights, converged = _solve(objective, n, config)
    if not converged:
        raise SolverFailure('max_sharpe did not converge')
    return weights


OPTIMIZERS = {
    'equal': equal_weight,
    'custom': custom_weight,
    'inverse_vol': inverse_volatility,
    'min_variance': minimum_variance,
    'risk_parity': risk_parity,
    'max_sharpe': maximum_sharpe,
}


def optimize(returns, config: OptimizerConfig, scheme: str) -> OptimizerOutcome:
    """Run one scheme, falling back to inverse-volatility on solver failure.

    The fallback is recorded rather than swallowed: silently substituting a
    different strategy would make the whole backtest a lie about what it tested.
    """
    if scheme not in OPTIMIZERS:
        raise ValueError(f"Unknown weighting scheme {scheme!r}")

    try:
        weights = OPTIMIZERS[scheme](returns, config)
    except SolverFailure:
        return OptimizerOutcome(
            weights=inverse_volatility(returns, config),
            converged=False,
            fallback_from=scheme,
        )

    weights = np.asarray(weights, dtype=float)
    if not np.all(np.isfinite(weights)):
        return OptimizerOutcome(
            weights=inverse_volatility(returns, config),
            converged=False,
            fallback_from=scheme,
        )
    return OptimizerOutcome(weights=weights)
