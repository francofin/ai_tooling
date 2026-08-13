"""Performance measures of §9.

Everything risk- or return-shaped is computed from the time-weighted `index`
series. Only balances come from `nav`. With periodic contributions, a CAGR taken
off `nav` conflates investment skill with the deposit schedule, and a drawdown
taken off `nav` lets a well-timed deposit paper over a real loss.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import drawdown_series
from .covariance import estimate_covariance
from .optimizers import relative_risk_contribution

TRADING_DAYS = 252


def _finite(value):
    """JSON-safe scalar: NaN and ±inf become None, numpy scalars become floats."""
    if value is None:
        return None
    value = float(value)
    if value != value or value in (float('inf'), float('-inf')):
        return None
    return value


def drawdown_detail(index_values, dates) -> dict:
    values = np.asarray(index_values, dtype=float)
    drawdown = drawdown_series(values)
    trough = int(np.argmin(drawdown))
    if drawdown[trough] >= -1e-15:
        return {'max_drawdown': 0.0, 'peak_date': None, 'trough_date': None,
                'recovery_date': None}

    peak = int(np.argmax(values[:trough + 1]))
    recovery = None
    after = np.flatnonzero(values[trough:] >= values[peak])
    if after.size:
        recovery = dates[trough + int(after[0])]

    return {
        'max_drawdown': _finite(drawdown[trough]),
        'peak_date': dates[peak],
        'trough_date': dates[trough],
        'recovery_date': recovery,
    }


def calendar_year_returns(index_values, dates) -> dict:
    series = pd.Series(np.asarray(index_values, dtype=float),
                       index=pd.to_datetime(list(dates)))
    years = {}
    for year, block in series.groupby(series.index.year):
        years[str(year)] = _finite(block.iloc[-1] / block.iloc[0] - 1.0)
    return years


def beta_alpha(portfolio_returns, benchmark_returns, risk_free_rate=0.0):
    """OLS of portfolio excess returns on benchmark excess returns. Alpha is
    annualized; beta is unitless."""
    portfolio = np.asarray(portfolio_returns, dtype=float)
    benchmark = np.asarray(benchmark_returns, dtype=float)
    length = min(portfolio.size, benchmark.size)
    if length < 3:
        return None, None
    daily_rf = float(risk_free_rate) / TRADING_DAYS
    x = benchmark[-length:] - daily_rf
    y = portfolio[-length:] - daily_rf

    variance = float(np.var(x, ddof=1))
    if variance <= 0:
        return None, None
    beta = float(np.cov(y, x, ddof=1)[0, 1] / variance)
    alpha = float(y.mean() - beta * x.mean()) * TRADING_DAYS
    return _finite(beta), _finite(alpha)


def capture_ratios(portfolio_returns, benchmark_returns):
    portfolio = np.asarray(portfolio_returns, dtype=float)
    benchmark = np.asarray(benchmark_returns, dtype=float)
    length = min(portfolio.size, benchmark.size)
    portfolio, benchmark = portfolio[-length:], benchmark[-length:]

    def capture(mask):
        if not mask.any():
            return None
        denominator = float(benchmark[mask].mean())
        if abs(denominator) < 1e-15:
            return None
        return _finite(float(portfolio[mask].mean()) / denominator)

    return capture(benchmark > 0), capture(benchmark < 0)


def contribution_to_return(weights_over_time, returns_frame) -> dict:
    """w̄_i · r̄_i per asset, normalized to sum to 1."""
    shared = [c for c in weights_over_time.columns if c in returns_frame.columns]
    weights = weights_over_time[shared]
    returns = returns_frame.reindex(weights.index)[shared]

    products = (weights * returns).sum(axis=0)
    total = float(products.sum())
    if abs(total) < 1e-18:
        return {symbol: 0.0 for symbol in shared}
    return {symbol: _finite(products[symbol] / total) for symbol in shared}


def contribution_to_risk(weights, cov, symbols) -> dict:
    """wᵢ(Σw)ᵢ / (wᵀΣw) per asset. Shares the definition with the risk-parity
    objective -- see optimizers.relative_risk_contribution."""
    shares = relative_risk_contribution(np.asarray(weights, dtype=float),
                                        np.asarray(cov, dtype=float))
    return {symbol: _finite(share) for symbol, share in zip(symbols, shares)}


def correlation_matrix(returns_frame) -> dict:
    matrix = returns_frame.corr()
    return {
        'symbols': list(matrix.columns),
        'values': [[_finite(v) for v in row] for row in matrix.to_numpy()],
    }


def money_weighted_return(cash_flows) -> float | None:
    """XIRR by bisection on the dated cash-flow vector.

    Bisection rather than Newton: the NPV function is monotone in the discount
    rate for a conventional flow schedule, and bisection cannot diverge the way
    Newton does when the initial guess sits near a flat region.
    """
    flows = [(pd.Timestamp(d), float(a)) for d, a in cash_flows]
    if len(flows) < 2:
        return None
    amounts = [a for _, a in flows]
    if not (any(a > 0 for a in amounts) and any(a < 0 for a in amounts)):
        return None

    start = min(d for d, _ in flows)
    years = np.array([(d - start).days / 365.0 for d, _ in flows])
    values = np.array(amounts)

    def npv(rate):
        return float(np.sum(values / (1.0 + rate) ** years))

    low, high = -0.9999, 10.0
    if npv(low) * npv(high) > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2.0
        if npv(low) * npv(mid) <= 0:
            high = mid
        else:
            low = mid
    return _finite((low + high) / 2.0)


def compute_metrics(result, request, returns_frame=None,
                    benchmark_returns=None) -> dict:
    """The §9 table for one wealth series, as a flat JSON-safe dict."""
    index_values = np.asarray(result.index, dtype=float)
    # Drop the seeding row: its return is 0 by construction and would bias every
    # mean and standard deviation downward.
    period_returns = np.asarray(result.returns, dtype=float)[1:]
    observations = period_returns.size
    years = len(result.dates) / TRADING_DAYS
    daily_rf = float(request.risk_free_rate) / TRADING_DAYS

    volatility = float(np.std(period_returns, ddof=1)) if observations > 1 else 0.0
    mean_return = float(period_returns.mean()) if observations else 0.0

    cagr = ((index_values[-1] / index_values[0]) ** (1 / years) - 1.0
            if years > 0 and index_values[0] > 0 else None)
    sharpe = ((mean_return - daily_rf) / volatility * np.sqrt(TRADING_DAYS)
              if volatility > 0 else None)

    downside = period_returns[period_returns < daily_rf] - daily_rf
    downside_deviation = float(np.sqrt(np.mean(downside ** 2))) if downside.size else 0.0
    sortino = ((mean_return - daily_rf) / downside_deviation * np.sqrt(TRADING_DAYS)
               if downside_deviation > 0 else None)

    drawdown = drawdown_detail(index_values, result.dates)
    calmar = (cagr / abs(drawdown['max_drawdown'])
              if cagr is not None and drawdown['max_drawdown'] else None)

    var_95 = float(np.percentile(period_returns, 5)) if observations else None
    tail = period_returns[period_returns <= var_95] if observations else np.array([])
    cvar_95 = float(tail.mean()) if tail.size else var_95

    years_map = calendar_year_returns(index_values, result.dates)
    complete_years = {k: v for k, v in years_map.items() if v is not None}

    total_turnover = sum(event['turnover'] for event in result.rebalance_events)
    total_cost_fraction = sum(event['cost'] for event in result.rebalance_events)
    contributed = float(request.initial_amount) + sum(
        -amount for _, amount in result.cash_flows[1:-1])

    beta = alpha = up_capture = down_capture = None
    if benchmark_returns is not None:
        benchmark_periods = np.asarray(benchmark_returns, dtype=float)[1:]
        beta, alpha = beta_alpha(period_returns, benchmark_periods,
                                 request.risk_free_rate)
        up_capture, down_capture = capture_ratios(period_returns, benchmark_periods)

    correlations = {'symbols': [], 'values': []}
    to_return, to_risk = {}, {}
    if returns_frame is not None and not returns_frame.empty:
        window = returns_frame.loc[returns_frame.index.astype(str).isin(result.dates)]
        correlations = correlation_matrix(window)
        to_return = contribution_to_return(result.weights_over_time, returns_frame)
        final_weights = result.weights_over_time.iloc[-1].to_numpy()
        if window.shape[0] > 2:
            cov = estimate_covariance(window.to_numpy(), request.covariance_method)
            to_risk = contribution_to_risk(final_weights, cov, list(window.columns))

    return {
        'years': _finite(years),
        'observations': int(observations),
        'cagr': _finite(cagr),
        'annualized_return': _finite(mean_return * TRADING_DAYS),
        'annualized_volatility': _finite(volatility * np.sqrt(TRADING_DAYS)),
        'sharpe': _finite(sharpe),
        'sortino': _finite(sortino),
        'max_drawdown': drawdown['max_drawdown'],
        'max_drawdown_peak_date': drawdown['peak_date'],
        'max_drawdown_trough_date': drawdown['trough_date'],
        'max_drawdown_recovery_date': drawdown['recovery_date'],
        'calmar': _finite(calmar),
        'var_95': _finite(var_95),
        'cvar_95': _finite(cvar_95),
        'calendar_year_returns': years_map,
        'best_year': max(complete_years, key=complete_years.get) if complete_years else None,
        'best_year_return': max(complete_years.values()) if complete_years else None,
        'worst_year': min(complete_years, key=complete_years.get) if complete_years else None,
        'worst_year_return': min(complete_years.values()) if complete_years else None,
        'beta': beta,
        'alpha': alpha,
        'up_capture': up_capture,
        'down_capture': down_capture,
        'annual_turnover': _finite(total_turnover / years) if years > 0 else None,
        'total_costs_paid': _finite(total_cost_fraction * float(request.initial_amount)),
        'total_costs_annualized_bps': (_finite(total_cost_fraction / years * 10_000)
                                       if years > 0 else None),
        'correlation_matrix': correlations,
        'contribution_to_return': to_return,
        'contribution_to_risk': to_risk,
        'ending_balance': _finite(result.nav[-1]),
        'total_contributed': _finite(contributed),
        'total_gain': _finite(float(result.nav[-1]) - contributed),
        'money_weighted_return': money_weighted_return(result.cash_flows),
    }
