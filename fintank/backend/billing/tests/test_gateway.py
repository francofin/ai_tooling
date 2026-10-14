import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import stripe
from django.test import SimpleTestCase, override_settings

from billing import gateway

CONFIGURED = dict(STRIPE_SECRET_KEY='sk_test_x', STRIPE_PRICE_PRO_MONTHLY='price_m',
                  STRIPE_PRICE_PRO_YEARLY='price_y', FRONTEND_URL='http://localhost:8020/')

SUB = {
    'id': 'sub_1', 'customer': 'cus_1', 'status': 'active', 'cancel_at_period_end': False,
    'items': {'data': [{'current_period_end': 1791849600,
                        'price': {'id': 'price_y', 'recurring': {'interval': 'year'}}}]},
}


def signed(payload: bytes, secret: str, at=None):
    at = int(at or time.time())
    sig = hmac.new(secret.encode(), f"{at}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={at},v1={sig}"


class ToStateTests(SimpleTestCase):

    def test_reads_the_period_end_from_the_first_item(self):
        state = gateway.to_state(SUB)
        self.assertEqual(state, gateway.SubscriptionState(
            id='sub_1', customer_id='cus_1', status='active', interval='year',
            current_period_end=datetime(2026, 10, 13, tzinfo=timezone.utc),
            cancel_at_period_end=False))

    def test_falls_back_to_the_legacy_top_level_period_end(self):
        legacy = dict(SUB, current_period_end=1791849600,
                      items={'data': [{'price': {'recurring': {'interval': 'month'}}}]})
        state = gateway.to_state(legacy)
        self.assertEqual(state.current_period_end, datetime(2026, 10, 13, tzinfo=timezone.utc))
        self.assertEqual(state.interval, 'month')

    def test_an_expanded_customer_object_gives_its_id(self):
        self.assertEqual(gateway.to_state(dict(SUB, customer={'id': 'cus_9'})).customer_id, 'cus_9')

    def test_works_on_a_real_stripe_object(self):
        obj = stripe.Subscription.construct_from(SUB, 'sk_test_x')
        self.assertEqual(gateway.to_state(obj).interval, 'year')

    def test_no_items_means_no_period_or_interval(self):
        state = gateway.to_state(dict(SUB, items={'data': []}))
        self.assertIsNone(state.current_period_end)
        self.assertIsNone(state.interval)

    def test_cancel_at_marks_cancelled_and_becomes_the_period_end(self):
        # Flexible billing mode (API 2026-09-30.endive): the portal's "cancel
        # at period end" sets `cancel_at`, not `cancel_at_period_end`.
        obj = stripe.Subscription.construct_from(
            dict(SUB, cancel_at_period_end=False, cancel_at=1800000000), 'sk_test_x')
        state = gateway.to_state(obj)
        self.assertTrue(state.cancel_at_period_end)
        self.assertEqual(state.current_period_end, datetime(2027, 1, 15, 8, 0, tzinfo=timezone.utc))

    def test_cancel_at_none_leaves_existing_behaviour_unchanged(self):
        state = gateway.to_state(dict(SUB, cancel_at=None))
        self.assertEqual(state.current_period_end, datetime(2026, 10, 13, tzinfo=timezone.utc))
        self.assertFalse(state.cancel_at_period_end)


class ConfigTests(SimpleTestCase):

    @override_settings(**CONFIGURED)
    def test_configured_when_every_setting_is_present(self):
        self.assertTrue(gateway.is_configured())

    @override_settings(**dict(CONFIGURED, STRIPE_PRICE_PRO_YEARLY=None))
    def test_not_configured_when_any_setting_is_missing(self):
        self.assertFalse(gateway.is_configured())
        with self.assertRaises(gateway.BillingNotConfigured):
            gateway.create_portal_url('cus_1')


@override_settings(**CONFIGURED)
class CallTests(SimpleTestCase):

    def _client(self):
        client = MagicMock()
        patcher = patch.object(gateway.stripe, 'StripeClient', return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)
        return client

    def test_checkout_uses_the_interval_price_and_return_urls(self):
        client = self._client()
        client.v1.checkout.sessions.create.return_value = {'url': 'https://checkout.stripe.com/x'}

        url = gateway.create_checkout_url('cus_1', 'year', 42)

        self.assertEqual(url, 'https://checkout.stripe.com/x')
        params = client.v1.checkout.sessions.create.call_args.args[0]
        self.assertEqual(params['mode'], 'subscription')
        self.assertEqual(params['customer'], 'cus_1')
        self.assertEqual(params['client_reference_id'], '42')
        self.assertEqual(params['line_items'], [{'price': 'price_y', 'quantity': 1}])
        self.assertEqual(params['success_url'], 'http://localhost:8020/subscription?checkout=success')
        self.assertEqual(params['cancel_url'], 'http://localhost:8020/subscription?checkout=cancelled')

    def test_portal_returns_to_the_subscription_page(self):
        client = self._client()
        client.v1.billing_portal.sessions.create.return_value = {'url': 'https://billing.stripe.com/p'}

        self.assertEqual(gateway.create_portal_url('cus_1'), 'https://billing.stripe.com/p')
        params = client.v1.billing_portal.sessions.create.call_args.args[0]
        self.assertEqual(params, {'customer': 'cus_1',
                                  'return_url': 'http://localhost:8020/subscription'})

    def test_customer_carries_the_user_id(self):
        client = self._client()
        client.v1.customers.create.return_value = {'id': 'cus_new'}

        self.assertEqual(gateway.create_customer('a@b.co', 7), 'cus_new')
        params = client.v1.customers.create.call_args.args[0]
        self.assertEqual(params, {'email': 'a@b.co', 'metadata': {'user_id': '7'}})

    def test_price_amount(self):
        client = self._client()
        client.v1.prices.retrieve.return_value = {'unit_amount': 999, 'currency': 'usd'}

        self.assertEqual(gateway.price_amount('month'), {'amount': 999, 'currency': 'usd'})
        client.v1.prices.retrieve.assert_called_once_with('price_m')
        # Retries off: a slow Stripe must not stall the subscription page.
        gateway.stripe.StripeClient.assert_called_once_with('sk_test_x', max_network_retries=0)

    def test_retrieve_subscription_fetches_and_converts(self):
        client = self._client()
        client.v1.subscriptions.retrieve.return_value = stripe.Subscription.construct_from(
            SUB, 'sk_test_x')

        state = gateway.retrieve_subscription('sub_1')

        client.v1.subscriptions.retrieve.assert_called_once_with('sub_1')
        gateway.stripe.StripeClient.assert_called_once_with('sk_test_x')
        self.assertEqual(state.id, 'sub_1')
        self.assertEqual(state.interval, 'year')
        self.assertEqual(state.current_period_end, datetime(2026, 10, 13, tzinfo=timezone.utc))

    def test_stripe_errors_become_stripe_unavailable(self):
        client = self._client()
        client.v1.billing_portal.sessions.create.side_effect = stripe.StripeError('down')

        with self.assertRaises(gateway.StripeUnavailable):
            gateway.create_portal_url('cus_1')


class ParseEventTests(SimpleTestCase):
    SECRET = 'whsec_test'

    def test_a_correctly_signed_payload_parses(self):
        payload = json.dumps({'id': 'evt_1', 'object': 'event', 'type': 'customer.subscription.updated',
                              'data': {'object': {'id': 'sub_1'}}}).encode()

        event = gateway.parse_event(payload, signed(payload, self.SECRET), self.SECRET)

        self.assertEqual(event['type'], 'customer.subscription.updated')
        self.assertEqual(event['data']['object']['id'], 'sub_1')

    def test_a_wrong_signature_is_rejected(self):
        payload = b'{"id": "evt_1", "object": "event"}'
        with self.assertRaises(gateway.InvalidWebhook):
            gateway.parse_event(payload, signed(payload, 'whsec_other'), self.SECRET)

    def test_a_missing_signature_is_rejected(self):
        with self.assertRaises(gateway.InvalidWebhook):
            gateway.parse_event(b'{}', '', self.SECRET)

    def test_an_old_signature_is_rejected(self):
        payload = b'{"id": "evt_1", "object": "event"}'
        with self.assertRaises(gateway.InvalidWebhook):
            gateway.parse_event(payload, signed(payload, self.SECRET, at=time.time() - 3600), self.SECRET)
