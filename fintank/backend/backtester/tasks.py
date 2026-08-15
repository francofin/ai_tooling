"""The Celery task. Celery's autodiscover_tasks() picks this up with no config
change (§16)."""
from django.utils import timezone

from celery import shared_task

from .engine.backtest import run_backtest
from .engine.config import (
    OPTIMIZER_SCHEMES,
    NoEligibleAssets,
    PriceDataUnavailable,
    RequestValidationError,
    validate_request,
)
from .engine.prices import load_benchmark_series, load_price_panel
from .models import BacktestRun
from .quota import refund
from .results import build_payload, store_payload, summarize

PROGRESS_STAGES = ('loading_prices', 'optimizing', 'simulating', 'computing_metrics')


def _set_progress(run, stage):
    run.progress = stage
    run.save(update_fields=['progress'])


@shared_task(bind=True)
def run_portfolio_backtest(self, run_id):
    """Load prices, run the engine, store the result, update the row.

    Errors are recorded on the row and the run is refunded rather than retried:
    a bad request or a missing symbol will fail identically on every retry, and
    users do not pay for our bugs (§13 rule 3).
    """
    try:
        run = BacktestRun.objects.get(pk=run_id)
    except BacktestRun.DoesNotExist:
        return None

    run.status = BacktestRun.STATUS_RUNNING
    run.progress = PROGRESS_STAGES[0]
    run.save(update_fields=['status', 'progress'])

    try:
        request = validate_request(run.request)

        panel = load_price_panel(request.symbols, start=request.start_date,
                                 end=request.end_date)
        benchmark, _ = load_benchmark_series(request.benchmark_symbol,
                                             start=request.start_date,
                                             end=request.end_date)

        # The loop optimizes and simulates in one pass, so the stage label
        # reflects which of the two dominates the wait for this request.
        _set_progress(run, 'optimizing' if request.weighting_scheme in OPTIMIZER_SCHEMES
                      else 'simulating')
        result = run_backtest(panel, request)

        _set_progress(run, 'computing_metrics')
        payload = build_payload(result, request, panel, benchmark)

        run.result_key = store_payload(run.user_id, run.task_id, payload)
        run.summary = summarize(payload['metrics'])
        run.status = BacktestRun.STATUS_COMPLETE
        run.progress = 'complete'
        run.error = ''
        run.completed_at = timezone.now()
        run.save(update_fields=['result_key', 'summary', 'status', 'progress',
                                'error', 'completed_at'])
        return run.task_id

    except (RequestValidationError, NoEligibleAssets, PriceDataUnavailable) as error:
        _fail(run, str(error))
        return None
    except Exception as error:                      # noqa: BLE001
        _fail(run, f"{type(error).__name__}: {error}")
        return None


def _fail(run, message):
    run.status = BacktestRun.STATUS_FAILED
    run.progress = 'failed'
    run.error = message
    run.completed_at = timezone.now()
    run.save(update_fields=['status', 'progress', 'error', 'completed_at'])
    refund(run)
