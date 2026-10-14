"""The only module that talks to Stripe.

Everything else in billing/ calls these functions and works with the plain
SubscriptionState they return, so tests patch this module instead of the SDK.
Stripe objects are read by subscript (`obj["items"]`), never by attribute:
`obj.items` is dict.items on a StripeObject.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps

import stripe
from django.conf import settings

INTERVALS = ('month', 'year')
REQUIRED_SETTINGS = ('STRIPE_SECRET_KEY', 'STRIPE_PRICE_PRO_MONTHLY',
                     'STRIPE_PRICE_PRO_YEARLY', 'FRONTEND_URL')


class BillingNotConfigured(Exception):
    """A billing setting is missing; the endpoints answer 503."""


class StripeUnavailable(Exception):
    """Stripe rejected or failed the call; the endpoints answer 502."""


class InvalidWebhook(Exception):
    """The webhook payload or its signature did not verify."""


@dataclass(frozen=True)
class SubscriptionState:
    id: str
    customer_id: str
    status: str
    interval: str | None
    current_period_end: datetime | None
    cancel_at_period_end: bool


def is_configured() -> bool:
    return all(getattr(settings, name, None) for name in REQUIRED_SETTINGS)


def _client():
    if not is_configured():
        raise BillingNotConfigured()
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY)


def _price_id(interval: str) -> str:
    return {'month': settings.STRIPE_PRICE_PRO_MONTHLY,
            'year': settings.STRIPE_PRICE_PRO_YEARLY}[interval]


def _frontend(path: str) -> str:
    return settings.FRONTEND_URL.rstrip('/') + path


def _stripe_call(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except stripe.StripeError as exc:
            # The message is Stripe's own; never includes the key.
            raise StripeUnavailable(str(exc)) from exc
    return wrapper


def _id(value):
    return value if isinstance(value, str) else value['id']


def _get(obj, key):
    try:
        return obj[key]
    except (KeyError, TypeError):
        return None


@_stripe_call
def create_customer(email, user_id) -> str:
    params = {'metadata': {'user_id': str(user_id)}}
    if email:
        params['email'] = email
    return _client().v1.customers.create(params)['id']


@_stripe_call
def create_checkout_url(customer_id: str, interval: str, user_id) -> str:
    session = _client().v1.checkout.sessions.create({
        'mode': 'subscription',
        'customer': customer_id,
        'client_reference_id': str(user_id),
        'line_items': [{'price': _price_id(interval), 'quantity': 1}],
        'success_url': _frontend('/subscription?checkout=success'),
        'cancel_url': _frontend('/subscription?checkout=cancelled'),
    })
    return session['url']


@_stripe_call
def create_portal_url(customer_id: str) -> str:
    session = _client().v1.billing_portal.sessions.create({
        'customer': customer_id,
        'return_url': _frontend('/subscription'),
    })
    return session['url']


@_stripe_call
def retrieve_subscription(subscription_id: str) -> SubscriptionState:
    return to_state(_client().v1.subscriptions.retrieve(subscription_id))


@_stripe_call
def price_amount(interval: str) -> dict:
    price = _client().v1.prices.retrieve(_price_id(interval))
    return {'amount': price['unit_amount'], 'currency': price['currency']}


def parse_event(payload: bytes, signature: str, secret: str):
    try:
        return stripe.Webhook.construct_event(payload, signature, secret)
    except (stripe.SignatureVerificationError, ValueError) as exc:
        raise InvalidWebhook() from exc


def to_state(subscription) -> SubscriptionState:
    items = _get(_get(subscription, 'items') or {}, 'data') or []
    first = items[0] if items else {}
    # API 2025-03-31.basil moved the billing period onto the items.
    period_end = _get(first, 'current_period_end') or _get(subscription, 'current_period_end')
    recurring = _get(_get(first, 'price') or {}, 'recurring') or {}
    return SubscriptionState(
        id=subscription['id'],
        customer_id=_id(subscription['customer']),
        status=subscription['status'],
        interval=_get(recurring, 'interval'),
        current_period_end=(datetime.fromtimestamp(period_end, tz=timezone.utc)
                            if period_end else None),
        cancel_at_period_end=bool(_get(subscription, 'cancel_at_period_end')),
    )
