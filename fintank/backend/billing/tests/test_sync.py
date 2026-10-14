from datetime import datetime, timezone
from unittest.mock import patch

import stripe
from django.test import TestCase, override_settings

from backtester.quota import get_quota
from billing import sync
from billing.gateway import SubscriptionState
from billing.tests.test_profile_fields import make_user
from users.models import UserProfile

END = datetime(2026, 11, 13, tzinfo=timezone.utc)


def state(**overrides):
    base = dict(id='sub_1', customer_id='cus_1', status='active', interval='month',
                current_period_end=END, cancel_at_period_end=False)
    base.update(overrides)
    return SubscriptionState(**base)


def event(kind, obj):
    return {'type': kind, 'data': {'object': obj}}


class TierForStatusTests(TestCase):

    def test_pro_granting_statuses(self):
        for status in ('active', 'trialing', 'past_due'):
            self.assertEqual(sync.tier_for_status(status), 'pro', status)

    def test_everything_else_is_free(self):
        for status in ('canceled', 'unpaid', 'incomplete', 'incomplete_expired',
                       'paused', None, ''):
            self.assertEqual(sync.tier_for_status(status), 'free', status)


class ApplySubscriptionTests(TestCase):

    def setUp(self):
        self.user = make_user()
        UserProfile.objects.filter(user=self.user).update(stripe_customer_id='cus_1')

    def profile(self):
        return UserProfile.objects.get(user=self.user)

    def test_an_active_subscription_makes_the_user_pro(self):
        self.assertTrue(sync.apply_subscription(state()))

        p = self.profile()
        self.assertEqual(p.subscription_tier, 'pro')
        self.assertEqual(p.stripe_subscription_id, 'sub_1')
        self.assertEqual(p.subscription_status, 'active')
        self.assertEqual(p.subscription_interval, 'month')
        self.assertEqual(p.current_period_end, END)
        self.assertFalse(p.cancel_at_period_end)

    def test_a_pending_cancellation_keeps_pro_until_the_period_ends(self):
        sync.apply_subscription(state(cancel_at_period_end=True))
        p = self.profile()
        self.assertEqual(p.subscription_tier, 'pro')
        self.assertTrue(p.cancel_at_period_end)

    def test_a_cancelled_subscription_drops_the_user_to_free(self):
        sync.apply_subscription(state())
        sync.apply_subscription(state(status='canceled'))
        self.assertEqual(self.profile().subscription_tier, 'free')

    def test_applying_the_same_state_twice_is_harmless(self):
        sync.apply_subscription(state())
        sync.apply_subscription(state())
        self.assertEqual(self.profile().subscription_tier, 'pro')

    def test_an_unknown_customer_writes_nothing(self):
        with self.assertLogs('billing.sync', level='WARNING'):
            self.assertFalse(sync.apply_subscription(state(customer_id='cus_nobody')))
        self.assertEqual(self.profile().subscription_tier, 'free')

    def test_falls_back_to_the_user_id_from_checkout(self):
        UserProfile.objects.filter(user=self.user).update(stripe_customer_id=None)
        self.assertTrue(sync.apply_subscription(state(), user_id=str(self.user.pk)))
        self.assertEqual(self.profile().stripe_customer_id, 'cus_1')

    def test_the_user_id_fallback_never_moves_a_profile_to_another_customer(self):
        with self.assertLogs('billing.sync', level='ERROR'):
            self.assertFalse(sync.apply_subscription(state(customer_id='cus_other'),
                                                     user_id=str(self.user.pk)))
        self.assertEqual(self.profile().stripe_customer_id, 'cus_1')

    def test_a_garbage_user_id_is_ignored(self):
        with self.assertLogs('billing.sync', level='WARNING'):
            self.assertFalse(sync.apply_subscription(state(customer_id='cus_nobody'), user_id='abc'))

    def test_a_second_live_subscription_is_not_adopted(self):
        sync.apply_subscription(state())
        with self.assertLogs('billing.sync', level='ERROR'):
            self.assertFalse(sync.apply_subscription(state(id='sub_2')))
        self.assertEqual(self.profile().stripe_subscription_id, 'sub_1')

    def test_an_old_subscription_ending_does_not_downgrade_the_live_one(self):
        sync.apply_subscription(state(id='sub_2'))
        self.assertFalse(sync.apply_subscription(state(id='sub_1', status='canceled')))
        p = self.profile()
        self.assertEqual(p.stripe_subscription_id, 'sub_2')
        self.assertEqual(p.subscription_tier, 'pro')

    def test_a_new_subscription_replaces_a_finished_one(self):
        sync.apply_subscription(state(status='canceled'))
        self.assertTrue(sync.apply_subscription(state(id='sub_2')))
        self.assertEqual(self.profile().stripe_subscription_id, 'sub_2')

    @override_settings(FREE_TIER_BACKTEST_LIMIT=3)
    def test_upgrade_and_cancellation_move_the_backtest_limit(self):
        self.assertEqual(get_quota(self.user).limit, 3)
        sync.apply_subscription(state())
        # apply_subscription writes through a UserProfile row it looks up itself,
        # a different Python object from self.user.userprofile. Django's reverse
        # one-to-one accessor caches that related object on first access (see
        # get_quota() above), so self.user needs an explicit refresh to see the
        # write -- otherwise get_quota(self.user) reads the pre-upgrade cached
        # profile despite the database already holding 'pro'.
        self.user.refresh_from_db()
        self.assertIsNone(get_quota(self.user).limit)
        sync.apply_subscription(state(status='canceled'))
        self.user.refresh_from_db()
        self.assertEqual(get_quota(self.user).limit, 3)


