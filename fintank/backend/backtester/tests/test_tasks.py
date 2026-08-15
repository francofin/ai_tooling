"""The Celery task and the result payload assembly."""
from unittest.mock import patch

import numpy as np
import pandas as pd
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from backtester.models import BacktestRun
from backtester.engine.prices import PricePanel

User = get_user_model()

LOCMEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'backtester-task-tests',
    }
}


def _user(email='task@example.com'):
    user = User.objects.create_user(username=email, email=email, password='sw0rdfish!x',
                                    first_name='Test', last_name='User')
    from users.models import UserProfile
    if not getattr(user, 'userprofile', None):
        UserProfile.objects.create(user=user)
    return user


def _panel(symbols=('A', 'B'), periods=800, seed=5):
    dates = pd.bdate_range('2018-01-01', periods=periods)
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame(
        {symbol: 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, periods))
         for symbol in symbols},
        index=dates)
    return PricePanel(prices=frame,
                      first_valid={c: frame.index[0] for c in frame.columns},
                      last_valid={c: frame.index[-1] for c in frame.columns},
                      provenance={c: 'test' for c in frame.columns})


def _benchmark(periods=800, seed=6):
    dates = pd.bdate_range('2018-01-01', periods=periods)
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.009, periods)),
                     index=dates)


@override_settings(CACHES=LOCMEM_CACHE)
class BuildPayloadTests(TestCase):

    def setUp(self):
        from backtester.engine.backtest import run_backtest
        from backtester.engine.config import validate_request

        self.panel = _panel()
        self.request = validate_request({
            'holdings': [{'symbol': 'A'}, {'symbol': 'B'}],
            'rebalance_frequency': 'annual', 'min_history_days': 1,
        })
        self.result = run_backtest(self.panel, self.request)

    def _payload(self, benchmark=None):
        from backtester.results import build_payload

        return build_payload(self.result, self.request, self.panel,
                             benchmark if benchmark is not None else _benchmark())

    def test_the_payload_carries_every_documented_section(self):
        payload = self._payload()

        expected = {'dates', 'nav', 'index', 'drawdown', 'returns',
                    'weights_over_time', 'effective_asset_count', 'rebalance_events',
                    'composition_events', 'benchmark_index', 'benchmark_drawdown',
                    'metrics', 'benchmark_metrics', 'diagnostics', 'frontier',
                    'effective_start', 'effective_end', 'truncation_cause',
                    'symbols', 'request', 'provenance'}
        self.assertTrue(expected.issubset(payload), expected - set(payload))

    def test_the_payload_is_json_serializable(self):
        import json

        json.dumps(self._payload())

    def test_every_series_has_the_same_length_as_dates(self):
        payload = self._payload()
        length = len(payload['dates'])

        for key in ('nav', 'index', 'drawdown', 'returns', 'effective_asset_count',
                    'benchmark_index', 'benchmark_drawdown'):
            with self.subTest(key=key):
                self.assertEqual(len(payload[key]), length)

    def test_weights_over_time_is_one_series_per_symbol(self):
        payload = self._payload()

        self.assertEqual(set(payload['weights_over_time']), {'A', 'B'})
        self.assertEqual(len(payload['weights_over_time']['A']),
                         len(payload['dates']))

    def test_the_benchmark_is_aligned_to_the_portfolio_dates(self):
        payload = self._payload()

        self.assertAlmostEqual(payload['benchmark_index'][0], 1.0, places=12)

    def test_diagnostics_always_include_survivorship_bias(self):
        codes = [f['code'] for f in self._payload()['diagnostics']]

        self.assertIn('survivorship_bias', codes)

    def test_a_missing_benchmark_leaves_the_benchmark_sections_empty(self):
        payload = self._payload(benchmark=pd.Series(dtype=float))

        self.assertEqual(payload['benchmark_index'], [])
        self.assertIsNone(payload['metrics']['beta'])


