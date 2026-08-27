from django.shortcuts import render, HttpResponseRedirect, get_object_or_404, redirect
from django.http import HttpResponse
from pytz import timezone
from requests import get
import boto3
import gzip
import json
from django.conf import settings
from .analyzer_utils.CorePerformanceTools import home_crypto_cache, home_etf_cache, economic_data_cache, json_safe
from utils.StockCalculations import GetData
from django.core.cache import cache
from datetime import date
from rest_framework import status, mixins, generics, viewsets, parsers
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from stockuploader.models import Stock, ETF, ProfileStock, Crypto
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .serializers import StockSerializer
from rest_framework.pagination import PageNumberPagination

data_getter = GetData()

home_index_cache = "home:index_performance:v1"

@api_view(['GET'])
def get_all_stock_names_available(request):
    # Replace with new models just for stock names, not linked to user. 
    data = cache.get("stock:names:v1")

    if data:
        payload = json.loads(gzip.decompress(data))
        return Response(payload,status=status.HTTP_200_OK)

    # fallback: try to load once even if market is closed
    from .analyzer_utils.CorePerformanceTools import get_all_stock_names
    data = get_all_stock_names()

    if data:
        return get_all_stock_names_available(request)

    return Response(
        {"detail": "Data temporarily unavailable"},
        status=503
    )

