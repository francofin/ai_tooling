from django.db import models
from django.conf import settings


# Create your models here.
class Stock(models.Model):
    symbol = models.CharField(max_length=300, db_index=True)
    name = models.CharField(max_length=300, default="")
    currency = models.CharField(max_length=30, default="")
    isin = models.CharField(max_length=30, default="")
    cusip = models.CharField(max_length=30, default="")
    exchange = models.CharField(max_length=200, null=True, blank=True, default=None)
    exchange_short_name = models.CharField(max_length=40, null=True, blank=True, default=None)
    industry = models.CharField(max_length=200, null=True, blank=True, default=None)
    sector = models.CharField(max_length=200, null=True, blank=True, default=None)
    country = models.CharField(max_length=20, null=True, blank=True, default=None)
    no_of_employees = models.CharField(max_length=20, null=True, blank=True, default=None)
    description = models.TextField(null=True, blank=True, default=None)
    is_etf = models.BooleanField(default=False, null=True)
    owner_count = models.BigIntegerField(null=True, blank=True)

    def __str__(self):
        return self.symbol

    
class ProfileStock(models.Model):
    stock = models.ForeignKey(Stock, on_delete=models.SET_NULL, null=True, default=None)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    date_added = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.stock.symbol if self.stock else f"ProfileStock({self.pk})"

class ETF(models.Model):
    symbol = models.CharField(max_length=300, db_index=True)
    name = models.CharField(max_length=300)
    exchange = models.CharField(max_length=300, default="", null=True)
    exchange_short = models.CharField(max_length=300, default="", null=True)
    def __str__(self):
        return self.symbol
    
class Crypto(models.Model):
    symbol = models.CharField(max_length = 200, db_index=True)
    symbol_clean = models.CharField(max_length=200, db_index=True)
    name = models.CharField(max_length=300, null=True, blank=True)
    exchange = models.CharField(max_length=300, default="", null=True)
    def __str__(self):
        return self.symbol
    
class IncomeStatement(models.Model):
    date = models.DateTimeField(auto_now_add=False, null=True, db_index=True)
    symbol = models.CharField(max_length=300, db_index=True)
    currency = models.CharField(max_length=300)
    cik = models.CharField(max_length=300, null=True)
    calendar_year = models.CharField(max_length=300, null=True, db_index=True)
    period = models.CharField(max_length=300, null=True, db_index=True)
    revenue=models.BigIntegerField(default=0, blank=True, null=True)
    cost_of_revenue = models.BigIntegerField(default=0, blank=True, null=True)
    gross_profit = models.BigIntegerField(null=True, blank=True)
    gross_profit_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    research_and_development_expenses = models.BigIntegerField(null=True, blank=True)
    general_and_administrative_expenses = models.BigIntegerField(null=True, blank=True)
    selling_and_marketing_expenses = models.BigIntegerField(null=True, blank=True)
    selling_general_and_admin_expenses = models.BigIntegerField(null=True, blank=True)
    other_expenses = models.BigIntegerField(null=True, blank=True)
    operating_expenses = models.BigIntegerField(null=True, blank=True)
    cost_and_expenses = models.BigIntegerField(null=True, blank=True)
    interest_income = models.BigIntegerField(null=True, blank=True)
    interest_expense = models.BigIntegerField(null=True, blank=True)
    depreciation_and_amortization = models.BigIntegerField(null=True, blank=True)
    ebitda = models.BigIntegerField(null=True, blank=True)
    ebitda_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    operating_income = models.BigIntegerField(null=True, blank=True)
    operating_income_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    total_other_income_expense = models.BigIntegerField(null=True, blank=True)
    income_before_tax = models.BigIntegerField(null=True, blank=True)
    income_before_tax_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    income_tax_expense = models.BigIntegerField(null=True, blank=True)
    net_income = models.BigIntegerField(null=True, blank=True)
    net_income_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    eps = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    epsdiluted = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    weighted_average_shs_out = models.BigIntegerField(null=True, blank=True)
    weighted_average_shs_out_dil = models.BigIntegerField(null=True, blank=True)
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, null=True, default=None)

    class Meta:
        ordering = ['-date']
        constraints = [
            models.UniqueConstraint(fields=['symbol', 'date'], name='unique_symbol_date_income')
        ]

    def __str__(self):
        return self.symbol

