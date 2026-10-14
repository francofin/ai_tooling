import logging

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.models import UserProfile

from . import gateway, plans, sync

logger = logging.getLogger(__name__)

NOT_CONFIGURED = {'detail': 'Billing is not available right now.'}
STRIPE_DOWN = {'detail': 'Could not reach the payment provider. Please try again.'}


def _profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def subscription_view(request):
    profile = _profile(request.user)
    return Response({
        'tier': profile.subscription_tier or 'free',
        'status': profile.subscription_status,
        'interval': profile.subscription_interval,
        'current_period_end': profile.current_period_end,
        'cancel_at_period_end': profile.cancel_at_period_end,
        'has_billing_account': bool(profile.stripe_customer_id),
        'plans': plans.get_plans() if gateway.is_configured() else None,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def checkout_view(request):
    if not gateway.is_configured():
        return Response(NOT_CONFIGURED, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    interval = request.data.get('interval')
    if interval not in gateway.INTERVALS:
        return Response({'detail': 'Choose a monthly or yearly plan.'},
                        status=status.HTTP_400_BAD_REQUEST)

    profile = _profile(request.user)
    if sync.tier_for_status(profile.subscription_status) == 'pro':
        return Response({'detail': 'You already have Pro. Manage it from the billing portal.'},
                        status=status.HTTP_409_CONFLICT)

    try:
        # Locked so two quick clicks can't create two Stripe customers.
        with transaction.atomic():
            profile = UserProfile.objects.select_for_update().get(pk=profile.pk)
            if not profile.stripe_customer_id:
                profile.stripe_customer_id = gateway.create_customer(request.user.email, request.user.pk)
                profile.save(update_fields=['stripe_customer_id', 'updated_at'])
        url = gateway.create_checkout_url(profile.stripe_customer_id, interval, request.user.pk)
    except gateway.StripeUnavailable:
        logger.warning("Checkout session failed for user %s", request.user.pk, exc_info=True)
        return Response(STRIPE_DOWN, status=status.HTTP_502_BAD_GATEWAY)
    return Response({'url': url})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def portal_view(request):
    if not gateway.is_configured():
        return Response(NOT_CONFIGURED, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    profile = _profile(request.user)
    if not profile.stripe_customer_id:
        return Response({'detail': 'You do not have a subscription to manage yet.'},
                        status=status.HTTP_409_CONFLICT)
    try:
        url = gateway.create_portal_url(profile.stripe_customer_id)
    except gateway.StripeUnavailable:
        logger.warning("Portal session failed for user %s", request.user.pk, exc_info=True)
        return Response(STRIPE_DOWN, status=status.HTTP_502_BAD_GATEWAY)
    return Response({'url': url})


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Stripe calls this directly. Plain Django view, not DRF: the signature is
    over the raw body, which DRF's parsers would consume first."""
    secret = settings.STRIPE_WEBHOOK_SECRET
    if not secret or not gateway.is_configured():
        return JsonResponse(NOT_CONFIGURED, status=503)

    try:
        event = gateway.parse_event(request.body, request.headers.get('Stripe-Signature', ''), secret)
    except gateway.InvalidWebhook:
        return JsonResponse({'detail': 'Invalid signature.'}, status=400)

    try:
        sync.handle_event(event)
    except Exception:
        # 500 makes Stripe retry later. Log the type only, never the payload.
        # `event` may be a real StripeObject here, which has no `.get` -- use
        # gateway.field so this logging path cannot itself raise.
        logger.exception("Stripe webhook %s failed", gateway.field(event, 'type'))
        return JsonResponse({'detail': 'Webhook processing failed.'}, status=500)
    return JsonResponse({'received': True})
