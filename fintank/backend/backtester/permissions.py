"""Permissions for the backtester routes.

Only execution is metered, so this class guards `POST /run/` alone. Every other
route uses plain IsAuthenticated -- portfolio management is free (§13 rule 2).
"""
from rest_framework.permissions import BasePermission

from .quota import get_quota


class HasBacktestQuota(BasePermission):
    message = 'Your free backtest allowance is spent.'

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method != 'POST':
            return True
        # The view still calls check_and_consume so the 402 body carries used and
        # limit; this class exists so the permission is visible on the view.
        return not get_quota(request.user).exhausted
