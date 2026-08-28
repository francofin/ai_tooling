from django.shortcuts import render, redirect
from import_export.formats.base_formats import XLSX
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import Stock, ETF, ProfileStock, Crypto, FundamentalMetric, FundamentalRatio, IncomeStatement, CashFlowStatement, BalanceSheet
from .resources import (StockResource, ETFResource, ProfileStockResource, CryptoResource, IncomeStatementResource, CashFlowResource, BalanceSheetResource,
                        FundamentalRatioResource, FundamentalMetricResource, FundamentalMetricTTMResource, FundamentalRatioTTMResource)
from django.contrib import messages
from django.http import HttpResponse
from tablib import Dataset
import io
import pandas as pd
from django.views.decorators.http import require_POST
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

secret_key = settings.SECRET_KEY

# Map resource classes to model names or URL-friendly names
RESOURCE_CLASSES = {
    'stock': StockResource,
    'etf': ETFResource,
    'crypto': CryptoResource,
    'income': IncomeStatementResource,
    'cashflow': CashFlowResource,
    'balancesheet': BalanceSheetResource,
    'fundamentalmetric': FundamentalMetricResource,
    'fundamentalratio': FundamentalRatioResource,
    'fundamentalmetricttm': FundamentalMetricTTMResource,
    'fundamentalratiottm': FundamentalRatioTTMResource,
}


def _staff_only(u):  # why: portal is admin-only
    return u.is_active and (u.is_staff or u.is_superuser)

def _df_to_dataset(df: pd.DataFrame) -> Dataset:
    """Convert pandas DataFrame to tablib Dataset with headers preserved."""
    ds = Dataset()
    ds.headers = list(df.columns)
    for row in df.itertuples(index=False, name=None):
        ds.append(list(row))
    return ds

@login_required(login_url="pages:landing")
@user_passes_test(_staff_only, login_url="pages:landing")
@require_POST
def upload_file_for_model(request, model_name: str):
    """
    Accepts .parquet or .xlsx and imports via django-import-export Resource for `model_name`.
    """
    f = request.FILES.get("myfile")
    if not f:
        messages.error(request, "Please choose a file to upload.")
        return redirect("pages:landing")

    resource_class = RESOURCE_CLASSES.get(model_name)
    if not resource_class:
        messages.error(request, f"No resource defined for model: {model_name}")
        return redirect("pages:landing")

    resource = resource_class()
    name = (f.name or "").lower()

    try:
        if name.endswith(".parquet"):
            df = pd.read_parquet(f)  # requires pyarrow
            if df.empty:
                messages.warning(request, "File contained no rows.")
                return redirect("pages:landing")
            imported_data = _df_to_dataset(df)

        elif name.endswith(".xlsx"):
            # fmt = XLSX()
            imported_data = Dataset()
            imported_data.load(f.read(), format='xlsx')

        else:
            messages.error(request, "Unsupported file type. Upload a .parquet or .xlsx file.")
            return redirect("pages:landing")

        # Dry run first
        result = resource.import_data(imported_data, dry_run=True)
        if result.has_errors():
            messages.error(request, "Errors found in the file. No data was imported.")
            first_errs = []
            for row_idx, errs in result.row_errors()[:5]:
                first_errs.append(f"Row {row_idx+1}: " + "; ".join(str(e.error) for e in errs))
            if first_errs:
                messages.error(request, " | ".join(first_errs))
            return redirect("pages:landing")

        # Commit
        result = resource.import_data(imported_data, dry_run=False)
        created = result.totals.get("new", 0)
        updated = result.totals.get("update", 0)
        skipped = result.totals.get("skip", 0)
        messages.success(request, f"{model_name.capitalize()} import OK — created: {created}, updated: {updated}, skipped: {skipped}.")

    except Exception as exc:
        messages.error(request, f"Upload failed: {exc}")

    return redirect("pages:landing")

# ---------------------------------------------------------------------------
# Watchlist
#
# authContext.js has been calling these three routes all along -- they simply
# were never implemented, so every "Add to Watchlist" button 404'd silently.
# The response shapes below are dictated by that existing client code rather
# than chosen fresh: both the add and the *remove* handler gate on
# `res.data.added === true`, and checkStockOnWatchlist reads a bare boolean.
# ---------------------------------------------------------------------------

def _watchlist_stock_or_404(ticker):
    """Resolve a ticker to a Stock row.

    Matching is case-insensitive so /addtowatchlist/rqp.to/ behaves like
    /addtowatchlist/RQP.TO/. ETFs live in this table too (Stock.is_etf), which
    is why the ETF page can reuse it -- the separate ETF model is empty.
    """
    return Stock.objects.filter(symbol__iexact=ticker).first()


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_to_watchlist(request, ticker):
    stock = _watchlist_stock_or_404(ticker)
    if stock is None:
        return Response({"detail": f"Symbol '{ticker}' not found."},
                        status=status.HTTP_404_NOT_FOUND)

    ProfileStock.objects.get_or_create(user=request.user, stock=stock)
    return Response({"added": True}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def delete_from_watchlist(request, ticker):
    stock = _watchlist_stock_or_404(ticker)
    if stock is None:
        return Response({"detail": f"Symbol '{ticker}' not found."},
                        status=status.HTTP_404_NOT_FOUND)

    # Scoped to request.user, so one account cannot clear another's watchlist.
    ProfileStock.objects.filter(user=request.user, stock=stock).delete()
    # `added: True` reads oddly for a removal, but removeFromWatchlist in
    # authContext.js checks for exactly that before flipping its local state.
    return Response({"added": True}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_watchlist(request):
    """The requesting user's watchlist, most recently added first.

    `date_added` is carried through because the profile performance panel reports
    each holding's return since it was added; it has been recorded on
    ProfileStock all along.

    Rows whose Stock was deleted are skipped -- the FK is SET_NULL, so a removed
    symbol leaves a ProfileStock pointing at nothing rather than disappearing.
    """
    entries = (
        ProfileStock.objects
        .filter(user=request.user, stock__isnull=False)
        .select_related('stock')
        .order_by('-date_added')
    )

    return Response(
        [
            {
                "symbol": entry.stock.symbol,
                "name": entry.stock.name,
                "date_added": entry.date_added,
            }
            for entry in entries
        ],
        status=status.HTTP_200_OK,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def stock_on_watchlist(request, ticker):
    stock = _watchlist_stock_or_404(ticker)
    if stock is None:
        return Response({"detail": f"Symbol '{ticker}' not found."},
                        status=status.HTTP_404_NOT_FOUND)

    on_list = ProfileStock.objects.filter(user=request.user, stock=stock).exists()
    return Response(on_list, status=status.HTTP_200_OK)
