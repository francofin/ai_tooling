"""Pro prices as Stripe will charge them, cached so the page doesn't call
Stripe on every load. A failure is not cached: the next load retries."""
import logging

from django.core.cache import cache

from . import gateway

logger = logging.getLogger(__name__)

PLANS_CACHE_KEY = 'billing:plans:v1'
PLANS_TTL = 3600


def get_plans():
    cached = cache.get(PLANS_CACHE_KEY)
    if cached:
        return cached
    try:
        plans = {interval: gateway.price_amount(interval) for interval in gateway.INTERVALS}
    except (gateway.StripeUnavailable, gateway.BillingNotConfigured):
        logger.warning("Could not load Pro prices from Stripe", exc_info=True)
        return None
    cache.set(PLANS_CACHE_KEY, plans, PLANS_TTL)
    return plans
