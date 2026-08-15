"""Models plus the privilege-escalation guard on UserProfile."""
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from backtester.models import BacktestRun, Portfolio, PortfolioHolding

User = get_user_model()


def _user(email='someone@example.com'):
    return User.objects.create_user(username=email, email=email, password='sw0rdfish!x',
                                    first_name='Test', last_name='User')


class PortfolioModelTests(TestCase):

    def setUp(self):
        self.user = _user()

    def test_defaults_match_the_spec(self):
        portfolio = Portfolio.objects.create(user=self.user, name='Core')

        self.assertEqual(portfolio.benchmark_symbol, 'SPY')
        self.assertEqual(float(portfolio.initial_amount), 10_000.0)
        self.assertEqual(float(portfolio.periodic_contribution), 0.0)
        self.assertEqual(portfolio.contribution_frequency, 'none')
        self.assertEqual(portfolio.weighting_scheme, 'equal')
        self.assertEqual(portfolio.backtest_mode, 'fixed')
        self.assertEqual(portfolio.rebalance_frequency, 'annual')
        self.assertEqual(portfolio.settings, {})

    def test_a_user_cannot_reuse_a_portfolio_name(self):
        Portfolio.objects.create(user=self.user, name='Core')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Portfolio.objects.create(user=self.user, name='Core')

    def test_two_users_can_each_have_a_portfolio_called_core(self):
        Portfolio.objects.create(user=self.user, name='Core')
        Portfolio.objects.create(user=_user('other@example.com'), name='Core')

        self.assertEqual(Portfolio.objects.filter(name='Core').count(), 2)

    def test_holdings_are_ordered_by_their_order_field(self):
        portfolio = Portfolio.objects.create(user=self.user, name='Core')
        PortfolioHolding.objects.create(portfolio=portfolio, symbol='VTI', order=1)
        PortfolioHolding.objects.create(portfolio=portfolio, symbol='AAPL', order=0)

        self.assertEqual([h.symbol for h in portfolio.holdings.all()], ['AAPL', 'VTI'])

    def test_a_symbol_cannot_appear_twice_in_one_portfolio(self):
        portfolio = Portfolio.objects.create(user=self.user, name='Core')
        PortfolioHolding.objects.create(portfolio=portfolio, symbol='AAPL')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PortfolioHolding.objects.create(portfolio=portfolio, symbol='AAPL')

    def test_deleting_a_portfolio_deletes_its_holdings(self):
        portfolio = Portfolio.objects.create(user=self.user, name='Core')
        PortfolioHolding.objects.create(portfolio=portfolio, symbol='AAPL')

        portfolio.delete()
        self.assertEqual(PortfolioHolding.objects.count(), 0)


class BacktestRunModelTests(TestCase):

    def setUp(self):
        self.user = _user()

    def test_a_run_starts_queued_and_counts_against_quota(self):
        run = BacktestRun.objects.create(user=self.user, task_id='t1',
                                         request_hash='h1', request={})

        self.assertEqual(run.status, BacktestRun.STATUS_QUEUED)
        self.assertTrue(run.counted_against_quota)
        self.assertIsNone(run.completed_at)

    def test_deleting_a_portfolio_keeps_its_runs(self):
        """Run history is the quota ledger; deleting a portfolio must not erase it."""
        portfolio = Portfolio.objects.create(user=self.user, name='Core')
        run = BacktestRun.objects.create(user=self.user, portfolio=portfolio,
                                         task_id='t2', request_hash='h2', request={})

        portfolio.delete()
        run.refresh_from_db()
        self.assertIsNone(run.portfolio)
        self.assertEqual(BacktestRun.objects.count(), 1)

    def test_deleting_a_user_deletes_their_runs(self):
        BacktestRun.objects.create(user=self.user, task_id='t3',
                                   request_hash='h3', request={})

        self.user.delete()
        self.assertEqual(BacktestRun.objects.count(), 0)


class UserProfileFieldTests(TestCase):

    def setUp(self):
        self.user = _user()
        self.profile = self._profile()

    def _profile(self):
        from users.models import UserProfile

        profile = getattr(self.user, 'userprofile', None)
        return profile or UserProfile.objects.create(user=self.user)

    def test_new_accounts_default_to_the_free_tier(self):
        self.assertEqual(self.profile.subscription_tier, 'free')
        self.assertIsNone(self.profile.backtest_quota_override)


class PrivilegeEscalationTests(TestCase):
    """REQUIRED (§11, §15). Without the read-only guard the meter is trivially
    bypassable by any authenticated user."""

    def setUp(self):
        from users.models import UserProfile

        self.user = _user()
        self.profile = (getattr(self.user, 'userprofile', None)
                        or UserProfile.objects.create(user=self.user))
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _patch(self, payload):
        return self.client.patch('/api/users/me/profile/update/', payload, format='json')

    def test_patching_subscription_tier_does_not_change_it(self):
        self._patch({'subscription_tier': 'pro'})
        self.profile.refresh_from_db()

        self.assertEqual(self.profile.subscription_tier, 'free')

    def test_patching_the_quota_override_does_not_change_it(self):
        self._patch({'backtest_quota_override': 100_000})
        self.profile.refresh_from_db()

        self.assertIsNone(self.profile.backtest_quota_override)

    def test_the_tier_is_still_readable_so_the_banner_can_show_it(self):
        """Read-only, not excluded -- the frontend displays tier and remaining runs."""
        self.profile.subscription_tier = 'pro'
        self.profile.save(update_fields=['subscription_tier'])

        response = self._patch({'company_number': '123'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('subscription_tier'), 'pro')

    def test_a_writable_field_still_updates(self):
        response = self._patch({'company_number': '999'})

        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.company_number, '999')
