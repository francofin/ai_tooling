/**
 * Field catalogue and formatting for the financial statement parquets, shared
 * by the statements table and the statements chart.
 */

// Every field the statement parquets carry, grouped and in statement order.
// `symbol`, `date` and `period` are the page and the column headers; the
// backend already drops cik, accepted_date and the filing links.
export const SECTIONS = {
  income_statements: [
    ['Revenue', [
      ['revenue', 'Revenue'],
      ['cost_of_revenue', 'Cost of Revenue'],
      ['gross_profit', 'Gross Profit'],
      ['gross_profit_ratio', 'Gross Margin'],
    ]],
    ['Operating Expenses', [
      ['research_and_development_expenses', 'Research & Development'],
      ['general_and_administrative_expenses', 'General & Administrative'],
      ['selling_and_marketing_expenses', 'Selling & Marketing'],
      ['selling_general_and_administrative_expenses', 'SG&A'],
      ['other_expenses', 'Other Expenses'],
      ['operating_expenses', 'Operating Expenses'],
      ['cost_and_expenses', 'Cost & Expenses'],
    ]],
    ['Operating Results', [
      ['interest_income', 'Interest Income'],
      ['interest_expense', 'Interest Expense'],
      ['depreciation_and_amortization', 'Depreciation & Amortization'],
      ['ebitda', 'EBITDA'],
      ['ebitda_ratio', 'EBITDA Margin'],
      ['operating_income', 'Operating Income'],
      ['operating_income_ratio', 'Operating Margin'],
    ]],
    ['Earnings', [
      ['total_other_income_expenses_net', 'Other Income / Expenses (net)'],
      ['income_before_tax', 'Income Before Tax'],
      ['income_before_tax_ratio', 'Pre-Tax Margin'],
      ['income_tax_expense', 'Income Tax Expense'],
      ['net_income', 'Net Income'],
      ['net_income_ratio', 'Net Margin'],
    ]],
    ['Per Share', [
      ['eps', 'EPS'],
      ['eps_diluted', 'EPS (diluted)'],
      ['weighted_average_shares_out', 'Weighted Avg. Shares'],
      ['weighted_average_shares_out_diluted', 'Weighted Avg. Shares (diluted)'],
    ]],
  ],
  balance_sheet_statements: [
    ['Current Assets', [
      ['cash_and_cash_equivalents', 'Cash & Equivalents'],
      ['short_term_investments', 'Short-Term Investments'],
      ['cash_and_short_term_investments', 'Cash & Short-Term Investments'],
      ['net_receivables', 'Net Receivables'],
      ['inventory', 'Inventory'],
      ['other_current_assets', 'Other Current Assets'],
      ['total_current_assets', 'Total Current Assets'],
    ]],
    ['Non-Current Assets', [
      ['property_plant_equipment_net', 'PP&E (net)'],
      ['goodwill', 'Goodwill'],
      ['intangible_assets', 'Intangible Assets'],
      ['goodwill_and_intangible_assets', 'Goodwill & Intangibles'],
      ['long_term_investments', 'Long-Term Investments'],
      ['tax_assets', 'Tax Assets'],
      ['other_non_current_assets', 'Other Non-Current Assets'],
      ['total_non_current_assets', 'Total Non-Current Assets'],
      ['other_assets', 'Other Assets'],
      ['total_assets', 'Total Assets'],
    ]],
    ['Current Liabilities', [
      ['account_payables', 'Accounts Payable'],
      ['short_term_debt', 'Short-Term Debt'],
      ['tax_payables', 'Tax Payables'],
      ['deferred_revenue', 'Deferred Revenue'],
      ['other_current_liabilities', 'Other Current Liabilities'],
      ['total_current_liabilities', 'Total Current Liabilities'],
    ]],
    ['Non-Current Liabilities', [
      ['long_term_debt', 'Long-Term Debt'],
      ['deferred_revenue_non_current', 'Deferred Revenue (non-current)'],
      ['deferred_tax_liabilities_non_current', 'Deferred Tax Liabilities'],
      ['other_non_current_liabilities', 'Other Non-Current Liabilities'],
      ['total_non_current_liabilities', 'Total Non-Current Liabilities'],
      ['other_liabilities', 'Other Liabilities'],
      ['capital_lease_obligations', 'Capital Lease Obligations'],
      ['total_liabilities', 'Total Liabilities'],
    ]],
    ['Equity', [
      ['preferred_stock', 'Preferred Stock'],
      ['common_stock', 'Common Stock'],
      ['retained_earnings', 'Retained Earnings'],
      ['accumulated_other_comprehensive_income_loss', 'Accumulated OCI'],
      ['other_total_stockholders_equity', 'Other Stockholders\' Equity'],
      ['total_stockholders_equity', 'Total Stockholders\' Equity'],
      ['minority_interest', 'Minority Interest'],
      ['total_equity', 'Total Equity'],
    ]],
    ['Totals', [
      ['total_liabilities_and_stockholders_equity', 'Total Liabilities & Stockholders\' Equity'],
      ['total_liabilities_and_total_equity', 'Total Liabilities & Total Equity'],
      ['total_investments', 'Total Investments'],
      ['total_debt', 'Total Debt'],
      ['net_debt', 'Net Debt'],
    ]],
  ],
  cash_flow_statements: [
    ['Operating Activities', [
      ['net_income', 'Net Income'],
      ['depreciation_and_amortization', 'Depreciation & Amortization'],
      ['deferred_income_tax', 'Deferred Income Tax'],
      ['stock_based_compensation', 'Stock-Based Compensation'],
      ['change_in_working_capital', 'Change in Working Capital'],
      ['accounts_receivables', 'Accounts Receivable'],
      ['inventory', 'Inventory'],
      ['accounts_payables', 'Accounts Payable'],
      ['other_working_capital', 'Other Working Capital'],
      ['other_non_cash_items', 'Other Non-Cash Items'],
      ['net_cash_from_operating_activities', 'Net Cash from Operating Activities'],
    ]],
    ['Investing Activities', [
      ['investments_in_property_plant_and_equipment', 'Investments in PP&E'],
      ['acquisitions_net', 'Acquisitions (net)'],
      ['purchases_of_investments', 'Purchases of Investments'],
      ['sales_maturities_of_investments', 'Sales / Maturities of Investments'],
      ['other_investing_activities', 'Other Investing Activities'],
      ['net_cash_used_for_investing_activities', 'Net Cash from Investing Activities'],
    ]],
    ['Financing Activities', [
      ['debt_repayment', 'Debt Repayment'],
      ['common_stock_issued', 'Common Stock Issued'],
      ['common_stock_repurchased', 'Common Stock Repurchased'],
      ['dividends_paid', 'Dividends Paid'],
      ['other_financing_activities', 'Other Financing Activities'],
      ['net_cash_from_financing_activities', 'Net Cash from Financing Activities'],
    ]],
    ['Cash Position', [
      ['effect_of_forex_changes_on_cash', 'Effect of FX on Cash'],
      ['net_change_in_cash', 'Net Change in Cash'],
      ['cash_at_beginning_of_period', 'Cash at Beginning of Period'],
      ['cash_at_end_of_period', 'Cash at End of Period'],
    ]],
    ['Free Cash Flow', [
      ['operating_cash_flow', 'Operating Cash Flow'],
      ['capital_expenditure', 'Capital Expenditure'],
      ['free_cash_flow', 'Free Cash Flow'],
    ]],
  ],
};

const TEXT_KEYS = new Set(['reported_currency', 'filing_date', 'calendar_year']);
export const PER_SHARE_KEYS = new Set(['eps', 'eps_diluted']);

export const humanise = (key) =>
  key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

export const scaled = (value) => {
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${(value / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  return Intl.NumberFormat().format(value);
};

export const formatValue = (value, key) => {
  if (value === null || value === undefined || value === '') return '—';
  if (TEXT_KEYS.has(key)) return String(value);
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  // Ratios are stored as fractions: 0.4718 is a 47.18% margin.
  if (key.endsWith('_ratio')) return `${(number * 100).toFixed(2)}%`;
  if (PER_SHARE_KEYS.has(key)) return number.toFixed(2);
  return scaled(number);
};

const SHARE_COUNT_KEYS = new Set(['weighted_average_shares_out', 'weighted_average_shares_out_diluted']);

// What a field measures, so values of one kind share an axis and kinds never mix.
export const unitOf = (key) => {
  if (key.endsWith('_ratio')) return 'percent';
  if (PER_SHARE_KEYS.has(key)) return 'perShare';
  if (SHARE_COUNT_KEYS.has(key)) return 'shares';
  return 'amount';
};
