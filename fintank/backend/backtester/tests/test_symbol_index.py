from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from backtester import symbol_index

LOCMEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'symbol-index-tests',
    }
}


@override_settings(CACHES=LOCMEM_CACHE)
class SymbolIndexCacheTests(SimpleTestCase):
    """A degraded typeahead build must not be cached for the full day."""

    LISTS = {key: [] for key in symbol_index.STOCK_CONSTITUENT_KEYS}
    LISTS['sp500'] = [{'asset': 'AAPL', 'name': 'Apple Inc.'}]
    LISTS['nasdaq'] = [{'asset': 'MSFT', 'name': 'Microsoft'}]
    LISTS['etfs'] = [{'symbol': 'VTI', 'name': 'Vanguard Total'}]

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.cache = cache
        self.spy = Mock(wraps=cache)
        patcher = patch.object(symbol_index, 'cache', self.spy)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _constituents(self, failing=()):
        def fetch(key):
            if key in failing:
                raise OSError(f"S3 read failed for {key}")
            return self.LISTS[key]
        return patch.object(symbol_index.data_getter, 'get_index_constituents',
                            side_effect=fetch)

    def _index_timeout(self):
        timeouts = [c.kwargs['timeout'] for c in self.spy.set.call_args_list
                    if c.args[0] == symbol_index.CACHE_KEY]
        return timeouts[-1]

    def _expire_index(self):
        self.cache.delete(symbol_index.CACHE_KEY)
        self.spy.set.reset_mock()

    def test_a_complete_build_is_cached_for_a_day(self):
        with self._constituents():
            index = symbol_index.get_symbol_index()

        self.assertEqual([row['symbol'] for row in index], ['AAPL', 'MSFT', 'VTI'])
        self.assertEqual(self._index_timeout(), symbol_index.CACHE_TIMEOUT)

    def test_a_partial_build_is_retried_once_then_cached_for_a_day(self):
        with self._constituents(failing={'etfs'}):
            symbol_index.get_symbol_index()
            self.assertEqual(self._index_timeout(), symbol_index.PARTIAL_TIMEOUT)

            self._expire_index()
            symbol_index.get_symbol_index()
            self.assertEqual(self._index_timeout(), symbol_index.CACHE_TIMEOUT)

    def test_a_missing_name_source_counts_as_degraded(self):
        self.LISTS = dict(self.LISTS, sp500=[{'asset': 'AAPL'}])
        with self._constituents(), \
             patch.object(symbol_index.data_getter, 'load_long_profiles',
                          side_effect=OSError('S3 timeout')):
            index = symbol_index.get_symbol_index()

        self.assertEqual(index[0], {'symbol': 'AAPL', 'name': '', 'kind': 'stock'})
        self.assertEqual(self._index_timeout(), symbol_index.PARTIAL_TIMEOUT)

    def test_a_total_failure_is_cached_only_briefly(self):
        failing = set(symbol_index.STOCK_CONSTITUENT_KEYS) | {'etfs'}
        with self._constituents(failing=failing) as fetch:
            self.assertEqual(symbol_index.get_symbol_index(), [])
            calls = fetch.call_count
            self.assertEqual(symbol_index.search('AA'), [])

        self.assertEqual(self._index_timeout(), symbol_index.EMPTY_TIMEOUT)
        self.assertEqual(fetch.call_count, calls)

    def test_recovery_after_a_partial_build_resets_the_retry(self):
        with self._constituents(failing={'etfs'}):
            symbol_index.get_symbol_index()
        self._expire_index()
        with self._constituents():
            symbol_index.get_symbol_index()

        self.assertEqual(self._index_timeout(), symbol_index.CACHE_TIMEOUT)
        self.assertIsNone(self.cache.get(symbol_index.PARTIAL_RETRY_KEY))
