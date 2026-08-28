from import_export import resources
from .models import (Stock, ETF, ProfileStock, IncomeStatement, CashFlowStatement, BalanceSheet, FundamentalMetric, FundamentalRatio, Crypto, FundamentalRatioTTM, FundamentalMetricTTM)

class InjectStockMixin:
    def before_import_row(self, row, **kwargs):
        symbol = row.get('symbol')
        if not symbol:
            raise ValueError("Missing symbol")

        try:
            row['stock'] = Stock.objects.get(symbol=symbol)
        except Stock.DoesNotExist:
            raise ValueError(f"Stock with symbol {symbol} does not exist")


class StockResource(resources.ModelResource):

    class Meta:
        model = Stock
        import_id_fields = ('symbol',)
        exclude = ('id', 'owner_count')
        skip_unchanged = True
        report_skipped = True

class ProfileStockResource(resources.ModelResource):

    class Meta:
        model = ProfileStock


class ETFResource(resources.ModelResource):

    class Meta:
        model = ETF
        import_id_fields = ('symbol',)
        skip_unchanged = True
        report_skipped = True

class IncomeStatementResource(InjectStockMixin, resources.ModelResource):

    class Meta:
        model = IncomeStatement
        import_id_fields = ('symbol', 'date')
        exclude = ('id', 'stock',) 
        skip_unchanged = True
        report_skipped = True

        
class CashFlowResource(InjectStockMixin, resources.ModelResource):

    class Meta:
        model = CashFlowStatement
        import_id_fields = ('symbol', 'date')
        exclude = ('id', 'stock',) 
        skip_unchanged = True
        report_skipped = True


class BalanceSheetResource(InjectStockMixin, resources.ModelResource):

    class Meta:
        model = BalanceSheet
        import_id_fields = ('symbol', 'date')
        exclude = ('id', 'stock',) 
        skip_unchanged = True
        report_skipped = True


class FundamentalMetricResource(InjectStockMixin, resources.ModelResource):

    class Meta:
        model = FundamentalMetric
        import_id_fields = ('symbol', 'date')
        exclude = ('id', 'stock',) 
        skip_unchanged = True
        report_skipped = True


class FundamentalRatioResource(InjectStockMixin, resources.ModelResource):

    class Meta:
        model = FundamentalRatio
        import_id_fields = ('symbol', 'date')
        exclude = ('id', 'stock',) 
        skip_unchanged = True
        report_skipped = True


class CryptoResource(resources.ModelResource):

    class Meta:
        model = Crypto
        import_id_fields = ('symbol',)
        skip_unchanged = True
        report_skipped = True

class FundamentalMetricTTMResource(InjectStockMixin, resources.ModelResource):

    class Meta:
        model = FundamentalMetricTTM
        import_id_fields = ('symbol',)
        exclude = ('id', 'stock',) 
        skip_unchanged = True
        report_skipped = True


class FundamentalRatioTTMResource(InjectStockMixin, resources.ModelResource):

    class Meta:
        model = FundamentalRatioTTM
        import_id_fields = ('symbol',)
        exclude = ('id', 'stock',) 
        skip_unchanged = True
        report_skipped = True