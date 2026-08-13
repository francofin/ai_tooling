"""Efficient frontier sampling for the illustrative chart of §7.

Computed on the full-period, in-sample covariance. That makes it a picture of
the opportunity set as it turned out, not a forecast and not a walk-forward
result -- the UI labels it accordingly.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from .config import OptimizerConfig
from .covariance import estimate_covariance

TRADING_DAYS = 252


def _annualized(weights, mu, cov):
    portfolio_return = float(weights @ mu) * TRADING_DAYS
    volatility = float(np.sqrt(max(weights @ cov @ weights, 0.0))) * np.sqrt(TRADING_DAYS)
    return volatility, portfolio_return


def _point(weights, mu, cov, symbols):
    volatility, portfolio_return = _annualized(weights, mu, cov)
    return {
        'volatility': volatility,
        'return': portfolio_return,
        'sharpe': (portfolio_return / volatility) if volatility > 0 else None,
        'weights': {symbol: float(round(w, 6)) for symbol, w in zip(symbols, weights)},
    }


def _bounds(n, config: OptimizerConfig):
    lower = 0.0 if config.long_only else -1.0
    if config.min_weight is not None:
        lower = max(lower, float(config.min_weight))
    upper = 1.0 if config.max_weight is None else float(config.max_weight)
    return [(lower, upper)] * n


def _min_variance_at(target_return, mu, cov, config):
    """Min variance subject to a target expected return -- one point on the
    analytic frontier."""
    n = cov.shape[0]
    constraints = (
        {'type': 'eq', 'fun': lambda w: float(np.sum(w)) - 1.0},
        {'type': 'eq', 'fun': lambda w: float(w @ mu) - target_return},
    )
    result = minimize(lambda w: float(w @ cov @ w), np.full(n, 1.0 / n),
                      method='SLSQP', bounds=_bounds(n, config),
                      constraints=constraints,
                      options={'maxiter': 300, 'ftol': 1e-12})
    if not result.success or not np.all(np.isfinite(result.x)):
        return None
    weights = np.asarray(result.x, dtype=float)
    total = weights.sum()
    return weights / total if abs(total) > 1e-12 else None


def sample_frontier(returns, symbols, config: OptimizerConfig,
                    portfolio_weights=None, samples: int = 2000,
                    grid: int = 40, seed: int = 0) -> dict:
    returns = np.asarray(returns, dtype=float)
    cov = estimate_covariance(returns, config.covariance_method)
    mu = returns.mean(axis=0)
    n = cov.shape[0]
    symbols = list(symbols)

    if n == 1:
        only = np.ones(1)
        point = _point(only, mu, cov, symbols)
        return {
            'scatter': {'volatility': [point['volatility']], 'return': [point['return']]},
            'frontier': {'volatility': [point['volatility']], 'return': [point['return']]},
            'gmvp': point,
            'tangency': point,
            'portfolio': point if portfolio_weights is not None else None,
            'symbols': symbols,
            'annualized': True,
        }

    # Random long-only weight vectors: a Dirichlet draw is uniform over the
    # simplex, which is what makes the cloud an honest picture of "any portfolio
    # you could have picked".
    rng = np.random.default_rng(seed)
    draws = rng.dirichlet(np.ones(n), size=int(samples))
    scatter_volatility = (np.sqrt(np.einsum('ij,jk,ik->i', draws, cov, draws))
                          * np.sqrt(TRADING_DAYS))
    scatter_return = draws @ mu * TRADING_DAYS

    # The GMVP is the unconstrained-in-return minimum, so it is solved directly
    # rather than through _min_variance_at's target-return constraint.
    result = minimize(lambda w: float(w @ cov @ w), np.full(n, 1.0 / n),
                      method='SLSQP', bounds=_bounds(n, config),
                      constraints=({'type': 'eq', 'fun': lambda w: float(np.sum(w)) - 1.0},),
                      options={'maxiter': 300, 'ftol': 1e-12})
    gmvp_weights = (np.asarray(result.x) / np.sum(result.x)
                    if result.success else np.full(n, 1.0 / n))
    gmvp = _point(gmvp_weights, mu, cov, symbols)

    lowest = float(gmvp_weights @ mu)
    highest = float(mu.max())
    curve = []
    for target in np.linspace(lowest, highest, int(grid)):
        weights = _min_variance_at(float(target), mu, cov, config)
        if weights is not None:
            curve.append(_point(weights, mu, cov, symbols))

    if not curve:
        curve = [gmvp]
    curve.sort(key=lambda p: p['return'])
    tangency = max(curve, key=lambda p: p['sharpe'] if p['sharpe'] else -np.inf)

    return {
        'scatter': {'volatility': [float(v) for v in scatter_volatility],
                    'return': [float(r) for r in scatter_return]},
        'frontier': {'volatility': [p['volatility'] for p in curve],
                     'return': [p['return'] for p in curve]},
        'gmvp': gmvp,
        'tangency': tangency,
        'portfolio': (_point(np.asarray(portfolio_weights, dtype=float), mu, cov, symbols)
                      if portfolio_weights is not None else None),
        'symbols': symbols,
        'annualized': True,
    }
