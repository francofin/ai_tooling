"""API surface. The price loader is mocked everywhere -- no S3, FMP or Redis."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from backtester.models import Portfolio, PortfolioHolding

User = get_user_model()

LOCMEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'backtester-view-tests',
    }
}


def _user(email='api@example.com'):
    user = User.objects.create_user(username=email, email=email, password='sw0rdfish!x',
                                    first_name='Test', last_name='User')
    from users.models import UserProfile
    if not getattr(user, 'userprofile', None):
        UserProfile.objects.create(user=user)
    return user


def _client(user=None):
    client = APIClient()
    if user:
        client.force_authenticate(user=user)
    return client


class AuthenticationTests(TestCase):
    """Every route requires authentication (§12)."""

    def test_anonymous_requests_are_rejected_everywhere(self):
        client = _client()
        for method, path in [
            ('get', '/api/backtester/portfolios/'),
            ('post', '/api/backtester/portfolios/'),
            ('get', '/api/backtester/portfolios/1/'),
            ('post', '/api/backtester/portfolios/1/duplicate/'),
            ('get', '/api/backtester/quota/'),
            ('get', '/api/backtester/search-symbols/?q=aa'),
            # '/api/backtester/history/' is added by Task 14, which owns the route.
        ]:
            with self.subTest(path=path):
                response = getattr(client, method)(path)
                self.assertIn(response.status_code, (401, 403))


class PortfolioCrudTests(TestCase):

    def setUp(self):
        self.user = _user()
        self.client = _client(self.user)

    def _payload(self, **overrides):
        payload = {
            'name': 'Core',
            'holdings': [{'symbol': 'aapl', 'target_weight': 0.6, 'order': 0},
                         {'symbol': 'VTI', 'target_weight': 0.4, 'order': 1}],
        }
        payload.update(overrides)
        return payload

    def test_creating_a_portfolio_stores_its_holdings(self):
        response = self.client.post('/api/backtester/portfolios/', self._payload(),
                                    format='json')

        self.assertEqual(response.status_code, 201)
        portfolio = Portfolio.objects.get(name='Core')
        self.assertEqual(portfolio.user, self.user)
        self.assertEqual([h.symbol for h in portfolio.holdings.all()], ['AAPL', 'VTI'])

    def test_the_owner_is_taken_from_the_request_not_the_body(self):
        other = _user('other@example.com')
        self.client.post('/api/backtester/portfolios/',
                         self._payload(user=other.pk), format='json')

        self.assertEqual(Portfolio.objects.get(name='Core').user, self.user)

    def test_the_list_shows_only_my_portfolios(self):
        Portfolio.objects.create(user=self.user, name='Mine')
        Portfolio.objects.create(user=_user('other@example.com'), name='Theirs')

        response = self.client.get('/api/backtester/portfolios/')

        names = [row['name'] for row in response.data]
        self.assertEqual(names, ['Mine'])

    def test_a_duplicate_name_is_a_400_not_a_500(self):
        self.client.post('/api/backtester/portfolios/', self._payload(), format='json')
        response = self.client.post('/api/backtester/portfolios/', self._payload(),
                                    format='json')

        self.assertEqual(response.status_code, 400)

    def test_retrieving_another_users_portfolio_is_a_404(self):
        theirs = Portfolio.objects.create(user=_user('other@example.com'), name='Theirs')

        response = self.client.get(f"/api/backtester/portfolios/{theirs.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_patching_replaces_the_holdings_wholesale(self):
        created = self.client.post('/api/backtester/portfolios/', self._payload(),
                                   format='json').data
        response = self.client.patch(
            f"/api/backtester/portfolios/{created['id']}/",
            {'holdings': [{'symbol': 'BND', 'target_weight': 1.0, 'order': 0}]},
            format='json')

        self.assertEqual(response.status_code, 200)
        portfolio = Portfolio.objects.get(pk=created['id'])
        self.assertEqual([h.symbol for h in portfolio.holdings.all()], ['BND'])

    def test_patching_without_holdings_leaves_them_alone(self):
        created = self.client.post('/api/backtester/portfolios/', self._payload(),
                                   format='json').data
        self.client.patch(f"/api/backtester/portfolios/{created['id']}/",
                          {'description': 'notes'}, format='json')

        portfolio = Portfolio.objects.get(pk=created['id'])
        self.assertEqual(portfolio.holdings.count(), 2)
        self.assertEqual(portfolio.description, 'notes')

    def test_deleting_my_portfolio_works(self):
        created = self.client.post('/api/backtester/portfolios/', self._payload(),
                                   format='json').data

        response = self.client.delete(f"/api/backtester/portfolios/{created['id']}/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(Portfolio.objects.count(), 0)

    def test_deleting_another_users_portfolio_is_a_404(self):
        theirs = Portfolio.objects.create(user=_user('other@example.com'), name='Theirs')

        response = self.client.delete(f"/api/backtester/portfolios/{theirs.pk}/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Portfolio.objects.filter(pk=theirs.pk).count(), 1)


class DuplicateTests(TestCase):

    def setUp(self):
        self.user = _user()
        self.client = _client(self.user)
        self.portfolio = Portfolio.objects.create(user=self.user, name='Core',
                                                  weighting_scheme='risk_parity')
        PortfolioHolding.objects.create(portfolio=self.portfolio, symbol='AAPL',
                                        target_weight=0.5, order=0)
        PortfolioHolding.objects.create(portfolio=self.portfolio, symbol='VTI',
                                        target_weight=0.5, order=1)

    def test_duplicating_copies_settings_and_holdings(self):
        response = self.client.post(
            f"/api/backtester/portfolios/{self.portfolio.pk}/duplicate/")

        self.assertEqual(response.status_code, 201)
        copy = Portfolio.objects.get(pk=response.data['id'])
        self.assertEqual(copy.weighting_scheme, 'risk_parity')
        self.assertEqual([h.symbol for h in copy.holdings.all()], ['AAPL', 'VTI'])

    def test_the_copy_gets_a_unique_name(self):
        first = self.client.post(
            f"/api/backtester/portfolios/{self.portfolio.pk}/duplicate/").data
        second = self.client.post(
            f"/api/backtester/portfolios/{self.portfolio.pk}/duplicate/").data

        self.assertNotEqual(first['name'], second['name'])
        self.assertEqual(Portfolio.objects.filter(user=self.user).count(), 3)

    def test_duplicating_another_users_portfolio_is_a_404(self):
        theirs = Portfolio.objects.create(user=_user('other@example.com'), name='T')

        response = self.client.post(f"/api/backtester/portfolios/{theirs.pk}/duplicate/")
        self.assertEqual(response.status_code, 404)


@override_settings(FREE_TIER_BACKTEST_LIMIT=7)
class QuotaEndpointTests(TestCase):

    def setUp(self):
        self.user = _user()
        self.client = _client(self.user)

    def test_it_reports_the_allowance(self):
        response = self.client.get('/api/backtester/quota/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data,
                         {'used': 0, 'limit': 7, 'tier': 'free', 'remaining': 7})


@override_settings(CACHES=LOCMEM_CACHE)
class SymbolSearchTests(TestCase):

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.user = _user()
        self.client = _client(self.user)
        self.index = [
            {'symbol': 'AAPL', 'name': 'Apple Inc.', 'kind': 'stock'},
            {'symbol': 'VTI', 'name': 'Vanguard Total Stock Market ETF', 'kind': 'etf'},
            {'symbol': 'AAL', 'name': 'American Airlines Group', 'kind': 'stock'},
        ]

    def _search(self, query):
        from backtester import symbol_index

        with patch.object(symbol_index, 'build_symbol_index', return_value=self.index):
            return self.client.get(f"/api/backtester/search-symbols/?q={query}")

    def test_a_symbol_prefix_match_ranks_first(self):
        response = self._search('aa')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'][0]['symbol'], 'AAL')

    def test_a_name_substring_also_matches(self):
        response = self._search('vanguard')

        self.assertEqual([row['symbol'] for row in response.data['results']], ['VTI'])

    def test_an_exact_symbol_match_outranks_a_prefix_match(self):
        response = self._search('AAPL')

        self.assertEqual(response.data['results'][0]['symbol'], 'AAPL')

    def test_a_short_query_returns_nothing_rather_than_the_whole_universe(self):
        response = self._search('')

        self.assertEqual(response.data['results'], [])

    def test_results_are_capped(self):
        from backtester import symbol_index

        self.index = [{'symbol': f"AA{i}", 'name': f"Company {i}", 'kind': 'stock'}
                      for i in range(100)]
        with patch.object(symbol_index, 'build_symbol_index', return_value=self.index):
            response = self.client.get('/api/backtester/search-symbols/?q=aa')

        self.assertLessEqual(len(response.data['results']), 25)
