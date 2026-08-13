"""Typed request contract for a portfolio backtest.

Pure: no Django, no I/O. The view layer's only job is to hand `validate_request`
a dict and turn `RequestValidationError` into a 422, which keeps every
validation rule unit-testable without a request factory.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime

import numpy as np

WEIGHTING_SCHEMES = ('equal', 'custom', 'inverse_vol', 'min_variance',
                     'risk_parity', 'max_sharpe')
# Schemes that estimate a covariance and therefore need a complete rectangular
# block of returns before an asset can enter (§5).
OPTIMIZER_SCHEMES = ('inverse_vol', 'min_variance', 'risk_parity', 'max_sharpe')
BACKTEST_MODES = ('fixed', 'walk_forward')
REBALANCE_FREQUENCIES = ('none', 'monthly', 'quarterly', 'semiannual', 'annual')
CONTRIBUTION_FREQUENCIES = ('none', 'monthly', 'quarterly', 'annual')
COVARIANCE_METHODS = ('sample', 'ledoit_wolf')
INCEPTION_POLICIES = ('phase_in', 'common_start')

DEFAULT_MIN_HISTORY_DAYS = 1
TRADING_DAYS_PER_YEAR = 252


class RequestValidationError(ValueError):
    """Bad input. The view renders this as 422."""


class NoEligibleAssets(ValueError):
    """No requested asset ever clears its eligibility bar (§5). 422."""


class PriceDataUnavailable(RuntimeError):
    """Neither S3 nor FMP could serve a symbol. Carries the per-symbol reason."""

    def __init__(self, message, reasons=None):
        super().__init__(message)
        self.reasons = reasons or {}


@dataclass(frozen=True)
class Holding:
    symbol: str
    target_weight: float = 0.0


@dataclass(frozen=True)
class BacktestRequest:
    holdings: tuple[Holding, ...]
    benchmark_symbol: str = 'SPY'
    start_date: date | None = None
    end_date: date | None = None
    initial_amount: float = 10_000.0
    periodic_contribution: float = 0.0
    contribution_frequency: str = 'none'

    weighting_scheme: str = 'equal'
    backtest_mode: str = 'fixed'
    rebalance_frequency: str = 'annual'

    lookback_days: int = 252
    gap_days: int = 1
    covariance_method: str = 'ledoit_wolf'
    transaction_cost_bps: float = 10.0
    long_only: bool = True
    max_weight: float | None = None
    min_weight: float | None = None
    risk_free_rate: float = 0.0
    inception_policy: str = 'phase_in'
    enter_immediately: bool = False
    min_history_days: int = DEFAULT_MIN_HISTORY_DAYS

    @property
    def symbols(self) -> list:
        return [h.symbol for h in self.holdings]

    @property
    def target_weights(self) -> np.ndarray:
        return np.array([h.target_weight for h in self.holdings], dtype=float)


@dataclass(frozen=True)
class OptimizerConfig:
    """What every scheme in `engine/optimizers.py` receives.

    `custom_weights` is the eligible-subset slice of the user's targets, already
    renormalized by the caller. It is None for every scheme but `custom`.
    """
    long_only: bool = True
    max_weight: float | None = None
    min_weight: float | None = None
    risk_free_rate: float = 0.0
    covariance_method: str = 'ledoit_wolf'
    custom_weights: np.ndarray | None = None

    def with_custom_weights(self, weights) -> 'OptimizerConfig':
        return replace(self, custom_weights=np.asarray(weights, dtype=float))


def _choice(payload, key, allowed, default):
    value = payload.get(key, default)
    if value not in allowed:
        raise RequestValidationError(
            f"{key} must be one of {', '.join(allowed)} (got {value!r})")
    return value


def _number(payload, key, default, minimum=None, allow_none=False):
    raw = payload.get(key, default)
    if raw is None:
        if allow_none:
            return None
        raise RequestValidationError(f"{key} is required")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise RequestValidationError(f"{key} must be a number (got {raw!r})")
    if value != value:  # NaN
        raise RequestValidationError(f"{key} must be a number (got NaN)")
    if minimum is not None and value < minimum:
        raise RequestValidationError(f"{key} must be >= {minimum} (got {value})")
    return value


def _date(payload, key):
    raw = payload.get(key)
    if raw in (None, ''):
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    try:
        return datetime.strptime(str(raw)[:10], '%Y-%m-%d').date()
    except ValueError:
        raise RequestValidationError(f"{key} must be an ISO date (got {raw!r})")


def _holdings(payload, weighting_scheme, long_only):
    raw = payload.get('holdings') or []
    if not isinstance(raw, (list, tuple)) or not raw:
        raise RequestValidationError('A backtest needs at least one holding.')

    seen, holdings = set(), []
    for entry in raw:
        if isinstance(entry, str):
            entry = {'symbol': entry}
        symbol = str(entry.get('symbol', '')).strip().upper()
        if not symbol:
            raise RequestValidationError('Every holding needs a symbol.')
        if symbol in seen:
            raise RequestValidationError(f"{symbol} appears more than once.")
        seen.add(symbol)
        weight = entry.get('target_weight', 0.0)
        try:
            weight = float(weight if weight is not None else 0.0)
        except (TypeError, ValueError):
            raise RequestValidationError(
                f"target_weight for {symbol} must be a number.")
        holdings.append(Holding(symbol=symbol, target_weight=weight))

    if weighting_scheme != 'custom':
        # Ignored for every other scheme (§3). Zero it so the request hash does
        # not vary on a field that cannot affect the result.
        return tuple(Holding(h.symbol, 0.0) for h in holdings)

    if long_only and any(h.target_weight < 0 for h in holdings):
        raise RequestValidationError(
            'Custom weights cannot be negative while long_only is on.')
    total = sum(h.target_weight for h in holdings)
    if total <= 0:
        raise RequestValidationError('Custom weights must sum to more than zero.')
    return tuple(Holding(h.symbol, h.target_weight / total) for h in holdings)


def validate_request(payload: dict) -> BacktestRequest:
    """Turn an untrusted dict into a BacktestRequest, or raise."""
    if not isinstance(payload, dict):
        raise RequestValidationError('Request body must be an object.')

    weighting_scheme = _choice(payload, 'weighting_scheme', WEIGHTING_SCHEMES, 'equal')
    long_only = bool(payload.get('long_only', True))
    holdings = _holdings(payload, weighting_scheme, long_only)
    n = len(holdings)

    lookback_days = int(_number(payload, 'lookback_days', 252, minimum=2))
    gap_days = int(_number(payload, 'gap_days', 1, minimum=0))
    max_weight = _number(payload, 'max_weight', None, minimum=0.0, allow_none=True)
    min_weight = _number(payload, 'min_weight', None, minimum=0.0, allow_none=True)

    # Feasibility before the solver sees it: an infeasible box produces a silent
    # SLSQP failure that looks like a numerical problem rather than bad input.
    if max_weight is not None and max_weight * n < 1.0 - 1e-12:
        raise RequestValidationError(
            f"max_weight={max_weight} cannot fill a portfolio of {n} assets; "
            f"it must be at least {1.0 / n:.4f}.")
    if min_weight is not None and min_weight * n > 1.0 + 1e-12:
        raise RequestValidationError(
            f"min_weight={min_weight} over-fills a portfolio of {n} assets; "
            f"it must be at most {1.0 / n:.4f}.")
    if (max_weight is not None and min_weight is not None
            and min_weight > max_weight):
        raise RequestValidationError('min_weight cannot exceed max_weight.')

    start_date, end_date = _date(payload, 'start_date'), _date(payload, 'end_date')
    if start_date and end_date and start_date >= end_date:
        raise RequestValidationError('start_date must be before end_date.')

    min_history_days = payload.get('min_history_days')
    if min_history_days in (None, ''):
        min_history_days = (lookback_days if weighting_scheme in OPTIMIZER_SCHEMES
                            else DEFAULT_MIN_HISTORY_DAYS)
    min_history_days = int(_number({'v': min_history_days}, 'v', None, minimum=1))

    benchmark = str(payload.get('benchmark_symbol') or 'SPY').strip().upper()

    return BacktestRequest(
        holdings=holdings,
        benchmark_symbol=benchmark,
        start_date=start_date,
        end_date=end_date,
        initial_amount=_number(payload, 'initial_amount', 10_000.0, minimum=0.01),
        periodic_contribution=_number(payload, 'periodic_contribution', 0.0, minimum=0.0),
        contribution_frequency=_choice(payload, 'contribution_frequency',
                                       CONTRIBUTION_FREQUENCIES, 'none'),
        weighting_scheme=weighting_scheme,
        backtest_mode=_choice(payload, 'backtest_mode', BACKTEST_MODES, 'fixed'),
        rebalance_frequency=_choice(payload, 'rebalance_frequency',
                                    REBALANCE_FREQUENCIES, 'annual'),
        lookback_days=lookback_days,
        gap_days=gap_days,
        covariance_method=_choice(payload, 'covariance_method',
                                  COVARIANCE_METHODS, 'ledoit_wolf'),
        transaction_cost_bps=_number(payload, 'transaction_cost_bps', 10.0, minimum=0.0),
        long_only=long_only,
        max_weight=max_weight,
        min_weight=min_weight,
        risk_free_rate=_number(payload, 'risk_free_rate', 0.0),
        inception_policy=_choice(payload, 'inception_policy', INCEPTION_POLICIES,
                                 'phase_in'),
        enter_immediately=bool(payload.get('enter_immediately', False)),
        min_history_days=min_history_days,
    )


def normalized_payload(request: BacktestRequest) -> dict:
    """Canonical JSON-safe dict. Two requests that must share a cache entry
    normalize to the same dict, so sha256(json(sort_keys=True)) is a usable
    identity for the dedupe in §12."""
    return {
        'holdings': [{'symbol': h.symbol, 'target_weight': round(h.target_weight, 9)}
                     for h in request.holdings],
        'benchmark_symbol': request.benchmark_symbol,
        'start_date': request.start_date.isoformat() if request.start_date else None,
        'end_date': request.end_date.isoformat() if request.end_date else None,
        'initial_amount': round(request.initial_amount, 4),
        'periodic_contribution': round(request.periodic_contribution, 4),
        'contribution_frequency': request.contribution_frequency,
        'weighting_scheme': request.weighting_scheme,
        'backtest_mode': request.backtest_mode,
        'rebalance_frequency': request.rebalance_frequency,
        'lookback_days': request.lookback_days,
        'gap_days': request.gap_days,
        'covariance_method': request.covariance_method,
        'transaction_cost_bps': round(request.transaction_cost_bps, 6),
        'long_only': request.long_only,
        'max_weight': request.max_weight,
        'min_weight': request.min_weight,
        'risk_free_rate': round(request.risk_free_rate, 8),
        'inception_policy': request.inception_policy,
        'enter_immediately': request.enter_immediately,
        'min_history_days': request.min_history_days,
    }


def optimizer_config(request: BacktestRequest, custom_weights=None) -> OptimizerConfig:
    config = OptimizerConfig(
        long_only=request.long_only,
        max_weight=request.max_weight,
        min_weight=request.min_weight,
        risk_free_rate=request.risk_free_rate,
        covariance_method=request.covariance_method,
    )
    if custom_weights is not None:
        config = config.with_custom_weights(custom_weights)
    return config
