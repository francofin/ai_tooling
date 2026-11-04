"""No client response, log line or stored error may carry the FMP key.

`raise_for_status()` puts the whole URL in its message, and the URLs carry
`apikey=`, so any exception text can hold the key.
"""
import contextlib
import io
from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings

LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                            'LOCATION': 'error-disclosure-tests'}}

LEAKY_MESSAGE = '403 Client Error for url: https://fmp.example/stable/x?apikey=SECRET'


def leaky_http_error():
    return requests.HTTPError(LEAKY_MESSAGE)


@override_settings(CACHES=LOCMEM_CACHE)
class ServerErrorResponseTests(SimpleTestCase):
    """Each entry: (url, dotted fetcher to break, expected status)."""

    CORE = 'analyzer.analyzer_utils.CorePerformanceTools'
    INDEX = 'analyzer.analyzer_utils.index_tools'
    CASES = [
        ('/api/sector-industry/nyse/', f'{CORE}.get_sector_performance_snapshot', 500),
        ('/api/stock-prices/AAPL/', f'{CORE}.get_stock_price_data', 500),
        ('/api/financial-statements/AAPL/income_statements/',
         f'{CORE}.get_financial_statements_resolved', 500),
    ]

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def _assert_clean(self, url, fetcher, expected_status):
        with patch(fetcher, side_effect=leaky_http_error()), \
                self.assertLogs('analyzer.views', level='ERROR') as logs:
            response = Client().get(url)
        self.assertEqual(response.status_code, expected_status, url)
        self.assertNotIn('SECRET', response.content.decode(), url)
        self.assertNotIn('apikey', response.content.decode(), url)
        output = '\n'.join(logs.output)
        self.assertIn('HTTPError', output)
        self.assertNotIn('SECRET', output)

    def test_public_views_never_return_the_exception_text(self):
        for url, fetcher, expected_status in self.CASES:
            with self.subTest(url=url):
                self._assert_clean(url, fetcher, expected_status)

    def test_the_cold_economic_data_path_keeps_its_503(self):
        self._assert_clean('/api/economic-data/', f'{self.CORE}.get_economic_data', 503)

    def test_the_sector_view_keeps_the_error_key_its_callers_read(self):
        with patch(f'{self.CORE}.get_sector_performance_snapshot', side_effect=leaky_http_error()):
            response = Client().get('/api/sector-industry/nyse/')
        self.assertIn('error', response.json())

    def test_a_4xx_branch_does_not_pass_a_url_through(self):
        """requests' InvalidURL is a ValueError, so it lands in the 400 branch."""
        error = requests.exceptions.InvalidURL(LEAKY_MESSAGE)
        with patch('analyzer.analyzer_utils.technicals.get_technicals', side_effect=error):
            response = Client().get('/api/technicals/AAPL/')
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('SECRET', response.content.decode())

    def test_a_4xx_branch_keeps_a_message_written_for_the_user(self):
        error = ValueError("Unknown indicator 'nope'.")
        with patch('analyzer.analyzer_utils.technicals.get_technicals', side_effect=error):
            response = Client().get('/api/technicals/AAPL/')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail'], "Unknown indicator 'nope'.")


@override_settings(CACHES=LOCMEM_CACHE)
class NewsAndJournalTests(SimpleTestCase):

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_news_does_not_return_the_exception_text(self):
        from news import views
        with patch.object(views.all_news_articles, 'cache_single_article',
                          side_effect=leaky_http_error()):
            response = Client().get('/api/get_articles/markets/')
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('SECRET', response.content.decode())

    def test_the_journal_does_not_return_storage_errors(self):
        from journal import views
        from journal.article_store import ArticleStoreUnavailable
        error = ArticleStoreUnavailable('AccessDenied on s3://private-bucket/index.json')
        with patch.object(views, 'get_article_index', side_effect=error):
            response = Client().get('/api/journals/')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private-bucket', response.content.decode())
        self.assertEqual(response.json()['indexes'], [])


