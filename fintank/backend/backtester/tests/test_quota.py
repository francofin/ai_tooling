"""Metering. The numbers are settings-driven; the three rules are not."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from backtester.models import BacktestRun
from backtester.quota import QuotaExceeded, check_and_consume, get_quota, refund

User = get_user_model()


def _user(email='meter@example.com'):
    user = User.objects.create_user(username=email, email=email, password='sw0rdfish!x',
                                    first_name='Test', last_name='User')
    from users.models import UserProfile
    if not getattr(user, 'userprofile', None):
        UserProfile.objects.create(user=user)
    return user


def _run(user, counted=True, status=BacktestRun.STATUS_COMPLETE, request_hash='h'):
    return BacktestRun.objects.create(user=user, task_id=f"t-{request_hash}",
                                      request_hash=request_hash, request={},
                                      status=status, counted_against_quota=counted)


@override_settings(FREE_TIER_BACKTEST_LIMIT=3)
class GetQuotaTests(TestCase):

    def setUp(self):
        self.user = _user()

    def test_a_fresh_free_account_has_the_full_allowance(self):
        quota = get_quota(self.user)

        self.assertEqual(quota.tier, 'free')
        self.assertEqual(quota.used, 0)
        self.assertEqual(quota.limit, 3)
        self.assertEqual(quota.remaining, 3)

    def test_counted_runs_reduce_the_remaining_allowance(self):
        _run(self.user, request_hash='a')
        _run(self.user, request_hash='b')

        quota = get_quota(self.user)
        self.assertEqual(quota.used, 2)
        self.assertEqual(quota.remaining, 1)

    def test_uncounted_runs_are_not_charged(self):
        _run(self.user, counted=False, request_hash='a')

        self.assertEqual(get_quota(self.user).used, 0)

    def test_another_users_runs_do_not_count(self):
        _run(_user('other@example.com'), request_hash='a')

        self.assertEqual(get_quota(self.user).used, 0)

    def test_a_pro_account_is_unlimited(self):
        profile = self.user.userprofile
        profile.subscription_tier = 'pro'
        profile.save(update_fields=['subscription_tier'])

        quota = get_quota(self.user)
        self.assertEqual(quota.tier, 'pro')
        self.assertIsNone(quota.limit)
        self.assertIsNone(quota.remaining)

    def test_an_override_beats_both_the_tier_and_the_default(self):
        profile = self.user.userprofile
        profile.backtest_quota_override = 50
        profile.save(update_fields=['backtest_quota_override'])

        self.assertEqual(get_quota(self.user).limit, 50)

    def test_an_override_of_zero_is_honoured_rather_than_ignored(self):
        profile = self.user.userprofile
        profile.backtest_quota_override = 0
        profile.save(update_fields=['backtest_quota_override'])

        self.assertEqual(get_quota(self.user).limit, 0)

    def test_a_user_without_a_profile_still_gets_the_free_tier(self):
        from users.models import UserProfile

        UserProfile.objects.filter(user=self.user).delete()
        self.user.refresh_from_db()

        quota = get_quota(self.user)
        self.assertEqual(quota.tier, 'free')
        self.assertEqual(quota.limit, 3)

    def test_the_payload_shape_is_what_the_api_returns(self):
        self.assertEqual(set(get_quota(self.user).as_dict()),
                         {'used', 'limit', 'tier', 'remaining'})


@override_settings(FREE_TIER_BACKTEST_LIMIT=2)
class CheckAndConsumeTests(TestCase):

    def setUp(self):
        self.user = _user()

    def test_it_passes_while_allowance_remains(self):
        check_and_consume(self.user)   # must not raise

    def test_it_raises_once_the_allowance_is_gone(self):
        _run(self.user, request_hash='a')
        _run(self.user, request_hash='b')

        with self.assertRaises(QuotaExceeded) as caught:
            check_and_consume(self.user)

        self.assertEqual(caught.exception.status_code, 402)
        self.assertEqual(caught.exception.detail['used'], 2)
        self.assertEqual(caught.exception.detail['limit'], 2)
        self.assertTrue(caught.exception.detail['upgrade_required'])

    def test_a_pro_account_never_raises(self):
        profile = self.user.userprofile
        profile.subscription_tier = 'pro'
        profile.save(update_fields=['subscription_tier'])
        for i in range(10):
            _run(self.user, request_hash=f"h{i}")

        check_and_consume(self.user)   # must not raise


@override_settings(FREE_TIER_BACKTEST_LIMIT=1)
class RefundTests(TestCase):
    """Rule 3: users do not pay for our bugs."""

    def setUp(self):
        self.user = _user()

    def test_refunding_a_failed_run_restores_the_allowance(self):
        run = _run(self.user, status=BacktestRun.STATUS_FAILED, request_hash='a')
        self.assertEqual(get_quota(self.user).remaining, 0)

        refund(run)

        run.refresh_from_db()
        self.assertFalse(run.counted_against_quota)
        self.assertEqual(get_quota(self.user).remaining, 1)

    def test_refunding_twice_is_harmless(self):
        run = _run(self.user, status=BacktestRun.STATUS_FAILED, request_hash='a')

        refund(run)
        refund(run)

        self.assertEqual(get_quota(self.user).used, 0)
