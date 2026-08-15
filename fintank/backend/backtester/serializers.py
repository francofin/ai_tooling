"""Serializers for the backtester API."""
from django.db import transaction
from rest_framework import serializers

from .models import BacktestRun, Portfolio, PortfolioHolding


class PortfolioHoldingSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortfolioHolding
        fields = ('symbol', 'target_weight', 'order')

    def validate_symbol(self, value):
        symbol = str(value).strip().upper()
        if not symbol:
            raise serializers.ValidationError('A holding needs a symbol.')
        return symbol


class PortfolioSerializer(serializers.ModelSerializer):
    holdings = PortfolioHoldingSerializer(many=True, required=False)

    class Meta:
        model = Portfolio
        fields = ('id', 'name', 'description', 'benchmark_symbol', 'initial_amount',
                  'periodic_contribution', 'contribution_frequency',
                  'weighting_scheme', 'backtest_mode', 'rebalance_frequency',
                  'start_date', 'end_date', 'settings', 'holdings',
                  'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate_name(self, value):
        """Uniqueness is per-user, and the user comes from the request rather than
        the body, so the model's unique_together cannot be checked by DRF's
        default validator -- do it here to return 400 instead of a 500."""
        user = self.context['request'].user
        queryset = Portfolio.objects.filter(user=user, name=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError('You already have a portfolio with that name.')
        return value

    @transaction.atomic
    def create(self, validated_data):
        holdings = validated_data.pop('holdings', [])
        portfolio = Portfolio.objects.create(user=self.context['request'].user,
                                             **validated_data)
        self._write_holdings(portfolio, holdings)
        return portfolio

    @transaction.atomic
    def update(self, instance, validated_data):
        # `holdings` absent means "leave them alone"; present means "replace
        # wholesale". A per-holding diff would need stable ids the client does
        # not have, and the builder always submits the full basket anyway.
        holdings = validated_data.pop('holdings', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if holdings is not None:
            instance.holdings.all().delete()
            self._write_holdings(instance, holdings)
        return instance

    @staticmethod
    def _write_holdings(portfolio, holdings):
        PortfolioHolding.objects.bulk_create([
            PortfolioHolding(portfolio=portfolio,
                             symbol=entry['symbol'],
                             target_weight=entry.get('target_weight', 0),
                             order=entry.get('order', position))
            for position, entry in enumerate(holdings)
        ])


class BacktestRunSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = BacktestRun
        fields = ('id', 'task_id', 'status', 'progress', 'summary', 'portfolio',
                  'request', 'error', 'counted_against_quota',
                  'created_at', 'completed_at')
        read_only_fields = fields
