/**
 * Option lists and the request payload shape, in one place.
 *
 * The values must match backend/backtester/engine/config.py exactly — a typo
 * here surfaces as a 422 with no clue which control caused it.
 */
export const WEIGHTING_OPTIONS = [
  { value: 'equal', label: 'Equal weight', hint: 'Same amount in each holding.' },
  { value: 'custom', label: 'My own weights', hint: 'You set the percentages.' },
  {
    value: 'inverse_vol',
    label: 'Inverse volatility',
    hint: 'More in the steadier holdings.',
  },
  {
    value: 'min_variance',
    label: 'Minimum variance',
    hint: 'The mix that would have swung the least.',
  },
  {
    value: 'risk_parity',
    label: 'Risk parity',
    hint: 'Every holding contributes the same share of risk.',
  },
  {
    value: 'max_sharpe',
    label: 'Maximum Sharpe',
    hint: 'Best past return per unit of risk. Very sensitive to the window.',
  },
]

export const REBALANCE_OPTIONS = [
  { value: 'none', label: 'Never' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'quarterly', label: 'Quarterly' },
  { value: 'semiannual', label: 'Every 6 months' },
  { value: 'annual', label: 'Annually' },
]

export const CONTRIBUTION_OPTIONS = [
  { value: 'none', label: 'No regular deposits' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'quarterly', label: 'Quarterly' },
  { value: 'annual', label: 'Annually' },
]

export const PERIOD_OPTIONS = [
  { value: 0, label: 'As far back as the data goes' },
  { value: 3, label: '3 years' },
  { value: 5, label: '5 years' },
  { value: 10, label: '10 years' },
  { value: 20, label: '20 years' },
]

export const COVARIANCE_OPTIONS = [
  {
    value: 'ledoit_wolf',
    label: 'Shrinkage (recommended)',
    hint: 'More stable when you hold many things over a short window.',
  },
  { value: 'sample', label: 'Plain sample', hint: 'Textbook estimate. Noisier.' },
]

export const INCEPTION_OPTIONS = [
  {
    value: 'phase_in',
    label: 'Phase holdings in as they list',
    hint: 'Keeps the full period. Holdings join when their price history starts.',
  },
  {
    value: 'common_start',
    label: 'Start only when every holding exists',
    hint: 'Shorter, but a clean like-for-like window.',
  },
]

export const BACKTEST_MODE_OPTIONS = [
  {
    value: 'fixed',
    label: 'Pick weights once',
    hint: 'Chosen at the start and held.',
  },
  {
    value: 'walk_forward',
    label: 'Re-optimize at each rebalance',
    hint: 'Only uses data available at the time. Slower, more honest.',
  },
]

export const DEFAULT_SETTINGS = {
  benchmarkSymbol: 'SPY',
  periodYears: 10,
  weightingScheme: 'equal',
  backtestMode: 'fixed',
  rebalanceFrequency: 'annual',
  initialAmount: 10000,
  periodicContribution: 0,
  contributionFrequency: 'none',
  // advanced
  lookbackDays: 252,
  gapDays: 1,
  covarianceMethod: 'ledoit_wolf',
  transactionCostBps: 10,
  longOnly: true,
  maxWeight: '',
  minWeight: '',
  riskFreeRate: 0,
  inceptionPolicy: 'phase_in',
  enterImmediately: false,
}

const optionalNumber = (value) => {
  if (value === '' || value === null || value === undefined) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/** Turn the UI state into the exact payload POST /run/ validates. */
export const buildRequestPayload = (holdings, settings, portfolioId = null) => {
  const startDate =
    settings.periodYears > 0
      ? new Date(new Date().setFullYear(new Date().getFullYear() - Number(settings.periodYears)))
          .toISOString()
          .slice(0, 10)
      : null

  return {
    holdings: holdings.map((holding, index) => ({
      symbol: holding.symbol,
      // Sent as a fraction; the builder collects percentages.
      target_weight: Number(holding.weight || 0) / 100,
      order: index,
    })),
    benchmark_symbol: settings.benchmarkSymbol || 'SPY',
    start_date: startDate,
    end_date: null,
    initial_amount: Number(settings.initialAmount) || 10000,
    periodic_contribution: Number(settings.periodicContribution) || 0,
    contribution_frequency: settings.contributionFrequency,
    weighting_scheme: settings.weightingScheme,
    backtest_mode: settings.backtestMode,
    rebalance_frequency: settings.rebalanceFrequency,
    lookback_days: Number(settings.lookbackDays) || 252,
    gap_days: Number(settings.gapDays) || 0,
    covariance_method: settings.covarianceMethod,
    transaction_cost_bps: Number(settings.transactionCostBps) || 0,
    long_only: Boolean(settings.longOnly),
    max_weight: optionalNumber(settings.maxWeight),
    min_weight: optionalNumber(settings.minWeight),
    risk_free_rate: Number(settings.riskFreeRate) || 0,
    inception_policy: settings.inceptionPolicy,
    enter_immediately: Boolean(settings.enterImmediately),
    portfolio_id: portfolioId,
  }
}
