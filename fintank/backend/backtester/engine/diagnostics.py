"""The seven-sins reality check of §10.

Plain language, no jargon without a gloss. Severity drives presentation:
`critical` findings render above the results, not below them.

Storytelling bias (sin #3) is not machine-detectable and is addressed in static
UI copy accompanying the panel rather than here.
"""
from __future__ import annotations

import numpy as np

CODES = (
    'survivorship_bias', 'history_truncation', 'composition_coverage',
    'single_asset_period', 'in_sample_fit', 'return_estimation', 'short_sample',
    'cost_sensitivity', 'outlier_dependence', 'concentration',
    'shorting_unmodelled', 'optimizer_fallback', 'benchmark_mismatch',
)
SEVERITY_ORDER = {'critical': 0, 'warning': 1, 'info': 2}

OPTIMIZER_SCHEMES = ('inverse_vol', 'min_variance', 'risk_parity', 'max_sharpe')
TRADING_DAYS = 252

# Thresholds, named so the reason each one exists is readable.
COVERAGE_SHARE_THRESHOLD = 0.25        # of the period
SINGLE_ASSET_MIN_DAYS = 30
SHORT_SAMPLE_YEARS = 3.0
SHORT_SAMPLE_REBALANCES = 60
COST_SHARE_OF_GROSS = 0.15
OUTLIER_CAGR_DROP = 0.50
MAX_SINGLE_WEIGHT = 0.40
MIN_EFFECTIVE_N = 3.0
BENCHMARK_MIN_CORRELATION = 0.30


def _longest_run(mask) -> int:
    longest = current = 0
    for flag in np.asarray(mask, dtype=bool):
        current = current + 1 if flag else 0
        longest = max(longest, current)
    return longest


