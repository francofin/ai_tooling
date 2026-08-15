"""API surface. The price loader is mocked everywhere -- no S3, FMP or Redis."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from backtester.models import BacktestRun, Portfolio, PortfolioHolding

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
            ('get', '/api/backtester/history/'),
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


@override_settings(FREE_TIER_BACKTEST_LIMIT=2, CACHES=LOCMEM_CACHE)
class SubmitRunTests(TestCase):

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.user = _user()
        self.client = _client(self.user)
        self.payload = {'holdings': [{'symbol': 'AAPL'}, {'symbol': 'VTI'}],
                        'rebalance_frequency': 'annual'}

    def _submit(self, payload=None):
        with patch('backtester.views.run_portfolio_backtest.delay') as enqueue:
            response = self.client.post('/api/backtester/run/',
                                        payload or self.payload, format='json')
        return response, enqueue

    def test_a_valid_request_is_queued_and_returns_a_task_id(self):
        response, enqueue = self._submit()

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data['status'], 'queued')
        self.assertTrue(response.data['task_id'])
        self.assertFalse(response.data['cached'])
        enqueue.assert_called_once()

    def test_the_engine_never_runs_in_the_request_thread(self):
        with patch('backtester.views.run_portfolio_backtest.delay') as enqueue, \
             patch('backtester.tasks.run_portfolio_backtest') as executed:
            self.client.post('/api/backtester/run/', self.payload, format='json')

        enqueue.assert_called_once()
        executed.assert_not_called()

    def test_bad_input_is_a_422_with_a_readable_message(self):
        response, enqueue = self._submit({'holdings': []})

        self.assertEqual(response.status_code, 422)
        self.assertIn('holding', response.data['detail'])
        enqueue.assert_not_called()

    def test_an_infeasible_constraint_is_rejected_before_enqueue(self):
        response, enqueue = self._submit(dict(self.payload, max_weight=0.1))

        self.assertEqual(response.status_code, 422)
        enqueue.assert_not_called()

    def test_a_repeat_request_hash_serves_the_cached_run_without_spending_quota(self):
        """§13 rule 1."""
        response, _ = self._submit()
        run = BacktestRun.objects.get(task_id=response.data['task_id'])
        run.status = BacktestRun.STATUS_COMPLETE
        run.save(update_fields=['status'])

        repeat, enqueue = self._submit()

        self.assertEqual(repeat.status_code, 200)
        self.assertTrue(repeat.data['cached'])
        self.assertEqual(repeat.data['task_id'], response.data['task_id'])
        enqueue.assert_not_called()
        self.assertEqual(BacktestRun.objects.count(), 1)

    def test_the_hash_ignores_irrelevant_key_order_and_casing(self):
        first, _ = self._submit({'holdings': [{'symbol': 'aapl'}, {'symbol': 'vti'}],
                                 'rebalance_frequency': 'annual'})
        run = BacktestRun.objects.get(task_id=first.data['task_id'])
        run.status = BacktestRun.STATUS_COMPLETE
        run.save(update_fields=['status'])

        repeat, _ = self._submit({'rebalance_frequency': 'annual',
                                  'holdings': [{'symbol': 'AAPL'}, {'symbol': 'VTI'}]})
        self.assertTrue(repeat.data['cached'])

    def test_an_exhausted_quota_is_a_402_with_upgrade_metadata(self):
        for i in range(2):
            BacktestRun.objects.create(user=self.user, task_id=f"t{i}",
                                       request_hash=f"h{i}", request={})

        response, enqueue = self._submit()

        self.assertEqual(response.status_code, 402)
        self.assertTrue(response.data['upgrade_required'])
        self.assertEqual(response.data['limit'], 2)
        enqueue.assert_not_called()

    def test_a_portfolio_id_is_attached_only_when_it_is_mine(self):
        mine = Portfolio.objects.create(user=self.user, name='Mine')
        theirs = Portfolio.objects.create(user=_user('other@example.com'), name='T')

        response, _ = self._submit(dict(self.payload, portfolio_id=mine.pk))
        self.assertEqual(BacktestRun.objects.get(
            task_id=response.data['task_id']).portfolio, mine)

        BacktestRun.objects.all().delete()
        response, _ = self._submit(dict(self.payload, portfolio_id=theirs.pk,
                                        benchmark_symbol='QQQ'))
        self.assertIsNone(BacktestRun.objects.get(
            task_id=response.data['task_id']).portfolio)


@override_settings(CACHES=LOCMEM_CACHE)
class StatusAndResultsTests(TestCase):

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.user = _user()
        self.client = _client(self.user)
        self.run = BacktestRun.objects.create(user=self.user, task_id='abc',
                                              request_hash='h', request={},
                                              progress='simulating')

    def test_status_reports_progress(self):
        response = self.client.get('/api/backtester/status/abc/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['progress'], 'simulating')

    def test_a_user_cannot_read_another_users_status(self):
        client = _client(_user('other@example.com'))

        self.assertEqual(client.get('/api/backtester/status/abc/').status_code, 404)

    def test_a_user_cannot_read_another_users_results(self):
        client = _client(_user('other@example.com'))

        self.assertEqual(client.get('/api/backtester/results/abc/').status_code, 404)

    def test_results_of_a_running_job_are_a_202(self):
        self.assertEqual(self.client.get('/api/backtester/results/abc/').status_code, 202)

    def test_results_of_a_failed_job_are_a_422_carrying_the_error(self):
        self.run.status = BacktestRun.STATUS_FAILED
        self.run.error = 'No requested asset has enough price history.'
        self.run.save(update_fields=['status', 'error'])

        response = self.client.get('/api/backtester/results/abc/')
        self.assertEqual(response.status_code, 422)
        self.assertIn('price history', response.data['detail'])

    def test_a_complete_job_returns_the_stored_payload(self):
        from backtester import results

        self.run.status = BacktestRun.STATUS_COMPLETE
        self.run.save(update_fields=['status'])
        with patch.object(results, '_write_to_s3'):
            results.store_payload(self.user.pk, 'abc', {'dates': ['2020-01-01']})

        response = self.client.get('/api/backtester/results/abc/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['dates'], ['2020-01-01'])

    def test_an_expired_payload_is_a_410_telling_the_user_to_re_run(self):
        self.run.status = BacktestRun.STATUS_COMPLETE
        self.run.save(update_fields=['status'])

        response = self.client.get('/api/backtester/results/abc/')
        self.assertEqual(response.status_code, 410)
        self.assertIn('Re-run', response.data['detail'])


class HistoryTests(TestCase):

    def setUp(self):
        self.user = _user()
        self.client = _client(self.user)
        for i in range(25):
            BacktestRun.objects.create(user=self.user, task_id=f"t{i}",
                                       request_hash=f"h{i}", request={})
        BacktestRun.objects.create(user=_user('other@example.com'), task_id='x',
                                   request_hash='x', request={})

    def test_history_is_paginated_and_scoped_to_me(self):
        response = self.client.get('/api/backtester/history/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 25)
        self.assertEqual(len(response.data['results']), 20)

    def test_page_two_holds_the_remainder(self):
        response = self.client.get('/api/backtester/history/?page=2')

        self.assertEqual(len(response.data['results']), 5)

    def test_history_carries_summaries_not_full_results(self):
        response = self.client.get('/api/backtester/history/')

        self.assertNotIn('nav', response.data['results'][0])
        self.assertIn('summary', response.data['results'][0])
