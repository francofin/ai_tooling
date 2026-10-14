"""Turns Stripe subscription state into UserProfile fields.

Every handled webhook re-fetches the subscription from Stripe and writes its
current state, so duplicate and out-of-order deliveries converge on the right
answer without an event log.

Real Stripe objects (what `stripe.Webhook.construct_event` returns, and its
nested `data.object`) are StripeObject instances, not dicts: they have no
`.get` and raise KeyError on a missing key. Every read from an event or a
Stripe object therefore goes through `gateway.field`, which works on both a
plain dict (as the tests use) and a real StripeObject.
"""
import logging

from django.db import transaction

from users.models import UserProfile

from . import gateway

logger = logging.getLogger(__name__)

# past_due keeps Pro while Stripe retries the card.
PRO_STATUSES = frozenset({'active', 'trialing', 'past_due'})

HANDLED_EVENTS = frozenset({
    'checkout.session.completed',
    'customer.subscription.created',
    'customer.subscription.updated',
    'customer.subscription.deleted',
})


def tier_for_status(status) -> str:
    return 'pro' if status in PRO_STATUSES else 'free'


def _find_profile(customer_id, user_id):
    profile = UserProfile.objects.filter(stripe_customer_id=customer_id).first()
    if profile is None and user_id is not None and str(user_id).isdigit():
        profile = UserProfile.objects.filter(user_id=int(user_id)).first()
    return profile


def apply_subscription(state: gateway.SubscriptionState, user_id=None) -> bool:
    found = _find_profile(state.customer_id, user_id)
    if found is None:
        logger.warning("Stripe subscription %s for unknown customer %s", state.id, state.customer_id)
        return False

    with transaction.atomic():
        profile = UserProfile.objects.select_for_update().get(pk=found.pk)

        if profile.stripe_customer_id and profile.stripe_customer_id != state.customer_id:
            logger.error("Subscription %s is for customer %s but user %s is customer %s; not applied",
                         state.id, state.customer_id, profile.user_id, profile.stripe_customer_id)
            return False

        tracked = profile.stripe_subscription_id
        if tracked and tracked != state.id and tier_for_status(profile.subscription_status) == 'pro':
            if tier_for_status(state.status) == 'pro':
                logger.error("User %s has a second live subscription %s; keeping %s. "
                             "Cancel and refund %s in Stripe.",
                             profile.user_id, state.id, tracked, state.id)
            return False

        profile.stripe_customer_id = state.customer_id
        profile.stripe_subscription_id = state.id
        profile.subscription_status = state.status
        profile.subscription_interval = state.interval
        profile.current_period_end = state.current_period_end
        profile.cancel_at_period_end = state.cancel_at_period_end
        profile.subscription_tier = tier_for_status(state.status)
        profile.save(update_fields=[
            'stripe_customer_id', 'stripe_subscription_id', 'subscription_status',
            'subscription_interval', 'current_period_end', 'cancel_at_period_end',
            'subscription_tier', 'updated_at',
        ])
    return True


def handle_event(event) -> None:
    kind = gateway.field(event, 'type')
    if kind not in HANDLED_EVENTS:
        return

    obj = gateway.field(gateway.field(event, 'data'), 'object')
    if kind == 'checkout.session.completed':
        subscription = gateway.field(obj, 'subscription')
        user_id = gateway.field(obj, 'client_reference_id')
        if not subscription:
            return
    else:
        subscription = gateway.field(obj, 'id')
        user_id = None

    subscription_id = subscription if isinstance(subscription, str) else gateway.field(subscription, 'id')
    apply_subscription(gateway.retrieve_subscription(subscription_id), user_id=user_id)
