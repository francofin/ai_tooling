"""Backtester API (§12).

Querysets are filtered by request.user at the manager level, never by a URL
parameter -- an id belonging to someone else must 404, not 403, so the API does
not confirm that the row exists.
"""
import hashlib
import json
import uuid

from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import symbol_index
from .engine.config import RequestValidationError, normalized_payload, validate_request
from .models import BacktestRun, Portfolio
from .permissions import HasBacktestQuota
from .quota import QuotaExceeded, check_and_consume, get_quota
from .results import load_payload
from .serializers import BacktestRunSummarySerializer, PortfolioSerializer
from .tasks import run_portfolio_backtest

SEARCH_LIMIT = 25


class PortfolioListCreateView(generics.ListCreateAPIView):
    serializer_class = PortfolioSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return (Portfolio.objects
                .filter(user=self.request.user)
                .prefetch_related('holdings'))


class PortfolioDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PortfolioSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (Portfolio.objects
                .filter(user=self.request.user)
                .prefetch_related('holdings'))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def duplicate_portfolio(request, pk):
    """Copying is free -- only execution meters (§13 rule 2)."""
    try:
        original = (Portfolio.objects
                    .filter(user=request.user)
                    .prefetch_related('holdings')
                    .get(pk=pk))
    except Portfolio.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    holdings = [{'symbol': h.symbol, 'target_weight': h.target_weight, 'order': h.order}
                for h in original.holdings.all()]

    base_name = f"{original.name} (copy)"
    name, suffix = base_name, 2
    while Portfolio.objects.filter(user=request.user, name=name).exists():
        name = f"{base_name} {suffix}"
        suffix += 1

    payload = PortfolioSerializer(original).data
    payload.update({'name': name, 'holdings': holdings})
    for read_only in ('id', 'created_at', 'updated_at'):
        payload.pop(read_only, None)

    serializer = PortfolioSerializer(data=payload, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_symbols(request):
    query = request.query_params.get('q', '')
    return Response({'results': symbol_index.search(query, limit=SEARCH_LIMIT)},
                    status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def quota_view(request):
    return Response(get_quota(request.user).as_dict(), status=status.HTTP_200_OK)


HISTORY_PAGE_SIZE = 20


def _request_hash(request_obj) -> str:
    canonical = json.dumps(normalized_payload(request_obj), sort_keys=True,
                           separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


@api_view(['POST'])
@permission_classes([IsAuthenticated, HasBacktestQuota])
def submit_run(request):
    """Enqueue a backtest. Never runs the engine in the request thread (§12)."""
    try:
        parsed = validate_request(request.data)
    except RequestValidationError as error:
        return Response({'detail': str(error)},
                        status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    request_hash = _request_hash(parsed)

    # Rule 1: an identical request serves from the existing run and is free.
    # Without this, toggling a chart option burns a credit.
    existing = (BacktestRun.objects
                .filter(user=request.user, request_hash=request_hash,
                        status=BacktestRun.STATUS_COMPLETE)
                .order_by('-created_at')
                .first())
    if existing:
        return Response({'task_id': existing.task_id, 'status': existing.status,
                         'cached': True}, status=status.HTTP_200_OK)

    try:
        check_and_consume(request.user)
    except QuotaExceeded as error:
        return Response(error.detail, status=error.status_code)

    portfolio_id = request.data.get('portfolio_id')
    portfolio = None
    if portfolio_id:
        portfolio = Portfolio.objects.filter(user=request.user, pk=portfolio_id).first()

    run = BacktestRun.objects.create(
        user=request.user,
        portfolio=portfolio,
        task_id=uuid.uuid4().hex,
        request_hash=request_hash,
        request=normalized_payload(parsed),
        status=BacktestRun.STATUS_QUEUED,
    )
    run_portfolio_backtest.delay(run.pk)
    return Response({'task_id': run.task_id, 'status': run.status, 'cached': False},
                    status=status.HTTP_202_ACCEPTED)


def _own_run(request, task_id):
    return BacktestRun.objects.filter(user=request.user, task_id=task_id).first()


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def run_status(request, task_id):
    run = _own_run(request, task_id)
    if not run:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    return Response({'task_id': run.task_id, 'status': run.status,
                     'progress': run.progress, 'error': run.error},
                    status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def run_results(request, task_id):
    run = _own_run(request, task_id)
    if not run:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if run.status == BacktestRun.STATUS_FAILED:
        return Response({'detail': run.error or 'The backtest failed.'},
                        status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    if run.status != BacktestRun.STATUS_COMPLETE:
        return Response({'detail': 'Still running.', 'status': run.status},
                        status=status.HTTP_202_ACCEPTED)

    payload = load_payload(run)
    if payload is None:
        return Response({'detail': 'These results have expired. Re-run the backtest.'},
                        status=status.HTTP_410_GONE)
    return Response(payload, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def run_history(request):
    queryset = BacktestRun.objects.filter(user=request.user)
    try:
        page = max(int(request.query_params.get('page', 1)), 1)
    except ValueError:
        page = 1
    start = (page - 1) * HISTORY_PAGE_SIZE
    rows = queryset[start:start + HISTORY_PAGE_SIZE]
    return Response({'count': queryset.count(), 'page': page,
                     'results': BacktestRunSummarySerializer(rows, many=True).data},
                    status=status.HTTP_200_OK)
