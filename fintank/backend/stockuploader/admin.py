from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from django.conf import settings
from .models import Stock, ETF, Crypto, IncomeStatement, CashFlowStatement, BalanceSheet, FundamentalMetric, FundamentalRatio, ProfileStock, FundamentalMetricTTM, FundamentalRatioTTM

# Register your models here.
@admin.register(Stock)
class StockAdmin(ImportExportModelAdmin):
    list_per_page = settings.LIST_PER_PAGE
    list_display = ('symbol', 'name', 'exchange', 'sector', 'industry')
    search_fields = ('symbol', 'name', 'sector', 'industry')

@admin.register(ProfileStock)
class ProfileStockAdmin(ImportExportModelAdmin):
    list_per_page = settings.LIST_PER_PAGE
    list_display = ("stock_symbol", "user", "date_added")
    ordering = ("-date_added",)
    search_fields = ("stock__symbol", "user__username", "user__email")
    list_select_related = ("stock", "user")  # perf

    def stock_symbol(self, obj):
        return obj.stock.symbol if obj.stock else "-"
    stock_symbol.short_description = "Symbol"
    stock_symbol.admin_order_field = "stock__symbol"

@admin.register(ETF)
class ETFAdmin(ImportExportModelAdmin):
    list_display = ('symbol', 'name', 'exchange', 'exchange_short')
    search_fields = ('symbol', 'name', 'exchange_short')

@admin.register(Crypto)
class CryptoAdmin(ImportExportModelAdmin):
    list_display = ('symbol', 'name', 'exchange')
    search_fields = ('symbol', 'name', 'exchange')

@admin.register(IncomeStatement)
class ISAdmin(ImportExportModelAdmin):
    list_display = ('symbol', 'date', 'currency', 'period')
    search_fields = ('symbol', 'date', 'currency', 'period')

@admin.register(CashFlowStatement)
class CFAdmin(ImportExportModelAdmin):
    list_display = ('symbol', 'date', 'currency', 'period')
    search_fields = ('symbol', 'date', 'currency', 'period')

@admin.register(BalanceSheet)
class BSAdmin(ImportExportModelAdmin):
    list_display = ('symbol', 'date', 'currency', 'period')
    search_fields = ('symbol', 'date', 'currency', 'period')


@admin.register(FundamentalMetric)
class FundamentalMetricAdmin(ImportExportModelAdmin):
    list_per_page = settings.LIST_PER_PAGE
    list_display = ('symbol',)
    search_fields = ('symbol',)



@admin.register(FundamentalRatio)
class FundamentalRatioAdmin(ImportExportModelAdmin):
    list_per_page = settings.LIST_PER_PAGE
    list_display = ('symbol',)
    search_fields = ('symbol',)



@admin.register(FundamentalMetricTTM)
class FundamentalMetricTTMAdmin(ImportExportModelAdmin):
    list_per_page = settings.LIST_PER_PAGE
    list_display = ('symbol',)
    search_fields = ('symbol',)



@admin.register(FundamentalRatioTTM)
class FundamentalRatioTTMAdmin(ImportExportModelAdmin):
    list_per_page = settings.LIST_PER_PAGE
    list_display = ('symbol',)
    search_fields = ('symbol',)