@override_settings(CACHES=LOCMEM_CACHE)
class StoreAndLoadTests(TestCase):

    def setUp(self):
        from django.core.cache import cache

        # LocMemCache is process-global and survives between test methods, so
        # without this the S3-fallback test still finds the payload the previous
        # test stored and never exercises the fallback at all.
        cache.clear()
        self.user = _user()
        self.run = BacktestRun.objects.create(user=self.user, task_id='abc123',
                                              request_hash='h', request={})

    def test_storing_writes_redis_and_returns_the_s3_key(self):
        from backtester import results

        with patch.object(results, '_write_to_s3') as writer:
            key = results.store_payload(self.user.pk, 'abc123', {'ok': True})

        self.assertEqual(key, f"backtest_results/{self.user.pk}/abc123.json")
        writer.assert_called_once()

    def test_loading_comes_from_redis_without_touching_s3(self):
        from backtester import results

        with patch.object(results, '_write_to_s3'):
            results.store_payload(self.user.pk, 'abc123', {'ok': True})

        with patch.object(results, '_read_from_s3') as reader:
            payload = results.load_payload(self.run)

        reader.assert_not_called()
        self.assertEqual(payload, {'ok': True})

    def test_loading_falls_back_to_s3_when_the_cache_has_expired(self):
        from backtester import results

        self.run.result_key = f"backtest_results/{self.user.pk}/abc123.json"
        self.run.save(update_fields=['result_key'])

        with patch.object(results, '_read_from_s3', return_value={'ok': 'from-s3'}):
            payload = results.load_payload(self.run)

        self.assertEqual(payload, {'ok': 'from-s3'})

    def test_an_s3_failure_returns_none_rather_than_raising(self):
        from backtester import results

        self.run.result_key = 'backtest_results/1/missing.json'
        self.run.save(update_fields=['result_key'])

        with patch.object(results, '_read_from_s3', side_effect=OSError('gone')):
            self.assertIsNone(results.load_payload(self.run))


@override_settings(CACHES=LOCMEM_CACHE)
class RunPortfolioBacktestTests(TestCase):

    def setUp(self):
        self.user = _user()
        self.request_payload = {
            'holdings': [{'symbol': 'A'}, {'symbol': 'B'}],
            'rebalance_frequency': 'annual', 'min_history_days': 1,
            'benchmark_symbol': 'SPY',
        }
        self.run = BacktestRun.objects.create(
            user=self.user, task_id='task-1', request_hash='hash-1',
            request=self.request_payload)

    def _execute(self, panel=None, benchmark=None):
        from backtester import tasks

        with patch.object(tasks, 'load_price_panel',
                          return_value=panel if panel is not None else _panel()), \
             patch.object(tasks, 'load_benchmark_series',
                          return_value=(benchmark if benchmark is not None
                                        else _benchmark(), 's3')), \
             patch('backtester.results._write_to_s3'):
            return tasks.run_portfolio_backtest(self.run.pk)

    def test_a_successful_run_completes_and_records_a_summary(self):
        self._execute()
        self.run.refresh_from_db()

        self.assertEqual(self.run.status, BacktestRun.STATUS_COMPLETE)
        self.assertIsNotNone(self.run.completed_at)
        self.assertIn('cagr', self.run.summary)
        self.assertTrue(self.run.result_key)
        self.assertEqual(self.run.error, '')

    def test_the_summary_holds_headline_metrics_only_not_the_series(self):
        self._execute()
        self.run.refresh_from_db()

        self.assertNotIn('nav', self.run.summary)
        self.assertNotIn('index', self.run.summary)
        self.assertLess(len(self.run.summary), 20)

    def test_the_full_payload_is_readable_afterwards(self):
        from backtester.results import load_payload

        self._execute()
        self.run.refresh_from_db()

        payload = load_payload(self.run)
        self.assertIn('diagnostics', payload)

    def test_a_price_failure_marks_the_run_failed_and_refunds_it(self):
        from backtester import tasks
        from backtester.engine.config import PriceDataUnavailable

        with patch.object(tasks, 'load_price_panel',
                          side_effect=PriceDataUnavailable('no data', {'A': 'gone'})):
            tasks.run_portfolio_backtest(self.run.pk)

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, BacktestRun.STATUS_FAILED)
        self.assertIn('no data', self.run.error)
        self.assertFalse(self.run.counted_against_quota)

    def test_an_unexpected_error_also_refunds(self):
        from backtester import tasks

        with patch.object(tasks, 'load_price_panel', side_effect=RuntimeError('boom')):
            tasks.run_portfolio_backtest(self.run.pk)

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, BacktestRun.STATUS_FAILED)
        self.assertFalse(self.run.counted_against_quota)

    def test_a_no_eligible_assets_error_is_reported_plainly(self):
        from backtester import tasks

        short = _panel(periods=5)
        # min_history_days must be *absent* for this scenario: an explicit 1
        # makes every asset eligible on day one and the five-row panel simulates
        # happily. Dropped, it defaults to lookback_days for an optimizer
        # scheme, which five rows cannot clear -- which is the failure under test.
        request = {key: value for key, value in self.request_payload.items()
                   if key != 'min_history_days'}
        self.run.request = dict(request, weighting_scheme='min_variance')
        self.run.save(update_fields=['request'])

        with patch.object(tasks, 'load_price_panel', return_value=short), \
             patch.object(tasks, 'load_benchmark_series',
                          return_value=(_benchmark(periods=5), 's3')):
            tasks.run_portfolio_backtest(self.run.pk)

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, BacktestRun.STATUS_FAILED)
        self.assertIn('history', self.run.error.lower())

    def test_a_missing_run_id_does_not_raise(self):
        from backtester import tasks

        self.assertIsNone(tasks.run_portfolio_backtest(999_999))
