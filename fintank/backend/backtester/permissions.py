"""Permissions for the backtester routes.

Only execution is metered, so this class guards `POST /run/` alone. Every other
route uses plain IsAuthenticated -- portfolio management is free (§13 rule 2).
"""
from rest_framework.permissions import BasePermission

from .quota import QuotaExceeded, get_quota


class HasBacktestQuota(BasePermission):
    message = 'Your free backtest allowance is spent.'

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method != 'POST':
            return True

        quota = get_quota(request.user)
        if quota.exhausted:
            # Raise rather than return False. A False here makes DRF answer 403
            # with a bare message *before* the view runs, so the view's own
            # check_and_consume never fires and the client loses the used/limit/
            # upgrade_required body the quota banner reads. QuotaExceeded is an
            # APIException, so the handler renders it as the intended 402.
            raise QuotaExceeded(used=quota.used, limit=quota.limit)
        return True