class HandleEventTests(TestCase):

    def setUp(self):
        self.user = make_user()
        UserProfile.objects.filter(user=self.user).update(stripe_customer_id='cus_1')

    def test_subscription_events_refetch_the_subscription(self):
        for kind in ('customer.subscription.created', 'customer.subscription.updated',
                     'customer.subscription.deleted'):
            with patch('billing.sync.gateway.retrieve_subscription', return_value=state()) as get:
                sync.handle_event(event(kind, {'id': 'sub_1', 'customer': 'cus_1', 'status': 'stale'}))
            get.assert_called_once_with('sub_1')

    def test_the_stored_state_comes_from_stripe_not_the_payload(self):
        with patch('billing.sync.gateway.retrieve_subscription',
                   return_value=state(status='canceled')):
            sync.handle_event(event('customer.subscription.updated',
                                    {'id': 'sub_1', 'status': 'active'}))
        self.assertEqual(UserProfile.objects.get(user=self.user).subscription_tier, 'free')

    def test_checkout_completed_uses_the_session_subscription_and_user(self):
        with patch('billing.sync.gateway.retrieve_subscription', return_value=state()) as get, \
             patch('billing.sync.apply_subscription') as apply:
            sync.handle_event(event('checkout.session.completed',
                                    {'subscription': 'sub_1', 'client_reference_id': '5'}))
        get.assert_called_once_with('sub_1')
        apply.assert_called_once_with(state(), user_id='5')

    def test_checkout_without_a_subscription_is_ignored(self):
        with patch('billing.sync.gateway.retrieve_subscription') as get:
            sync.handle_event(event('checkout.session.completed', {'subscription': None}))
        get.assert_not_called()

    def test_unhandled_events_are_ignored(self):
        with patch('billing.sync.gateway.retrieve_subscription') as get:
            sync.handle_event(event('invoice.paid', {'id': 'in_1'}))
        get.assert_not_called()

    def test_checkout_completed_works_on_a_real_stripe_event(self):
        real_event = stripe.Event.construct_from({
            'object': 'event', 'type': 'checkout.session.completed',
            'data': {'object': {'object': 'checkout.session', 'subscription': 'sub_1',
                                'client_reference_id': '5'}},
        }, 'sk_test_x')

        with patch('billing.sync.gateway.retrieve_subscription', return_value=state()) as get, \
             patch('billing.sync.apply_subscription') as apply:
            sync.handle_event(real_event)

        get.assert_called_once_with('sub_1')
        apply.assert_called_once_with(state(), user_id='5')

    def test_subscription_updated_works_on_a_real_stripe_event(self):
        real_event = stripe.Event.construct_from({
            'object': 'event', 'type': 'customer.subscription.updated',
            'data': {'object': {'object': 'subscription', 'id': 'sub_1',
                                'customer': 'cus_1', 'status': 'stale'}},
        }, 'sk_test_x')

        with patch('billing.sync.gateway.retrieve_subscription', return_value=state()) as get, \
             patch('billing.sync.apply_subscription') as apply:
            sync.handle_event(real_event)

        get.assert_called_once_with('sub_1')
        apply.assert_called_once_with(state(), user_id=None)