@api_view(['GET'])
def get_index_history_task(request, symbol):
    cache_key = f"home:index_chart:{symbol}:v1"

    def _decompress_and_respond(compressed):
        raw = gzip.decompress(compressed)
        data = json.loads(raw.decode("utf-8"))
        payload = data_getter.format_index_prices(data['data'])
        return Response({'data': payload, 'index_name': data['name']}, status=status.HTTP_200_OK)

    compressed = cache.get(cache_key)
    if compressed:
        try:
            return _decompress_and_respond(compressed)
        except Exception:
            pass

    try:
        from .analyzer_utils.CorePerformanceTools import get_index_charts
        get_index_charts()
        compressed = cache.get(cache_key)
        if compressed:
            return _decompress_and_respond(compressed)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({"error": "Index data not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
def get_index_performance_task(request):  
    data = cache.get(home_index_cache)

    if data:
        payload = json.loads(gzip.decompress(data))
        return Response(payload,status=status.HTTP_200_OK)

    # fallback: try to load once even if market is closed
    from .analyzer_utils.CorePerformanceTools import get_index_performance
    data = get_index_performance()

    if data:
        return Response(data, status=200)

    return Response(
        {"detail": "Data temporarily unavailable"},
        status=503
    )

@api_view(['GET'])
def get_etf_performance_task(request):  
    data = cache.get(home_etf_cache)

    if data:
        payload = json.loads(gzip.decompress(data))
        return Response(payload,status=status.HTTP_200_OK)

    from .analyzer_utils.CorePerformanceTools import get_etf_performance
    data = get_etf_performance()

    if data:
        return Response(data, status=200)

    return Response(
        {"detail": "Data temporarily unavailable"},
        status=503
    )


@api_view(['GET'])
def get_crypto_performance_task(request):  
    data = cache.get(home_crypto_cache)

    if data:
        payload = json.loads(gzip.decompress(data))
        return Response(payload,status=status.HTTP_200_OK)

    from .analyzer_utils.CorePerformanceTools import get_crypto_performance
    data = get_crypto_performance()

    if data:
        return Response(data, status=200)

    return Response(
        {"detail": "Data temporarily unavailable"},
        status=503
    )

@api_view(['GET'])
def get_gainers_losers_task(request):  
    data = cache.get("home:gainers_losers:v1")

    if data:
        payload = json.loads(gzip.decompress(data))
        return Response(payload,status=status.HTTP_200_OK)

    # fallback: try to load once even if market is closed
    from .analyzer_utils.CorePerformanceTools import get_biggest_gainers_and_losers
    data = get_biggest_gainers_and_losers()

    if data:
        return Response(data, status=200)

    return Response(
        {"detail": "Data temporarily unavailable"},
        status=503
    )

@api_view(['GET'])
def get_sector_industry_task(request, exchange):  
    cache_key = f"home:sector_performance:{exchange}:v1"
    try:
        compressed = cache.get(cache_key)
        if compressed:
            decompressed_data = json.loads(gzip.decompress(compressed))
            return Response(decompressed_data,status=status.HTTP_200_OK)
    except Exception:
        pass

    try:
        from .analyzer_utils.CorePerformanceTools import get_sector_performance_snapshot
        get_sector_performance_snapshot()
        compressed = cache.get(cache_key)
        if compressed:
            decompressed_data = json.loads(gzip.decompress(compressed))
            return Response(decompressed_data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({"detail": "Data temporarily unavailable"}, status=503)


@api_view(['GET'])
def get_constituent_returns(request, universe):
    cache_key = f"home:universe_constituents_returns:{universe}:v1"
    
    try:
        compresssed = cache.get(cache_key)
        if compresssed:
            decompressed_data = json.loads(gzip.decompress(compresssed))
            universe_data = decompressed_data['universe_data']
            heat_map = decompressed_data['heat_map']
            payload = {
                'universe_data': universe_data,
                'heat_map': heat_map
            }
            return Response(payload,status=status.HTTP_200_OK)

    except Exception:
        pass

    try:
        from .analyzer_utils.CorePerformanceTools import get_universe_constituents_returns
        get_universe_constituents_returns()
        compresssed = cache.get(cache_key)
        if compresssed:
            decompressed_data = json.loads(gzip.decompress(compresssed))
            return Response(
                {
                    "universe_data": decompressed_data["universe_data"],
                    "heat_map": decompressed_data["heat_map"],
                },
                status=status.HTTP_200_OK,
            )
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({"detail": "Data temporarily unavailable"}, status=503)


@api_view(['GET'])
def get_economic_data_task(request):
    """Whole /capital-markets payload. The page pulls this in
    getServerSideProps, so every visit is a request -- it must never touch S3."""
    compressed = cache.get(economic_data_cache)

    if not compressed:
        # Cold cache: build it once, then fall through to the cached bytes.
        try:
            from .analyzer_utils.CorePerformanceTools import get_economic_data
            get_economic_data()
            compressed = cache.get(economic_data_cache)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    if not compressed:
        return Response({"detail": "Data temporarily unavailable"},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE)

    # Unlike the other cached endpoints this one returns the stored bytes as the
    # response body rather than decompress -> json.loads -> DRF re-render: the
    # payload is ~2.7 MB of yield history and that round trip is pure waste on
    # every SSR request. Clients that advertise gzip (Next's fetch does) get the
    # cached blob verbatim.
    if 'gzip' in request.META.get('HTTP_ACCEPT_ENCODING', ''):
        response = HttpResponse(compressed, content_type='application/json')
        response['Content-Encoding'] = 'gzip'
        return response

    try:
        return HttpResponse(gzip.decompress(compressed), content_type='application/json')
    except Exception:
        return Response({"detail": "Data temporarily unavailable"},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(['GET'])
def get_universe_profiles_task(request, universe):
    from .analyzer_utils.CorePerformanceTools import UNIVERSE_PROFILE_SLUGS
    if universe not in UNIVERSE_PROFILE_SLUGS:
        return Response({"error": f"Unknown universe '{universe}'"}, status=status.HTTP_400_BAD_REQUEST)

    cache_key = f"home:universe_profiles:{universe}:v1"

    try:
        compressed = cache.get(cache_key)
        if compressed:
            payload = json.loads(gzip.decompress(compressed))
            return Response(payload, status=status.HTTP_200_OK)
    except Exception:
        pass

    try:
        from .analyzer_utils.CorePerformanceTools import get_universe_profiles
        data = get_universe_profiles(universe)
        return Response(data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_company_profile(request, symbol):
    cache_key = "company:profiles:v1"

    try:
        compressed = cache.get(cache_key)
        if compressed:
            records = data_getter.file_decompressor(compressed)

            # Find matching symbol. ETF records carry NaN in the equity-only
            # fields (ceo, no_of_employees), which the DRF renderer rejects
            # after this view returns -- so every ETF 500'd here until the
            # payload was normalised.
            return Response(json_safe(records[symbol.upper()]), status=status.HTTP_200_OK)

    except Exception:
        pass

    # Fallback: refresh cache once
    try:
        from .analyzer_utils.CorePerformanceTools import get_company_profiles
        data = get_company_profiles()
        decompressed_profiles = data_getter.file_decompressor(data)
        return Response(json_safe(decompressed_profiles[symbol.upper()]), status=status.HTTP_200_OK)
    except KeyError:
        return Response({"detail": f"Symbol '{symbol}' not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception:
        pass

    return Response(
        {"detail": "Data temporarily unavailable"},
        status=status.HTTP_503_SERVICE_UNAVAILABLE
    )


@api_view(['GET'])
def get_stock_price_data(request, symbol):
    from .analyzer_utils.CorePerformanceTools import get_stock_price_data as _getter
    try:
        payload = _getter(symbol)
        return Response(payload, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_stock_long_profile(request, symbol):
    from .analyzer_utils.CorePerformanceTools import get_stock_long_profile as _getter
    try:
        record = _getter(symbol)
        return Response(record, status=status.HTTP_200_OK)
    except KeyError:
        return Response({"detail": f"Symbol '{symbol}' not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_stock_price_data_monthly(request, symbol):
    from .analyzer_utils.CorePerformanceTools import get_stock_price_data_monthly as _getter
    try:
        payload = _getter(symbol)
        return Response(payload, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_financial_statements(request, symbol, universe, statement_type):
    from .analyzer_utils.CorePerformanceTools import get_financial_statements as _getter, VALID_UNIVERSES, VALID_STATEMENT_TYPES
    if universe not in VALID_UNIVERSES:
        return Response({"detail": f"Unknown universe '{universe}'"}, status=status.HTTP_400_BAD_REQUEST)
    if statement_type not in VALID_STATEMENT_TYPES:
        return Response({"detail": f"Unknown statement_type '{statement_type}'"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        payload = _getter(symbol, universe, statement_type)
        return Response(payload, status=status.HTTP_200_OK)
    except KeyError as e:
        return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_financial_statements_auto(request, symbol, statement_type):
    """Statements without an explicit universe -- the backend resolves it."""
    from .analyzer_utils.CorePerformanceTools import get_financial_statements_resolved as _getter, VALID_STATEMENT_TYPES
    if statement_type not in VALID_STATEMENT_TYPES:
        return Response({"detail": f"Unknown statement_type '{statement_type}'"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        payload = _getter(symbol, statement_type)
        return Response(payload, status=status.HTTP_200_OK)
    except KeyError as e:
        return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_index_page_series(request, slug):
    """Headline price series + moving averages for /indexes/<slug>.

    Also carries the curated peer list, so the frontend never hardcodes
    comparison indexes again.
    """
    from .analyzer_utils.index_tools import get_index_series as _getter
    try:
        payload = _getter(
            slug,
            frequency=request.GET.get('frequency', 'daily'),
            years=request.GET.get('years', 5),
        )
        return Response(payload, status=status.HTTP_200_OK)
    except KeyError as e:
        return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)
    except (ValueError, TypeError) as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_index_page_comparison(request, slug, peer_key):
    """One index against one peer -- replaces getcomparisondatapackone..five."""
    from .analyzer_utils.index_tools import get_index_comparison as _getter
    try:
        payload = _getter(slug, peer_key, years=request.GET.get('years', 5))
        return Response(payload, status=status.HTTP_200_OK)
    except KeyError as e:
        return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)
    except (ValueError, TypeError) as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_index_page_risk(request, slug):
    """Constituent contribution to index volatility and to period return."""
    from .analyzer_utils.index_tools import get_index_risk as _getter
    try:
        payload = _getter(slug, limit=request.GET.get('limit', 20))
        return Response(payload, status=status.HTTP_200_OK)
    except KeyError as e:
        return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)
    except (ValueError, TypeError) as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_index_page_quotes(request, slug):
    """Constituent quotes -- movers panel and PE-ranked valuation table."""
    from .analyzer_utils.index_tools import get_index_quotes as _getter
    try:
        payload = _getter(slug)
        return Response(payload, status=status.HTTP_200_OK)
    except KeyError as e:
        return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_stock_quintiles_task(request, frequency, universe):
    """Factor decile performance for one index list at one frequency."""
    from .analyzer_utils.factor_tools import get_factor_ranks as _getter
    try:
        payload = _getter(frequency, universe)
        return Response(payload, status=status.HTTP_200_OK)
    except KeyError as e:
        return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)
    except (ValueError, TypeError) as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_watchlist_performance(request, symbol):
    """Price series and period returns for one stock on the caller's watchlist.

    Adds no upstream API calls. The daily series comes from
    CorePerformanceTools.get_stock_price_data, which is already backed by the S3
    parquet and a 24h per-symbol Redis entry, so a symbol held by many users is
    still one read per day. See
    docs/superpowers/plans/2026-08-22-watchlist-performance.md.

    Scoped to the requesting user's watchlist rather than accepting any symbol:
    without that check this would be an unauthenticated-equivalent route to
    precomputed stats for the whole universe.
    """
    from .analyzer_utils.CorePerformanceTools import get_stock_price_data as _prices
    from .analyzer_utils.watchlist_performance import period_returns, since_added_return
    from .analyzer_utils.market_hours import get_effective_market_date

    entry = (
        ProfileStock.objects
        .filter(user=request.user, stock__symbol__iexact=symbol, stock__isnull=False)
        .select_related('stock')
        .first()
    )
    if entry is None:
        return Response(
            {"detail": f"'{symbol}' is not on your watchlist."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        payload = _prices(entry.stock.symbol)
    except Exception:
        # A symbol with no parquet in the bucket is an expected gap, not a fault.
        return Response(
            {"detail": f"No price history available for '{entry.stock.symbol}'."},
            status=status.HTTP_404_NOT_FOUND,
        )

    dates = payload.get('dates') or []
    prices = (payload.get('series') or {}).get('adjClose') or []

    if not dates or not prices:
        return Response(
            {"detail": f"No price history available for '{entry.stock.symbol}'."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # The period figures depend only on the symbol and the trading day, so they
    # are cached per symbol rather than per user -- the arithmetic runs once a
    # day however many watchlists hold it.
    try:
        market_date = get_effective_market_date()
    except Exception:
        market_date = date.today()

    periods_key = f"watchlist:perf:{entry.stock.symbol.upper()}:{market_date}:v1"
    periods = cache.get(periods_key)
    if periods is None:
        periods = period_returns(dates, prices)
        cache.set(periods_key, periods, timeout=86400)

    # Depends on this user's own date_added, so it is computed per request. It is
    # a binary search and a division over data already in hand.
    since_added = since_added_return(dates, prices, entry.date_added)

    return Response(
        json_safe({
            "symbol": entry.stock.symbol,
            "name": entry.stock.name,
            "date_added": entry.date_added,
            "dates": dates,
            "prices": prices,
            "periods": periods,
            "since_added": since_added,
        }),
        status=status.HTTP_200_OK,
    )


@api_view(['GET'])
def get_technicals(request, symbol):
    """Candles, volume and technical indicators for one symbol.

    Replaces the five endpoints build-comparison.js was written against, none
    of which ever existed in a urls.py. Those were one billed FMP call per
    indicator; this is one cached parquet read per symbol and no FMP call.

    `indicators` is optional: omitting it returns candles and volume alone, so
    a freshly added ticker renders its price chart before anything is toggled.

    Status split copied from get_index_page_series above -- not from
    get_stock_price_data, which is a blanket 500.
    """
    from .analyzer_utils.technicals import get_technicals as _getter
    try:
        payload = _getter(symbol, request.GET.get('indicators'))
        return Response(payload, status=status.HTTP_200_OK)
    except KeyError as e:
        # str(KeyError('msg')) is "'msg'" -- args[0] avoids shipping the quotes.
        detail = e.args[0] if e.args else str(e)
        return Response({"detail": detail}, status=status.HTTP_404_NOT_FOUND)
    except (ValueError, TypeError) as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
