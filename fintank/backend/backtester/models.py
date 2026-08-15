"""User-scoped portfolios and backtest run records (§11).

Full result JSON lives in S3 and Redis, never in Postgres. `BacktestRun` does
triple duty: quota counter, run history for a future comparison view, and usage
analytics -- which is why it keeps the request payload and a summary but not the
result.
"""
from django.conf import settings
from django.db import models


class Portfolio(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='portfolios',
                             on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default='')
    benchmark_symbol = models.CharField(max_length=20, default='SPY')
    initial_amount = models.DecimalField(max_digits=14, decimal_places=2, default=10000)
    periodic_contribution = models.DecimalField(max_digits=14, decimal_places=2,
                                                default=0)
    contribution_frequency = models.CharField(max_length=20, default='none')
    weighting_scheme = models.CharField(max_length=30, default='equal')
    backtest_mode = models.CharField(max_length=20, default='fixed')
    rebalance_frequency = models.CharField(max_length=20, default='annual')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    # The §3 advanced block. JSON rather than columns: these are optimizer knobs
    # that change with the engine, and none of them is ever queried on.
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'name')
        indexes = [models.Index(fields=['user', '-updated_at'])]
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.name} ({self.user_id})"


class PortfolioHolding(models.Model):
    portfolio = models.ForeignKey(Portfolio, related_name='holdings',
                                 on_delete=models.CASCADE)
    symbol = models.CharField(max_length=20)
    target_weight = models.DecimalField(max_digits=7, decimal_places=6, default=0)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ('portfolio', 'symbol')
        ordering = ['order']

    def __str__(self):
        return f"{self.symbol} @ {self.target_weight}"


class BacktestRun(models.Model):
    STATUS_QUEUED = 'queued'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETE = 'complete'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = (
        (STATUS_QUEUED, 'Queued'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETE, 'Complete'),
        (STATUS_FAILED, 'Failed'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='backtest_runs',
                             on_delete=models.CASCADE)
    # SET_NULL, not CASCADE: this row is the quota ledger, so deleting a saved
    # portfolio must not erase the record of runs already paid for.
    portfolio = models.ForeignKey(Portfolio, null=True, blank=True,
                                  on_delete=models.SET_NULL, related_name='runs')
    task_id = models.CharField(max_length=64, db_index=True)
    request_hash = models.CharField(max_length=64, db_index=True)
    request = models.JSONField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,
                              default=STATUS_QUEUED)
    progress = models.CharField(max_length=40, blank=True, default='')
    summary = models.JSONField(null=True, blank=True)
    result_key = models.CharField(max_length=300, blank=True, default='')
    error = models.TextField(blank=True, default='')
    counted_against_quota = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['user', '-created_at']),
                   models.Index(fields=['user', 'request_hash'])]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.task_id} [{self.status}]"
