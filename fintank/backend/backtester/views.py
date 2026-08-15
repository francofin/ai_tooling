"""Backtester API (§12).

Querysets are filtered by request.user at the manager level, never by a URL
parameter -- an id belonging to someone else must 404, not 403, so the API does
not confirm that the row exists.
"""
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import symbol_index
from .models import Portfolio
from .quota import get_quota
from .serializers import PortfolioSerializer

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
