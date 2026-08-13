"""The simulation loop of §8.

The timing contract, restated because getting it wrong produces spectacular
fictional results:

    Weights decided for date t may use data only through t − 1 − gap_days.
    The portfolio return realized at t is R_t = w_{t−1}ᵀ r_t.

Step order inside the loop matters as much as the contract: R_t is computed
*before* drift, because the drift denominator is 1 + R_t. Computing drift first
and then taking w_driftᵀ r_t is a look-ahead error.

tests/test_backtest.py::LookAheadRegressionTests is the permanent guardrail on
both. It has been observed failing against a deliberately reordered loop.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import (
    BacktestRequest,
    NoEligibleAssets,
    optimizer_config,
)
from .optimizers import optimize

PERIOD_FREQ = {
    'monthly': 'M',
    'quarterly': 'Q',
    'semiannual': '2Q',
    'annual': 'Y',
}
WEIGHT_EPSILON = 1e-12


@dataclass
class BacktestResult:
    """§8's output. The trailing slots are filled by tasks.py, not here."""
    dates: list
    nav: np.ndarray
    index: np.ndarray
    drawdown: np.ndarray
    returns: np.ndarray
    weights_over_time: pd.DataFrame
    effective_asset_count: np.ndarray
    rebalance_events: list
    composition_events: list
    cash_flows: list
    symbols: list
    effective_start: str
    effective_end: str
    truncation_cause: str | None = None
    fallback_dates: list = field(default_factory=list)

    benchmark_index: list | None = None
    benchmark_drawdown: list | None = None
    metrics: dict | None = None
    benchmark_metrics: dict | None = None
    diagnostics: list | None = None
    frontier: dict | None = None