class CashFlowStatement(models.Model):
    date = models.DateTimeField(auto_now_add=False, null=True, db_index=True)
    symbol = models.CharField(max_length=300, db_index=True)
    currency = models.CharField(max_length=300)
    cik = models.CharField(max_length=300, null=True)
    calendar_year = models.CharField(max_length=300, null=True, db_index=True)
    period = models.CharField(max_length=300, null=True, db_index=True)
    net_income=models.BigIntegerField(default=0, blank=True, null=True)
    depreciation_and_amortization = models.BigIntegerField(default=0, blank=True, null=True)
    deferred_income_tax = models.BigIntegerField(null=True, blank=True)
    stock_based_compensation = models.BigIntegerField(null=True, blank=True)
    change_in_working_capital = models.BigIntegerField(null=True, blank=True)
    accounts_receivables = models.BigIntegerField(null=True, blank=True)
    inventory = models.BigIntegerField(null=True, blank=True)
    accounts_payables = models.BigIntegerField(null=True, blank=True)
    other_working_capital = models.BigIntegerField(null=True, blank=True)
    other_non_cash_items = models.BigIntegerField(null=True, blank=True)
    net_cash_provided_by_operating_activities = models.BigIntegerField(null=True, blank=True)
    investments_in_property_plant_and_equipment = models.BigIntegerField(null=True, blank=True)
    acquisitions_net = models.BigIntegerField(null=True, blank=True)
    purchases_of_investments = models.BigIntegerField(null=True, blank=True)
    sales_maturities_of_investments = models.BigIntegerField(null=True, blank=True)
    other_investing_activities = models.BigIntegerField(null=True, blank=True)
    net_cash_used_for_investing_activities = models.BigIntegerField(null=True, blank=True)
    debt_repayment = models.BigIntegerField(null=True, blank=True)
    common_stock_issued = models.BigIntegerField(null=True, blank=True)
    common_stock_repurchased = models.BigIntegerField(null=True, blank=True)
    dividends_paid = models.BigIntegerField(null=True, blank=True)
    other_financing_activities = models.BigIntegerField(null=True, blank=True)
    net_cash_used_provided_by_financing_activities = models.BigIntegerField(null=True, blank=True)
    effect_of_forex_changes_on_cash = models.BigIntegerField(null=True, blank=True)
    net_change_in_cash = models.BigIntegerField(null=True, blank=True)
    cash_at_end_of_period = models.BigIntegerField(null=True, blank=True)
    cash_at_beginning_of_period = models.BigIntegerField(null=True, blank=True)
    operating_cash_flow = models.BigIntegerField(null=True, blank=True)
    capital_expenditure = models.BigIntegerField(null=True, blank=True)
    free_cash_flow = models.BigIntegerField(null=True, blank=True)
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, null=True, default=None)

    class Meta:
        ordering = ['-date']
        constraints = [
            models.UniqueConstraint(fields=['symbol', 'date'], name='unique_symbol_date_cashflow')
        ]

    def __str__(self):
        return self.symbol


class BalanceSheet(models.Model):
    date = models.DateTimeField(auto_now_add=False, null=True, db_index=True)
    symbol = models.CharField(max_length=300, db_index=True)
    currency = models.CharField(max_length=300)
    cik = models.CharField(max_length=300, null=True)
    calendar_year = models.CharField(max_length=300, null=True, db_index=True)
    period = models.CharField(max_length=300, null=True, db_index=True)
    cash_and_cash_equivalents=models.BigIntegerField(default=0, blank=True, null=True)
    short_term_investments = models.BigIntegerField(default=0, blank=True, null=True)
    cash_and_short_term_investments = models.BigIntegerField(null=True, blank=True)
    net_receivables = models.BigIntegerField(null=True, blank=True)
    inventory = models.BigIntegerField(null=True, blank=True)
    other_current_assets = models.BigIntegerField(null=True, blank=True)
    total_current_assets = models.BigIntegerField(null=True, blank=True)
    property_plant_equipment_net = models.BigIntegerField(null=True, blank=True)
    goodwill = models.BigIntegerField(null=True, blank=True)
    intangible_assets = models.BigIntegerField(null=True, blank=True)
    long_term_investments = models.BigIntegerField(null=True, blank=True)
    tax_assets = models.BigIntegerField(null=True, blank=True)
    other_non_current_assets = models.BigIntegerField(null=True, blank=True)
    total_non_current_assets = models.BigIntegerField(null=True, blank=True)
    other_assets = models.BigIntegerField(null=True, blank=True)
    total_assets = models.BigIntegerField(null=True, blank=True)
    short_term_debt = models.BigIntegerField(null=True, blank=True)
    tax_payables = models.BigIntegerField(null=True, blank=True)
    deferred_revenue = models.BigIntegerField(null=True, blank=True)
    other_current_liabilities = models.BigIntegerField(null=True, blank=True)
    total_current_liabilities = models.BigIntegerField(null=True, blank=True)
    long_term_debt = models.BigIntegerField(null=True, blank=True)
    deferred_revenue_non_current = models.BigIntegerField(null=True, blank=True)
    other_non_current_liabilities = models.BigIntegerField(null=True, blank=True)
    total_non_current_liabilities = models.BigIntegerField(null=True, blank=True)
    other_liabilities = models.BigIntegerField(null=True, blank=True)
    capital_lease_obligations = models.BigIntegerField(null=True, blank=True)
    total_liabilities = models.BigIntegerField(null=True, blank=True)
    preferred_stock = models.BigIntegerField(null=True, blank=True)
    common_stock = models.BigIntegerField(null=True, blank=True)
    retained_earnings = models.BigIntegerField(null=True, blank=True)
    accumulated_other_comprehensive_income_loss = models.BigIntegerField(null=True, blank=True)
    other_total_stockholders_equity = models.BigIntegerField(null=True, blank=True)
    total_stockholders_equity = models.BigIntegerField(null=True, blank=True)
    total_liabilities_and_stockholders_equity = models.BigIntegerField(null=True, blank=True)
    minority_interest = models.BigIntegerField(null=True, blank=True)
    total_equity = models.BigIntegerField(null=True, blank=True)
    total_liabilities_and_total_equity = models.BigIntegerField(null=True, blank=True)
    total_investments = models.BigIntegerField(null=True, blank=True)
    total_debt = models.BigIntegerField(null=True, blank=True)
    net_debt = models.BigIntegerField(null=True, blank=True)
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, null=True, default=None)

    class Meta:
        ordering = ['-date']
        constraints = [
            models.UniqueConstraint(fields=['symbol', 'date'], name='unique_symbol_date_balancesheet')
        ]

    def __str__(self):
        return self.symbol


