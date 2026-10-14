"""Pro prices as Stripe will charge them, cached so the page doesn't call
Stripe on every load. A failure is cached too, briefly: otherwise a slow or
down Stripe gets hit on every single page load for as long as it's down."""
import logging

from django.core.cache import cache

from . import gateway

logger = logging.getLogger(__name__)

PLANS_CACHE_KEY = 'billing:plans:v1'
PLANS_UNAVAILABLE_KEY = 'billing:plans:unavailable:v1'
PLANS_TTL = 3600
UNAVAILABLE_TTL = 60


def get_plans():
    cached = cache.get(PLANS_CACHE_KEY)
    if cached:
        return cached
    if cache.get(PLANS_UNAVAILABLE_KEY):
        return None
    try:
        plans = {interval: gateway.price_amount(interval) for interval in gateway.INTERVALS}
    except (gateway.StripeUnavailable, gateway.BillingNotConfigured):
        logger.warning("Could not load Pro prices from Stripe", exc_info=True)
        cache.set(PLANS_UNAVAILABLE_KEY, True, UNAVAILABLE_TTL)
        return None
    cache.set(PLANS_CACHE_KEY, plans, PLANS_TTL)
    return plans