def schedule_dates(index: pd.DatetimeIndex, frequency: str) -> set:
    """Dates on which a period boundary is crossed, excluding the first date.

    The first date is excluded because the portfolio is seeded there -- charging
    a rebalance on the day you open the account would double-count the entry
    trade.
    """
    if frequency == 'none' or len(index) < 2:
        return set()
    if frequency not in PERIOD_FREQ:
        raise ValueError(f"Unknown frequency {frequency!r}")

    if frequency == 'semiannual':
        labels = pd.Index([(d.year, (d.month - 1) // 6) for d in index])
    else:
        labels = index.to_period(PERIOD_FREQ[frequency])

    changed = np.asarray(labels[1:]) != np.asarray(labels[:-1])
    return set(index[1:][changed])


def drawdown_series(index_values) -> np.ndarray:
    values = np.asarray(index_values, dtype=float)
    peaks = np.maximum.accumulate(values)
    with np.errstate(divide='ignore', invalid='ignore'):
        drawdown = np.where(peaks > 0, values / peaks - 1.0, 0.0)
    return np.minimum(drawdown, 0.0)


def _base_targets(request: BacktestRequest) -> np.ndarray:
    """Full-length target vector for the non-optimizer schemes."""
    n = len(request.holdings)
    if request.weighting_scheme == 'custom':
        return request.target_weights
    return np.full(n, 1.0 / n)


def _renormalized(targets: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """§5: preserve relative proportions over the available set.

    40/30/20/10 missing its 10% asset becomes 44.4/33.3/22.2 -- not something
    arbitrary. Falls back to equal weight over the mask when the masked targets
    sum to zero.
    """
    weights = np.where(mask, targets, 0.0)
    total = weights.sum()
    if total <= WEIGHT_EPSILON:
        count = int(mask.sum())
        return np.where(mask, 1.0 / count, 0.0) if count else weights
    return weights / total


def _window(returns: np.ndarray, position: int, request: BacktestRequest):
    """The trailing block a rebalance at row `position` is allowed to see.

    Ends at position − gap_days (exclusive), so the last row it contains is
    position − gap_days − 1. With the default gap_days=1 that is t − 2. This
    function is the entire reason the look-ahead guardrail can be stated as a
    property rather than checked by eye.
    """
    end = position - request.gap_days
    start = max(0, end - request.lookback_days)
    if end - start < 2:
        return None
    return returns[start:end]


def run_backtest(panel, request: BacktestRequest) -> BacktestResult:
    symbols = list(panel.prices.columns)
    n = len(symbols)
    dates = panel.prices.index
    returns_frame = panel.returns()
    returns = returns_frame.to_numpy()
    eligible_frame = panel.eligibility(request.min_history_days)

    if request.inception_policy == 'common_start':
        # Restore plain intersection behaviour: begin only when every asset is
        # eligible. The right choice for apples-to-apples comparison, but not
        # the default -- phase-in is what someone means by "ten years" (§5).
        complete = eligible_frame.all(axis=1).to_numpy()
        if not complete.any():
            raise NoEligibleAssets(
                'No date has price history for every requested asset. '
                'Try the phase-in inception policy.')
        start_position = int(np.argmax(complete))
    else:
        any_eligible = eligible_frame.any(axis=1).to_numpy()
        if not any_eligible.any():
            reasons = {
                symbol: (f"first price {panel.first_valid[symbol].date()}, "
                         f"fewer than {request.min_history_days} trading days of history")
                for symbol in symbols
            }
            raise NoEligibleAssets(
                'No requested asset has enough price history to be simulated. '
                f"Reasons: {reasons}")
        start_position = int(np.argmax(any_eligible))

    eligible = eligible_frame.to_numpy()
    sim_positions = list(range(start_position, len(dates)))
    sim_dates = dates[start_position:]

    truncation_cause = None
    if start_position > 0:
        earliest = min(symbols, key=lambda s: panel.first_valid[s])
        latest = max(symbols, key=lambda s: panel.first_valid[s])
        truncation_cause = (
            f"Started {sim_dates[0].date()} rather than {dates[0].date()}: that is "
            f"the earliest date any holding clears {request.min_history_days} "
            f"trading days of history. Earliest series is {earliest} "
            f"(first price {panel.first_valid[earliest].date()}), latest is {latest} "
            f"(first price {panel.first_valid[latest].date()}).")

    scheduled = schedule_dates(sim_dates, request.rebalance_frequency)
    contributions = (schedule_dates(sim_dates, request.contribution_frequency)
                     if request.periodic_contribution > 0 else set())
    cost_rate = request.transaction_cost_bps / 10_000.0
    base_targets = _base_targets(request)
    uses_optimizer = request.weighting_scheme not in ('equal', 'custom')

    # Fixed mode solves once per distinct eligible set and reuses the answer;
    # that is what "runs once ... and thereafter reuses those targets" means once
    # an asset can enter mid-run (§8). Walk-forward ignores this cache.
    solved_targets: dict = {}
    fallback_dates: list = []

    def compute_targets(position, mask):
        """Targets over all symbols; zero outside `mask`."""
        if not uses_optimizer:
            return _renormalized(base_targets, mask)

        key = tuple(np.flatnonzero(mask))
        if request.backtest_mode == 'fixed' and key in solved_targets:
            return _renormalized(solved_targets[key], mask)

        window = _window(returns, position, request)
        if window is None:
            return _renormalized(np.full(n, 1.0 / n), mask)

        sub_window = window[:, mask]
        config = optimizer_config(request)
        outcome = optimize(sub_window, config, request.weighting_scheme)
        if outcome.fallback_from is not None:
            fallback_dates.append(dates[position].strftime('%Y-%m-%d'))

        full = np.zeros(n)
        full[mask] = outcome.weights
        if request.backtest_mode == 'fixed':
            solved_targets[key] = full.copy()
        return full

    # --- seed -------------------------------------------------------------
    mask = eligible[start_position]
    weights = compute_targets(start_position, mask)
    held = mask & (weights > WEIGHT_EPSILON)

    # `known` tracks which symbols have ever been eligible, and is deliberately
    # separate from `held`. An optimizer assigning zero weight to an eligible
    # asset has made a decision, not deferred one -- treating that as a pending
    # entry made every zero-weight holding re-trigger a forced rebalance on every
    # subsequent date. `ever_entered` likewise keeps the composition timeline to
    # one entry per symbol rather than one per weight change.
    known = mask.copy()
    ever_entered = held.copy()

    nav_value = float(request.initial_amount)
    index_value = 1.0
    nav_series, index_series, return_series = [nav_value], [index_value], [0.0]
    weight_rows = [weights.copy()]
    rebalance_events, composition_events = [], []
    cash_flows = [(sim_dates[0], -float(request.initial_amount))]

    for symbol_position in np.flatnonzero(held):
        composition_events.append({
            'date': sim_dates[0].strftime('%Y-%m-%d'),
            'symbol': symbols[symbol_position],
            'action': 'entered',
            'reason': 'Held from the first simulated date.',
        })

    # Entries wait for the next scheduled rebalance on or after eligibility (§5).
    pending_entry: dict = {}

    # --- loop -------------------------------------------------------------
    for position in sim_positions[1:]:
        today = dates[position]
        row_returns = returns[position]

        # 1. realize yesterday's weights against today's returns
        portfolio_return = float(weights @ row_returns)

        # 2. weights drift with prices
        growth = 1.0 + portfolio_return
        if abs(growth) < 1e-12:
            drift = weights.copy()
        else:
            drift = weights * (1.0 + row_returns) / growth

        # 3/4. time-weighted index and account balance
        index_value *= growth
        nav_value *= growth

        # 5. contributions: deployed pro-rata at current weights, so NAV moves
        #    but composition does not. The one-way cost hits nav only -- index
        #    must stay free of anything driven by the deposit schedule.
        if today in contributions:
            contribution = float(request.periodic_contribution)
            nav_value += contribution
            nav_value -= contribution * cost_rate
            cash_flows.append((today, -contribution))

        # 6. rebalance triggers
        mask = eligible[position]
        exited = np.flatnonzero(held & ~mask)
        newly_eligible = np.flatnonzero(mask & ~known)

        for symbol_position in newly_eligible:
            pending_entry.setdefault(symbols[symbol_position], today)

        trigger = None
        if today in scheduled:
            trigger = 'scheduled'
        if exited.size:
            trigger = 'exit'
        if newly_eligible.size and request.enter_immediately:
            trigger = 'entry'
        if newly_eligible.size and not any(d >= today for d in scheduled):
            # Nothing is scheduled ahead, so waiting would drop the asset for
            # good. Enter now and say so in the timeline.
            trigger = trigger or 'entry'

        if trigger is not None:
            targets = compute_targets(position, mask)
            turnover = float(np.abs(targets - drift).sum())
            cost = turnover * cost_rate
            nav_value *= (1.0 - cost)
            index_value *= (1.0 - cost)
            rebalance_events.append({
                'date': today.strftime('%Y-%m-%d'),
                'turnover': turnover,
                'cost': cost,
                'trigger': trigger,
                'weights': {symbols[i]: float(targets[i])
                            for i in np.flatnonzero(targets > WEIGHT_EPSILON)},
            })

            for symbol_position in exited:
                composition_events.append({
                    'date': today.strftime('%Y-%m-%d'),
                    'symbol': symbols[symbol_position],
                    'action': 'exited',
                    'reason': (f"Price series ends "
                               f"{panel.last_valid[symbols[symbol_position]].date()}; "
                               f"liquidated and redistributed pro-rata."),
                })
            entering = np.flatnonzero(mask & (targets > WEIGHT_EPSILON) & ~ever_entered)
            for symbol_position in entering:
                symbol = symbols[symbol_position]
                became = pending_entry.pop(symbol, today)
                composition_events.append({
                    'date': today.strftime('%Y-%m-%d'),
                    'symbol': symbol,
                    'action': 'entered',
                    'reason': (f"Eligible from {became.date()}; entered at the "
                               f"{trigger} rebalance on {today.date()}."),
                })
            ever_entered = ever_entered | (targets > WEIGHT_EPSILON)

            weights = targets
        else:
            weights = drift

        known = known | mask
        held = weights > WEIGHT_EPSILON
        nav_series.append(nav_value)
        index_series.append(index_value)
        return_series.append(portfolio_return)
        weight_rows.append(weights.copy())

    cash_flows.append((sim_dates[-1], float(nav_value)))
    weights_over_time = pd.DataFrame(weight_rows, index=sim_dates, columns=symbols)
    index_values = np.asarray(index_series, dtype=float)

    return BacktestResult(
        dates=[d.strftime('%Y-%m-%d') for d in sim_dates],
        nav=np.asarray(nav_series, dtype=float),
        index=index_values,
        drawdown=drawdown_series(index_values),
        returns=np.asarray(return_series, dtype=float),
        weights_over_time=weights_over_time,
        effective_asset_count=(weights_over_time > WEIGHT_EPSILON).sum(axis=1).to_numpy(),
        rebalance_events=rebalance_events,
        composition_events=composition_events,
        cash_flows=[(d.strftime('%Y-%m-%d'), amount) for d, amount in cash_flows],
        symbols=symbols,
        effective_start=sim_dates[0].strftime('%Y-%m-%d'),
        effective_end=sim_dates[-1].strftime('%Y-%m-%d'),
        truncation_cause=truncation_cause,
        fallback_dates=fallback_dates,
    )