class FundamentalMetric(models.Model):
    date = models.DateTimeField(auto_now_add=False, null=True, db_index=True)
    symbol = models.CharField(max_length=300, null=False, blank=False, db_index=True)
    period = models.CharField(max_length=20, null=False, blank=False, db_index=True)
    calendar_year = models.CharField(max_length=20, null=False, blank=False, db_index=True)
    revenue_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    net_income_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    operating_cash_flow_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    free_cash_flow_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    cash_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    book_value_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    tangible_book_value_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    shareholders_equity_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    interest_debt_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    market_cap = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    enterprise_value = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    pe_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    psales_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    price_to_operating_cashflow = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    price_to_cashflow = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    price_to_book_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    enterprise_value_to_sales = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    enterprise_value_to_ebitda = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    ev_to_operating_cash_flow = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    ev_to_free_cash_flow = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    earnings_yield = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    free_cash_flow_yield = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    debt_to_equity = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    debt_to_assets = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    net_debt_to_ebitda = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    current_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    interest_coverage = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    income_quality = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    dividend_yield = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    payout_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    sales_and_general_admin_to_revenue = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    research_and_development_to_revenue = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    intangibles_to_total_assets = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    capex_to_operating_cash_flow = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    capex_to_revenue = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    capex_to_depreciation = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    stock_based_compensation_to_revenue = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    graham_number = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    return_on_invested_capital = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    return_on_tangible_assets = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    net_graham_number = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    working_capital = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    tangible_asset_value = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    net_current_asset_value = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    invested_capital = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    average_receivables = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    average_payables = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    average_inventory = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    days_sales_outstanding = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    days_payables_outstanding = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    days_inventory_on_hand = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    receivables_turnover = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    payables_turnover = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    inventory_turnover = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    return_on_equity = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    capex_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, null=True, default=None)

    class Meta:
        ordering = ['-date']
        constraints = [
            models.UniqueConstraint(fields=['symbol', 'date'], name='unique_symbol_date_fundamentalmetric')
        ]


    def __str__(self):
        return self.symbol



