from django.contrib import admin

from .models import BacktestRun, Portfolio, PortfolioHolding


class PortfolioHoldingInline(admin.TabularInline):
    model = PortfolioHolding
    extra = 0


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'weighting_scheme', 'updated_at')
    search_fields = ('name', 'user__email')
    inlines = [PortfolioHoldingInline]


@admin.register(BacktestRun)
class BacktestRunAdmin(admin.ModelAdmin):
    list_display = ('task_id', 'user', 'status', 'counted_against_quota', 'created_at')
    list_filter = ('status', 'counted_against_quota')
    search_fields = ('task_id', 'request_hash', 'user__email')
    readonly_fields = ('task_id', 'request_hash', 'request', 'summary')
