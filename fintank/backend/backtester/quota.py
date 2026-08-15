"""Usage metering (§13).

Pricing is deliberately undefined here. What ships is the meter and the three
rules that decide whether the tool feels fair:

  1. Only novel runs count. An identical request_hash serves from cache and is
     free -- otherwise toggling a chart option burns a credit.
  2. Saving, loading, editing and duplicating portfolios are always free. Only
     execution meters.
  3. Failed runs are refunded. Users do not pay for our bugs.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import APIException

from .models import BacktestRun

DEFAULT_FREE_LIMIT = 10
UNLIMITED_TIERS = ('pro',)


class QuotaExceeded(APIException):
    """402 Payment Required -- the free allowance is spent."""
    status_code = status.HTTP_402_PAYMENT_REQUIRED

    def __init__(self, used, limit):
        payload = {
            'detail': (f"You have used all {limit} of your free backtests. "
                       f"Saving and editing portfolios stays free."),
            'used': used,
            'limit': limit,
            'upgrade_required': True,
        }
        super().__init__(payload)
        # DRF's _get_error_details walks the dict and rewrites every leaf as an
        # ErrorDetail *string*, so `used` would reach the client as "2" and
        # `upgrade_required` as "True". The quota banner does arithmetic on those
        # numbers, so put the native types back. DRF's exception handler passes a
        # dict detail through to the Response untouched, so this renders as JSON
        # numbers and a JSON boolean.
        self.detail = payload


@dataclass(frozen=True)
class Quota:
    used: int
    limit: int | None
    tier: str

    @property
    def remaining(self) -> int | None:
        if self.limit is None:
            return None
        return max(self.limit - self.used, 0)

    @property
    def exhausted(self) -> bool:
        return self.limit is not None and self.used >= self.limit

    def as_dict(self) -> dict:
        return {'used': self.used, 'limit': self.limit, 'tier': self.tier,
                'remaining': self.remaining}


def _profile(user):
    return getattr(user, 'userprofile', None)


def get_quota(user) -> Quota:
    used = BacktestRun.objects.filter(user=user, counted_against_quota=True).count()
    profile = _profile(user)
    tier = getattr(profile, 'subscription_tier', 'free') or 'free'
    override = getattr(profile, 'backtest_quota_override', None)

    if override is not None:
        # `is not None` rather than truthiness: an override of 0 is a deliberate
        # lockout and must not silently fall through to the free-tier default.
        limit = int(override)
    elif tier in UNLIMITED_TIERS:
        limit = None
    else:
        limit = int(getattr(settings, 'FREE_TIER_BACKTEST_LIMIT', DEFAULT_FREE_LIMIT))

    return Quota(used=used, limit=limit, tier=tier)


def check_and_consume(user) -> None:
    """Raise if the allowance is spent. Consumption itself is the BacktestRun
    row the caller creates next -- there is no separate counter to drift out of
    sync with the ledger."""
    quota = get_quota(user)
    if quota.exhausted:
        raise QuotaExceeded(used=quota.used, limit=quota.limit)


def refund(run: BacktestRun) -> None:
    if run.counted_against_quota:
        run.counted_against_quota = False
        run.save(update_fields=['counted_against_quota'])