def build_diagnostics(result, request, metrics, benchmark_returns=None) -> list:
    findings = []

    def add(code, severity, title, detail):
        findings.append({'code': code, 'severity': severity,
                         'title': title, 'detail': detail})

    # --- Sin #1: survivorship. Always. --------------------------------------
    add('survivorship_bias', 'warning',
        'These results are optimistic by construction',
        'The universe behind this simulation is built from the companies that are '
        'in the major indexes *today*. Firms that went bankrupt or were taken '
        'private are simply absent from the data, so the historical returns you '
        'see are better than what an investor could actually have earned. There is '
        'no way to correct for this with the data available; treat every return '
        'below as an upper bound.')

    if result.truncation_cause:
        add('history_truncation', 'warning',
            'The simulation is shorter than you asked for',
            result.truncation_cause)

    # --- Coverage of the requested basket ----------------------------------
    counts = np.asarray(result.effective_asset_count, dtype=float)
    requested = len(request.holdings)
    if requested > 1 and counts.size:
        thin = counts < (requested / 2.0)
        share = float(thin.mean())
        if share > COVERAGE_SHARE_THRESHOLD:
            dominant = (result.weights_over_time.loc[thin]
                        .mean(axis=0).sort_values(ascending=False))
            names = ', '.join(dominant.index[:2])
            add('composition_coverage', 'critical',
                'For much of this period you did not own the portfolio you built',
                f"For {share * 100:.0f}% of the simulated period the portfolio held "
                f"fewer than half of your {requested} holdings, because the others "
                f"had no price history yet. That span was dominated by {names}. A "
                f"headline return over this window is mostly a statement about "
                f"those assets, not about the basket you assembled.")

        if _longest_run(counts <= 1) > SINGLE_ASSET_MIN_DAYS:
            add('single_asset_period', 'critical',
                'The portfolio was a single holding for an extended stretch',
                f"There is a run of more than {SINGLE_ASSET_MIN_DAYS} trading days "
                f"in which only one of your holdings had price data. Over that "
                f"span this is a single-stock backtest, with none of the "
                f"diversification the rest of the basket is meant to provide.")

    # --- Sin #4: overfitting ----------------------------------------------
    uses_optimizer = request.weighting_scheme in OPTIMIZER_SCHEMES
    if uses_optimizer and request.backtest_mode == 'fixed':
        add('in_sample_fit', 'warning',
            'The weights were chosen using the same data they are scored against',
            f"You ran the {request.weighting_scheme.replace('_', ' ')} optimizer in "
            f"fixed mode, so it saw the whole history before the simulation graded "
            f"it. That is not a result an investor could have achieved, because "
            f"nobody had that history in advance. Re-run in walk-forward mode to "
            f"see what the same rule would have produced using only data available "
            f"at each decision date.")

    if request.weighting_scheme == 'max_sharpe':
        add('return_estimation', 'warning',
            'Maximum Sharpe rests on a very noisy forecast',
            "This optimizer needs an estimate of each asset's future return, and "
            'the only one available is the average return over the lookback window. '
            'Past average returns are a famously poor predictor of future ones - far '
            'worse than past volatility is of future volatility. Expect these '
            'weights to look confident and to travel badly.')

    rebalance_count = len(result.rebalance_events)
    years = float(metrics.get('years') or 0.0)
    if years < SHORT_SAMPLE_YEARS or rebalance_count < SHORT_SAMPLE_REBALANCES:
        add('short_sample', 'warning',
            'There is not much evidence here',
            f"This simulation covers {years:.1f} years and {rebalance_count} "
            f"rebalances. With that few independent decisions, the difference "
            f"between this result and a different one is mostly luck. Treat the "
            f"ranking against alternatives as provisional.")

    # --- Sin #5: transaction costs ----------------------------------------
    cost_fractions = [event['cost'] for event in result.rebalance_events]
    index_values = np.asarray(result.index, dtype=float)
    net_return = (float(index_values[-1] / index_values[0] - 1.0)
                  if index_values.size else 0.0)
    surviving = float(np.prod([1.0 - c for c in cost_fractions])) if cost_fractions else 1.0
    gross_return = ((1.0 + net_return) / surviving - 1.0) if surviving > 0 else net_return
    cost_drag = gross_return - net_return
    if gross_return > 1e-9 and cost_drag / gross_return > COST_SHARE_OF_GROSS:
        add('cost_sensitivity', 'critical',
            'Trading costs consumed a large share of the gains',
            f"Rebalancing cost {cost_drag / gross_return * 100:.0f}% of this "
            f"strategy's gross return at {request.transaction_cost_bps:.0f} basis "
            f"points per trade. A strategy this trade-heavy is fragile: a slightly "
            f"worse fill or a wider spread than assumed would erase much of the "
            f"advantage. Try a less frequent rebalance.")

    # --- Sin #6: outliers -------------------------------------------------
    returns = np.asarray(result.returns, dtype=float)[1:]
    if returns.size > 20 and years > 0:
        full_growth = float(np.prod(1.0 + returns))
        trimmed = np.sort(returns)[:-5]
        trimmed_growth = float(np.prod(1.0 + trimmed))
        if full_growth > 0 and trimmed_growth > 0:
            full_cagr = full_growth ** (1 / years) - 1
            trimmed_cagr = trimmed_growth ** (1 / years) - 1
            if full_cagr > 1e-9 and (full_cagr - trimmed_cagr) / full_cagr > OUTLIER_CAGR_DROP:
                add('outlier_dependence', 'warning',
                    'Almost all of the return came from a handful of days',
                    f"Remove the five best days and the annual return falls from "
                    f"{full_cagr * 100:.1f}% to {trimmed_cagr * 100:.1f}%. A result "
                    f"that hinges on five days out of {returns.size} is not evidence "
                    f"of a durable edge - it is evidence that you would have had to "
                    f"be invested on exactly the right days.")

    # --- Concentration ----------------------------------------------------
    average_weights = result.weights_over_time.mean(axis=0).to_numpy()
    squared = float(np.sum(average_weights ** 2))
    effective_n = (1.0 / squared) if squared > 0 else 0.0
    largest = float(average_weights.max()) if average_weights.size else 0.0
    if largest > MAX_SINGLE_WEIGHT or effective_n < MIN_EFFECTIVE_N:
        heaviest = result.weights_over_time.mean(axis=0).idxmax()
        add('concentration', 'warning',
            'This portfolio is less diversified than the holding count suggests',
            f"The largest average position is {heaviest} at {largest * 100:.0f}%, and "
            f"the portfolio behaves like roughly {effective_n:.1f} independent "
            f"holdings. Whatever happens to the largest position will dominate the "
            f"result regardless of how many tickers are listed.")

    # --- Sin #7: shorting -------------------------------------------------
    if not request.long_only:
        add('shorting_unmodelled', 'critical',
            'Short positions here are free, and in reality they are not',
            'You disabled the long-only constraint, so the optimizer may hold '
            'negative weights. This simulation charges nothing for them: no stock '
            'borrow fee, no hard-to-borrow premium, no risk of a recall forcing you '
            'to close at the worst moment, and no margin requirement. Real short '
            'books pay all four. Any advantage the short positions appear to add '
            'is overstated by an unknown amount.')

    if result.fallback_dates:
        shown = ', '.join(result.fallback_dates[:5])
        more = ('' if len(result.fallback_dates) <= 5
                else f" and {len(result.fallback_dates) - 5} more")
        add('optimizer_fallback', 'critical',
            'The optimizer failed on some dates and a different rule was used',
            f"On {len(result.fallback_dates)} rebalance date(s) - {shown}{more} - the "
            f"{request.weighting_scheme.replace('_', ' ')} solver did not converge, "
            f"so those rebalances used inverse-volatility weights instead. The "
            f"result below is therefore a blend of two strategies, not the one you "
            f"selected.")

    # --- Benchmark suitability -------------------------------------------
    if benchmark_returns is not None:
        benchmark = np.asarray(benchmark_returns, dtype=float)
        length = min(benchmark.size, returns.size + 1)
        if length > 30:
            portfolio_tail = np.asarray(result.returns, dtype=float)[-length:]
            benchmark_tail = benchmark[-length:]
            if portfolio_tail.std() > 0 and benchmark_tail.std() > 0:
                correlation = float(np.corrcoef(portfolio_tail, benchmark_tail)[0, 1])
                if correlation < BENCHMARK_MIN_CORRELATION:
                    add('benchmark_mismatch', 'info',
                        f"{request.benchmark_symbol} may be the wrong yardstick",
                        f"Your portfolio's daily moves correlate only "
                        f"{correlation:.2f} with {request.benchmark_symbol}. They are "
                        f"not really exposed to the same things, so beating the "
                        f"benchmark says little here. A benchmark matching your "
                        f"holdings' asset class and region would be more informative.")

    findings.sort(key=lambda finding: SEVERITY_ORDER[finding['severity']])
    return findings