class FundamentalRatio(models.Model):
    date = models.DateTimeField(auto_now_add=False, null=True, db_index=True)
    symbol = models.CharField(max_length=300, null=False, blank=False, db_index=True)
    period = models.CharField(max_length=20, null=False, blank=False, db_index=True)
    calendar_year = models.CharField(max_length=20, null=False, blank=False, db_index=True)
    current_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    quick_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    days_of_sales_outstanding = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    days_of_inventory_outstanding = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    operating_cycle = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    days_of_payables_outstanding = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    cash_conversion_cycle = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    gross_profit_margin = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    operating_profit_margin = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    net_profit_margin = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    effective_tax_rate = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    roa = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    roe = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    roic = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    net_income_ebt = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    ebt_per_ebit = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    ebit_per_revenue = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    debt_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    debt_to_equity_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    long_term_debt_to_capitalization = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    total_debt_to_capitalization = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    interest_coverage = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    cash_flow_to_debt = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    company_equity_multiplier = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    receivables_turnover = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    payables_turnover = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    inventory_turnover = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    fixed_assets_turnover = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    asset_turnover = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    operating_cash_flow_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    free_cash_flow_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    cash_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    payout_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    operating_cash_flow_to_sales = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    free_cash_flow_to_operating_cash_flow = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    cash_flow_coverage_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    short_term_coverage_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    capital_expenditure_coverage = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    dividend_paid_and_capex_coverage_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    dividend_payout_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    pb_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    ps_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    pe_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    pfcf_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    pocf_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    pcf_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    peg_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    dividend_yield = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    ev_multiple = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    price_fair_value = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, null=True, default=None)

    class Meta:
        ordering = ['-date']
        constraints = [
            models.UniqueConstraint(fields=['symbol', 'date'], name='unique_symbol_date_fundamentalratio')
        ]


    def __str__(self):
        return self.symbol
    

class FundamentalMetricTTM(models.Model):
    symbol = models.CharField(max_length=300, null=False, blank=False, db_index=True)

    revenue_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    net_income_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    operating_cash_flow_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    free_cash_flow_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    cash_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    book_value_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    tangible_book_value_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    shareholders_equity_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    interest_debt_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    market_cap = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    enterprise_value = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    pe_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    psales_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    price_to_operating_cashflow = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    price_to_cashflow = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    price_to_book_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    enterprise_value_to_sales = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    enterprise_value_to_ebitda = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    ev_to_operating_cash_flow = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    ev_to_free_cash_flow = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    earnings_yield = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    free_cash_flow_yield = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    debt_to_equity = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    debt_to_assets = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    net_debt_to_ebitda = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    current_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    interest_coverage = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    income_quality = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    dividend_yield = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    
    dividend_yield_percent = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    payout_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    sales_and_general_admin_to_revenue = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    research_and_development_to_revenue = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    intangibles_to_total_assets = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    capex_to_operating_cash_flow = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    capex_to_revenue = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    capex_to_depreciation = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    stock_based_compensation_to_revenue = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    graham_number = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    return_on_invested_capital = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    return_on_tangible_assets = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    net_graham_number = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    working_capital = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    tangible_asset_value = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    net_current_asset_value = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    invested_capital = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    average_receivables = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    average_payables = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    average_inventory = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    days_sales_outstanding = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    days_payables_outstanding = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    days_inventory_on_hand = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    receivables_turnover = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    payables_turnover = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    inventory_turnover = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    return_on_equity = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    capex_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    
    dividend_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    
    debt_to_market_cap = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, null=True, default=None)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['symbol'], name='unique_symbol_fundamentalmetricttm')
        ]


    def __str__(self):
        return self.symbol


class FundamentalRatioTTM(models.Model):
    # take out second pe, ps and peg ratio
    symbol = models.CharField(max_length=300, null=False, blank=False, db_index=True)

    dividend_yield = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    dividend_yield_percent = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    
    pe_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    peg_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    payout_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    

    current_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    quick_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    cash_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    days_of_sales_outstanding = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    days_of_inventory_outstanding = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    operating_cycle = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    days_of_payables_outstanding = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    cash_conversion_cycle = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    gross_profit_margin = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    operating_profit_margin = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    pretax_profit_margin = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    net_profit_margin = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    effective_tax_rate = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    roa = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    roe = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    roic = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    net_income_ebt = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    ebt_per_ebit = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    ebit_per_revenue = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    debt_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    debt_to_equity_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    long_term_debt_to_capitalization = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    total_debt_to_capitalization = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    interest_coverage = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    cash_flow_to_debt = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    company_equity_multiplier = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    receivables_turnover = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    payables_turnover = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    inventory_turnover = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    fixed_assets_turnover = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    asset_turnover = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    operating_cash_flow_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    free_cash_flow_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    cash_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    operating_cash_flow_to_sales = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    free_cash_flow_to_operating_cash_flow = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    cash_flow_coverage_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    short_term_coverage_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    capital_expenditure_coverage = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    dividend_paid_and_capex_coverage_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    pb_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    ps_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    pfcf_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    pocf_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    pcf_ratio = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    ev_multiple = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    price_fair_value = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)
    dividend_per_share = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True, default=0.0)

    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, null=True, default=None)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['symbol'], name='unique_symbol_fundamentalratiottm')
        ]


    def __str__(self):
        return self.symbol