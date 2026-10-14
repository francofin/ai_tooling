from datetime import datetime, timezone
from unittest.mock import patch

import stripe
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from billing import gateway, plans
from billing.tests.test_gateway import CONFIGURED
from billing.tests.test_profile_fields import make_user
from users.models import UserProfile

LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
PLANS = {'month': {'amount': 999, 'currency': 'usd'}, 'year': {'amount': 7188, 'currency': 'usd'}}


@override_settings(CACHES=LOCMEM, **CONFIGURED)
class ViewTestCase(TestCase):

    def setUp(self):
        cache.clear()
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def set_profile(self, **fields):
        UserProfile.objects.filter(user=self.user).update(**fields)


class SubscriptionViewTests(ViewTestCase):

    def test_a_free_user(self):
        with patch('billing.plans.gateway.price_amount', side_effect=lambda i: PLANS[i]):
            data = self.client.get('/api/billing/subscription/').json()
        self.assertEqual(data, {
            'tier': 'free', 'status': None, 'interval': None, 'current_period_end': None,
            'cancel_at_period_end': False, 'has_billing_account': False, 'plans': PLANS,
        })

    def test_a_pro_user(self):
        self.set_profile(subscription_tier='pro', subscription_status='active',
                         subscription_interval='year', stripe_customer_id='cus_1',
                         current_period_end=datetime(2027, 10, 13, tzinfo=timezone.utc))
        with patch('billing.plans.gateway.price_amount', side_effect=lambda i: PLANS[i]):
            data = self.client.get('/api/billing/subscription/').json()
        self.assertEqual(data['tier'], 'pro')
        self.assertEqual(data['interval'], 'year')
        self.assertTrue(data['has_billing_account'])
        self.assertTrue(data['current_period_end'].startswith('2027-10-13T00:00:00'))

    def test_plans_are_cached(self):
        with patch('billing.plans.gateway.price_amount', side_effect=lambda i: PLANS[i]) as price:
            self.client.get('/api/billing/subscription/')
            self.client.get('/api/billing/subscription/')
        self.assertEqual(price.call_count, 2)  # month + year, once

    def test_plans_are_null_when_stripe_is_down_and_not_cached(self):
        with patch('billing.plans.gateway.price_amount', side_effect=gateway.StripeUnavailable('x')), \
             self.assertLogs('billing.plans', level='WARNING'):
            data = self.client.get('/api/billing/subscription/').json()
        self.assertIsNone(data['plans'])
        self.assertIsNone(cache.get(plans.PLANS_CACHE_KEY))

    @override_settings(STRIPE_PRICE_PRO_MONTHLY=None)
    def test_unconfigured_billing_still_shows_the_tier(self):
        response = self.client.get('/api/billing/subscription/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['plans'])

    def test_requires_login(self):
        self.assertEqual(APIClient().get('/api/billing/subscription/').status_code, 401)


class CheckoutViewTests(ViewTestCase):

    def test_creates_the_customer_once_and_returns_the_checkout_url(self):
        with patch('billing.views.gateway.create_customer', return_value='cus_new') as customer, \
             patch('billing.views.gateway.create_checkout_url', return_value='https://co/x') as checkout:
            first = self.client.post('/api/billing/checkout/', {'interval': 'year'}, format='json')
            second = self.client.post('/api/billing/checkout/', {'interval': 'month'}, format='json')

        self.assertEqual(first.json(), {'url': 'https://co/x'})
        self.assertEqual(second.status_code, 200)
        customer.assert_called_once_with(self.user.email, self.user.pk)
        checkout.assert_any_call('cus_new', 'year', self.user.pk)
        self.assertEqual(UserProfile.objects.get(user=self.user).stripe_customer_id, 'cus_new')

    def test_a_bad_interval_is_400(self):
        response = self.client.post('/api/billing/checkout/', {'interval': 'week'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_an_existing_live_subscription_is_409(self):
        self.set_profile(subscription_status='past_due', stripe_customer_id='cus_1')
        with patch('billing.views.gateway.create_checkout_url') as checkout:
            response = self.client.post('/api/billing/checkout/', {'interval': 'month'}, format='json')
        self.assertEqual(response.status_code, 409)
        checkout.assert_not_called()

    def test_stripe_failure_is_502(self):
        self.set_profile(stripe_customer_id='cus_1')
        with patch('billing.views.gateway.create_checkout_url',
                   side_effect=gateway.StripeUnavailable('x')), \
             self.assertLogs('billing.views', level='WARNING'):
            response = self.client.post('/api/billing/checkout/', {'interval': 'month'}, format='json')
        self.assertEqual(response.status_code, 502)

    @override_settings(FRONTEND_URL=None)
    def test_unconfigured_billing_is_503(self):
        response = self.client.post('/api/billing/checkout/', {'interval': 'month'}, format='json')
        self.assertEqual(response.status_code, 503)


class PortalViewTests(ViewTestCase):

    def test_no_billing_account_is_409(self):
        self.assertEqual(self.client.post('/api/billing/portal/').status_code, 409)

    def test_returns_the_portal_url(self):
        self.set_profile(stripe_customer_id='cus_1')
        with patch('billing.views.gateway.create_portal_url', return_value='https://bp/x') as portal:
            response = self.client.post('/api/billing/portal/')
        self.assertEqual(response.json(), {'url': 'https://bp/x'})
        portal.assert_called_once_with('cus_1')


@override_settings(STRIPE_WEBHOOK_SECRET='whsec_test')
class WebhookViewTests(ViewTestCase):

    def post(self, body=b'{}', signature='t=1,v1=x'):
        return APIClient().post('/api/billing/webhook/', body, content_type='application/json',
                                HTTP_STRIPE_SIGNATURE=signature)

    def test_a_bad_signature_is_400_and_nothing_is_handled(self):
        with patch('billing.views.gateway.parse_event', side_effect=gateway.InvalidWebhook()), \
             patch('billing.views.sync.handle_event') as handle:
            self.assertEqual(self.post().status_code, 400)
        handle.assert_not_called()

    def test_a_verified_event_is_handled(self):
        evt = {'type': 'customer.subscription.updated', 'data': {'object': {'id': 'sub_1'}}}
        with patch('billing.views.gateway.parse_event', return_value=evt) as parse, \
             patch('billing.views.sync.handle_event') as handle:
            response = self.post(b'{"x": 1}', 'sig')
        self.assertEqual(response.status_code, 200)
        parse.assert_called_once_with(b'{"x": 1}', 'sig', 'whsec_test')
        handle.assert_called_once_with(evt)

    def test_an_unexpected_error_is_500_so_stripe_retries(self):
        with patch('billing.views.gateway.parse_event', return_value={'type': 'x'}), \
             patch('billing.views.sync.handle_event', side_effect=RuntimeError('boom')), \
             self.assertLogs('billing.views', level='ERROR'):
            self.assertEqual(self.post().status_code, 500)

    def test_a_stripe_outage_while_syncing_is_500(self):
        with patch('billing.views.gateway.parse_event', return_value={'type': 'x'}), \
             patch('billing.views.sync.handle_event', side_effect=gateway.StripeUnavailable('x')), \
             self.assertLogs('billing.views', level='ERROR'):
            self.assertEqual(self.post().status_code, 500)

    def test_a_real_stripe_event_logging_path_does_not_raise(self):
        """Controller ruling: real Stripe event objects have no `.get`, so the
        except-branch logging must read the type through gateway.field, not
        `event.get('type')`. This proves that path works on a real event."""
        evt = stripe.Event.construct_from({
            'id': 'evt_1', 'object': 'event', 'type': 'customer.subscription.updated',
            'data': {'object': {'id': 'sub_1'}},
        }, 'sk_test_x')
        with patch('billing.views.gateway.parse_event', return_value=evt), \
             patch('billing.views.sync.handle_event', side_effect=RuntimeError('boom')), \
             self.assertLogs('billing.views', level='ERROR'):
            self.assertEqual(self.post().status_code, 500)

    @override_settings(STRIPE_WEBHOOK_SECRET=None)
    def test_without_a_webhook_secret_it_is_503(self):
        self.assertEqual(self.post().status_code, 503)

    def test_get_is_not_allowed(self):
        self.assertEqual(APIClient().get('/api/billing/webhook/').status_code, 405)