class LogAndPrintTests(SimpleTestCase):

    def test_the_heat_map_batch_print_omits_the_exception_text(self):
        from utils import StockCalculations
        getter = StockCalculations.GetData()
        stdout = io.StringIO()
        with patch.object(getter, 'get_index_constituents', return_value=[{'asset': 'AAPL'}]), \
                patch.object(StockCalculations.requests, 'get', side_effect=leaky_http_error()), \
                contextlib.redirect_stdout(stdout):
            try:
                getter.get_heat_map_data('sp500')
            except Exception:  # noqa: BLE001 - only the print matters here
                pass
        self.assertNotIn('SECRET', stdout.getvalue())

    def test_the_heat_map_fmp_call_has_a_timeout(self):
        from utils import StockCalculations
        getter = StockCalculations.GetData()
        with patch.object(getter, 'get_index_constituents', return_value=[{'asset': 'AAPL'}]), \
                patch.object(StockCalculations.requests, 'get',
                             side_effect=requests.ConnectionError('down')) as get, \
                contextlib.redirect_stdout(io.StringIO()):
            try:
                getter.get_heat_map_data('sp500')
            except Exception:  # noqa: BLE001 - only the call matters here
                pass
        get.assert_called()
        self.assertTrue(get.call_args.kwargs.get('timeout'))

    @override_settings(CACHES=LOCMEM_CACHE)
    def test_index_quotes_print_omits_the_exception_text(self):
        from django.core.cache import cache
        from analyzer.analyzer_utils import index_tools
        stdout = io.StringIO()
        cache.clear()
        with patch.object(index_tools.data_getter, 'get_index_constituents',
                             return_value=[{'asset': 'AAPL'}]), \
                patch.object(index_tools.requests, 'get', side_effect=requests.ConnectionError(LEAKY_MESSAGE)), \
                contextlib.redirect_stdout(stdout):
            with self.assertRaises(KeyError):
                index_tools.get_index_quotes('sp500')
        self.assertIn('ConnectionError', stdout.getvalue())
        self.assertNotIn('SECRET', stdout.getvalue())

    @override_settings(CACHES=LOCMEM_CACHE)
    def test_statement_fallback_logs_and_raises_without_the_exception_text(self):
        from analyzer.analyzer_utils import CorePerformanceTools as tools, universe_lookup
        with patch.object(universe_lookup, 'resolve_universes', return_value=['sp500']), \
                patch.object(tools, 'get_financial_statements', side_effect=leaky_http_error()), \
                self.assertLogs('analyzer.analyzer_utils.CorePerformanceTools', level='WARNING') as logs, \
                self.assertRaises(RuntimeError) as ctx:
            tools.get_financial_statements_resolved('AAPL', 'income_statements')
        self.assertNotIn('SECRET', str(ctx.exception))
        self.assertNotIn('SECRET', '\n'.join(logs.output))


@override_settings(CACHES=LOCMEM_CACHE)
class BacktesterDisclosureTests(TestCase):

    def test_an_unexpected_failure_stores_no_exception_text(self):
        from backtester import tasks
        from backtester.models import BacktestRun
        user = get_user_model().objects.create_user(
            username='disclosure', email='disclosure@example.test', password='x',
            first_name='Dis', last_name='Closure')
        run = BacktestRun.objects.create(
            user=user, task_id='disclosure', request_hash='h',
            request={'holdings': [{'symbol': 'A'}], 'rebalance_frequency': 'annual'})
        with patch.object(tasks, 'load_price_panel', side_effect=leaky_http_error()), \
                self.assertLogs('backtester.tasks', level='ERROR') as logs:
            tasks.run_portfolio_backtest(run.pk)
        run.refresh_from_db()
        self.assertEqual(run.status, BacktestRun.STATUS_FAILED)
        self.assertNotIn('SECRET', run.error)
        self.assertIn('HTTPError', '\n'.join(logs.output))
        self.assertNotIn('SECRET', '\n'.join(logs.output))

    def test_a_missing_symbol_reason_holds_no_exception_text(self):
        from backtester.engine import prices
        with patch.object(prices, '_load_symbol_cached', side_effect=leaky_http_error()), \
                self.assertRaises(prices.PriceDataUnavailable) as ctx:
            prices.load_price_panel(['AAA'])
        self.assertNotIn('SECRET', str(ctx.exception.reasons))
        self.assertNotIn('SECRET', str(ctx.exception))
