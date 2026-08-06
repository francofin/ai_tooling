from unittest.mock import patch

import numpy as np
import pandas as pd
from django.test import SimpleTestCase, override_settings

from analyzer.analyzer_utils import index_tools

# The configured cache points at Redis db 15; these cases exercise the
# transforms, so they run against locmem and clear between tests.
LOCMEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'index-tools-tests',
    }
}


def _price_frame(dates, base=100.0, step=1.0):
    """Minimal stand-in for a metric parquet: every column the tools read."""
    n = len(dates)
    frame = pd.DataFrame({'date': dates})
    frame['adjClose'] = [base + step * i for i in range(n)]
    frame['volume'] = [1_000_000 + i for i in range(n)]
    frame['returns'] = np.linspace(0.001, 0.01, n)
    for column in index_tools.MA_COLUMNS.values():
        frame[column] = frame['adjClose'].rolling(2, min_periods=1).mean()
    for mapping in (index_tools.RETURN_COLUMNS, index_tools.VOLATILITY_COLUMNS,
                    index_tools.RETURN_TO_RISK_COLUMNS):
        for i, column in enumerate(mapping.values(), start=1):
            frame[column] = np.linspace(0.01 * i, 0.02 * i, n)
    return frame


def _dates(count, start='2020-01-01'):
    return [d.strftime('%Y-%m-%d') for d in pd.bdate_range(start, periods=count)]


@override_settings(CACHES=LOCMEM_CACHE)
class IndexPageConfigTests(SimpleTestCase):
    """The old page shipped peer lists half of which had no data behind them."""

    def test_every_slug_declares_the_required_fields(self):
        required = {'title', 'price_key', 'price_source', 'constituent_key',
                    'risk_key', 'peers'}
        for slug, config in index_tools.INDEX_PAGES.items():
            with self.subTest(slug=slug):
                self.assertTrue(required.issubset(config), f"{slug} is missing fields")
                self.assertIn(config['price_source'], ('index', 'etf'))
                self.assertTrue(config['peers'], f"{slug} has no peers")

    def test_every_peer_key_resolves_to_a_real_index(self):
        for slug, config in index_tools.INDEX_PAGES.items():
            for peer_key in config['peers']:
                with self.subTest(slug=slug, peer=peer_key):
                    self.assertIn(peer_key, index_tools.index_mappers)

    def test_no_slug_lists_itself_or_repeats_a_peer(self):
        for slug, config in index_tools.INDEX_PAGES.items():
            with self.subTest(slug=slug):
                self.assertEqual(len(config['peers']), len(set(config['peers'])))
                self.assertNotIn(config['price_key'], config['peers'])

    def test_constituent_keys_are_known_to_the_data_getter(self):
        valid = set(index_tools.data_getter.constituent_maps)
        for slug, config in index_tools.INDEX_PAGES.items():
            with self.subTest(slug=slug):
                self.assertIn(config['constituent_key'], valid)

    def test_unknown_slug_raises_key_error(self):
        with self.assertRaises(KeyError):
            index_tools.get_index_page_config('dow')

    def test_peers_drop_keys_with_no_parquet(self):
        with patch.dict(index_tools.INDEX_PAGES['sp500'],
                        {'peers': ['vix', 'not_a_real_index']}):
            keys = [peer['key'] for peer in index_tools.get_index_peers('sp500')]
        self.assertEqual(keys, ['vix'])


class SeriesHelperTests(SimpleTestCase):

    def test_nan_becomes_none_and_values_are_rounded(self):
        column = pd.Series([1.123456789, float('nan'), 2.0])
        self.assertEqual(index_tools._series_to_json(column), [1.123457, None, 2.0])

    def test_trim_keeps_only_the_requested_years(self):
        frame = pd.DataFrame({'date': _dates(1200, start='2015-01-01')})
        trimmed = index_tools._trim_to_years(frame, 1)
        span = (pd.to_datetime(trimmed['date'].iloc[-1])
                - pd.to_datetime(trimmed['date'].iloc[0])).days
        self.assertLessEqual(span, 366)
        self.assertEqual(trimmed['date'].iloc[-1], frame['date'].iloc[-1])

    def test_available_drops_columns_the_parquet_lacks(self):
        frame = pd.DataFrame({'10_day_ma': [1.0], '20_day_ma': [1.0]})
        self.assertEqual(index_tools._available(frame, index_tools.MA_COLUMNS),
                         {'ma_10': '10_day_ma', 'ma_20': '20_day_ma'})

    def test_symbol_batches_stay_under_the_limit_and_lose_nothing(self):
        symbols = [f'SYM{i}' for i in range(500)]
        batches = index_tools._batch_symbols(symbols, max_length=100)
        self.assertTrue(all(len(batch) <= 100 for batch in batches))
        self.assertEqual(','.join(batches).split(','), symbols)


class PeriodPerformanceTests(SimpleTestCase):
    """Header ribbon, derived from the price series instead of a browser-side
    FMP call with the API key in the bundle."""

    def test_percent_change_over_each_window(self):
        dates = _dates(300)
        closes = [100.0] * 299 + [110.0]
        performance = index_tools._period_performance(dates, closes)
        self.assertAlmostEqual(performance['1D'], 10.0, places=4)
        self.assertAlmostEqual(performance['1Y'], 10.0, places=4)

    def test_ytd_uses_last_close_of_the_prior_year(self):
        dates = ['2025-12-30', '2025-12-31', '2026-01-02', '2026-01-05']
        closes = [50.0, 100.0, 105.0, 120.0]
        performance = index_tools._period_performance(dates, closes)
        self.assertAlmostEqual(performance['YTD'], 20.0, places=4)

    def test_windows_longer_than_the_history_are_omitted(self):
        dates = _dates(10)
        performance = index_tools._period_performance(dates, [100.0] * 10)
        self.assertIn('5D', performance)
        self.assertNotIn('1Y', performance)

    def test_too_short_a_series_returns_nothing(self):
        self.assertEqual(index_tools._period_performance(['2026-01-02'], [100.0]), {})


class RollingBetaTests(SimpleTestCase):

    def test_beta_of_a_doubled_series_is_two(self):
        rng = np.random.default_rng(7)
        peer = pd.Series(rng.normal(0, 0.01, 300))
        base = peer * 2
        beta = index_tools._rolling_beta(base, peer, 30)
        self.assertAlmostEqual(beta.iloc[-1], 2.0, places=6)

    def test_beta_is_null_before_the_window_fills(self):
        rng = np.random.default_rng(7)
        peer = pd.Series(rng.normal(0, 0.01, 100))
        beta = index_tools._rolling_beta(peer, peer, 30)
        self.assertTrue(beta.iloc[:29].isna().all())
        self.assertAlmostEqual(beta.iloc[-1], 1.0, places=6)

    def test_flat_peer_gives_null_not_infinity(self):
        peer = pd.Series([0.0] * 60)
        base = pd.Series(np.linspace(0, 0.01, 60))
        beta = index_tools._rolling_beta(base, peer, 30)
        self.assertTrue(beta.isna().all())


@override_settings(CACHES=LOCMEM_CACHE)
class ComparisonTests(SimpleTestCase):

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def _run(self, base_frame, peer_frame, slug='sp500', peer_key='vix', years=5):
        with patch.object(index_tools, '_load_price_frame', return_value=base_frame), \
             patch.object(index_tools.data_getter, 'load_index_parquet', return_value=peer_frame):
            return index_tools.get_index_comparison(slug, peer_key, years=years)

    def test_spreads_are_base_minus_peer(self):
        dates = _dates(400)
        base, peer = _price_frame(dates), _price_frame(dates)
        peer[index_tools.RETURN_COLUMNS['ret_30']] = (
            peer[index_tools.RETURN_COLUMNS['ret_30']] - 0.005)

        payload = self._run(base, peer)
        spread = payload['metrics']['return_spread']['ret_30']
        self.assertTrue(all(abs(v - 0.005) < 1e-6 for v in spread))

    def test_only_overlapping_dates_survive(self):
        base = _price_frame(_dates(300, start='2020-01-01'))
        peer = _price_frame(_dates(300, start='2020-06-01'))

        payload = self._run(base, peer)
        overlap = set(base['date']) & set(peer['date'])
        self.assertEqual(len(payload['dates']), len(overlap))
        self.assertTrue(set(payload['dates']).issubset(overlap))

    def test_price_levels_carry_both_sides_for_the_vix_chart(self):
        dates = _dates(300)
        payload = self._run(_price_frame(dates), _price_frame(dates, base=20.0))
        price = payload['metrics']['price']['adjClose']
        self.assertEqual(set(price), {'base', 'peer'})
        self.assertEqual(len(price['peer']), len(payload['dates']))
        self.assertNotEqual(price['base'][-1], price['peer'][-1])

    def test_moving_averages_carry_both_sides(self):
        dates = _dates(300)
        payload = self._run(_price_frame(dates), _price_frame(dates, base=50.0))
        ma = payload['metrics']['moving_average']['ma_10']
        self.assertEqual(set(ma), {'base', 'peer'})
        self.assertEqual(len(ma['base']), len(payload['dates']))
        self.assertNotEqual(ma['base'][-1], ma['peer'][-1])

    def test_every_series_is_the_same_length_as_dates(self):
        dates = _dates(800)
        payload = self._run(_price_frame(dates), _price_frame(dates), years=1)
        expected = len(payload['dates'])
        for family, series_map in payload['metrics'].items():
            for key, values in series_map.items():
                with self.subTest(family=family, metric=key):
                    if isinstance(values, dict):
                        self.assertEqual(len(values['base']), expected)
                        self.assertEqual(len(values['peer']), expected)
                    else:
                        self.assertEqual(len(values), expected)

    def test_beta_survives_trimming_with_values_at_the_first_visible_date(self):
        """Rolling maths runs on full history, so a trimmed window is not null
        at its left edge -- the reason trimming happens last."""
        dates = _dates(900)
        payload = self._run(_price_frame(dates), _price_frame(dates, base=80.0), years=1)
        beta = payload['metrics']['beta']['beta_120']
        self.assertIsNotNone(beta[0])

    def test_missing_columns_are_skipped_not_nulled(self):
        dates = _dates(300)
        base = _price_frame(dates).drop(columns=[index_tools.RETURN_COLUMNS['ret_3y']])
        payload = self._run(base, _price_frame(dates))
        self.assertNotIn('ret_3y', payload['metrics']['return_spread'])
        self.assertIn('ret_30', payload['metrics']['return_spread'])

    def test_unknown_peer_raises_key_error(self):
        dates = _dates(50)
        with self.assertRaises(KeyError):
            self._run(_price_frame(dates), _price_frame(dates), peer_key='not_an_index')

    def test_no_overlap_raises_key_error(self):
        base = _price_frame(_dates(50, start='2010-01-01'))
        peer = _price_frame(_dates(50, start='2020-01-01'))
        with self.assertRaises(KeyError):
            self._run(base, peer)

    def test_result_is_served_from_cache_on_the_second_call(self):
        dates = _dates(200)
        base, peer = _price_frame(dates), _price_frame(dates)
        with patch.object(index_tools, '_load_price_frame', return_value=base) as loader, \
             patch.object(index_tools.data_getter, 'load_index_parquet', return_value=peer):
            index_tools.get_index_comparison('sp500', 'vix')
            index_tools.get_index_comparison('sp500', 'vix')
        self.assertEqual(loader.call_count, 1)


@override_settings(CACHES=LOCMEM_CACHE)
class RiskTests(SimpleTestCase):

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    @staticmethod
    def _frame():
        return pd.DataFrame({
            'symbol': ['AAA', 'BBB', 'CCC'],
            'weight': [0.05, 0.03, 0.01],
            'annualized_vol': [0.4, 0.3, 0.2],
            'contr_to_vol': [0.02, 0.01, 0.005],
            'pct_contr_to_vol': [0.10, 0.05, 0.02],
            'period_return': [0.2, 0.4, 0.1],
            'contr_to_return': [0.01, 0.012, 0.001],
            'window_days': [90, 90, 90],
            'as_of': ['2026-07-31'] * 3,
        })

    def test_sections_are_sorted_independently(self):
        with patch.object(index_tools.data_getter, 'load_contr_to_var', return_value=self._frame()):
            payload = index_tools.get_index_risk('sp500')

        self.assertEqual([r['symbol'] for r in payload['contribution_to_volatility']],
                         ['AAA', 'BBB', 'CCC'])
        self.assertEqual([r['symbol'] for r in payload['period_return']],
                         ['BBB', 'AAA', 'CCC'])
        self.assertEqual(payload['as_of'], '2026-07-31')
        self.assertEqual(payload['window_days'], 90)
        self.assertEqual(payload['constituent_count'], 3)

    def test_limit_is_honoured(self):
        with patch.object(index_tools.data_getter, 'load_contr_to_var', return_value=self._frame()):
            payload = index_tools.get_index_risk('sp500', limit=2)
        self.assertEqual(len(payload['contribution_to_volatility']), 2)

    def test_empty_snapshot_raises_key_error(self):
        with patch.object(index_tools.data_getter, 'load_contr_to_var', return_value=pd.DataFrame()):
            with self.assertRaises(KeyError):
                index_tools.get_index_risk('sp500')


@override_settings(CACHES=LOCMEM_CACHE)
class QuotesTests(SimpleTestCase):

    CONSTITUENTS = [{'asset': 'AAA'}, {'asset': 'BBB'}, {'asset': 'CCC'}, {'asset': None}]
    QUOTES = [
        {'symbol': 'AAA', 'name': 'Alpha', 'pe': 30.0, 'eps': 2.0,
         'changesPercentage': -1.5, 'price': 60.0, 'marketCap': 1e9},
        {'symbol': 'BBB', 'name': 'Beta', 'pe': 10.0, 'eps': 5.0,
         'changesPercentage': 3.2, 'price': 50.0, 'marketCap': 2e9},
        {'symbol': 'CCC', 'name': 'Gamma', 'pe': None, 'eps': None,
         'changesPercentage': 0.4, 'price': 10.0, 'marketCap': 3e8},
        {'symbol': 'DDD', 'name': 'Delta', 'pe': -500.0, 'eps': -0.02,
         'changesPercentage': 1.0, 'price': 5.0, 'marketCap': 1e8},
    ]

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def _run(self, quotes=None):
        class _Response:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        with patch.object(index_tools.data_getter, 'get_index_constituents',
                          return_value=self.CONSTITUENTS), \
             patch.object(index_tools.requests, 'get',
                          return_value=_Response(self.QUOTES if quotes is None else quotes)), \
             patch.object(index_tools, 'is_market_open_now', return_value=False):
            return index_tools.get_index_quotes('sp500')

    def test_movers_are_ranked_by_change(self):
        payload = self._run()
        self.assertEqual(payload['top_performers'][0]['symbol'], 'BBB')
        self.assertEqual(payload['bottom_performers'][0]['symbol'], 'AAA')

    def test_valuations_are_pe_ascending_and_exclude_null_and_negative_pe(self):
        """A negative multiple is no earnings, not a bargain -- the old view
        sorted it to the top of the table."""
        payload = self._run()
        self.assertEqual([r['symbol'] for r in payload['valuations']], ['BBB', 'AAA'])

    def test_payload_carries_the_fields_the_table_renders(self):
        payload = self._run()
        self.assertEqual(set(payload['valuations'][0]),
                         {'symbol', 'name', 'pe', 'eps', 'changesPercentage',
                          'price', 'marketCap'})

    def test_no_quotes_raises_key_error(self):
        with self.assertRaises(KeyError):
            self._run(quotes=[])


@override_settings(CACHES=LOCMEM_CACHE)
class FactorRankTests(SimpleTestCase):
    """Decile packs for /factor-performance, from the factor_metrics parquet."""

    SECTORS = ['Technology', 'Energy', 'Utilities']

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    @classmethod
    def _frame(cls, n=120):
        rng = np.random.default_rng(3)
        return pd.DataFrame({
            'symbol': [f'S{i:04d}' for i in range(n)],
            'name': [f'Name {i}' for i in range(n)],
            'sector': [cls.SECTORS[i % len(cls.SECTORS)] for i in range(n)],
            'as_of': ['2026-08-05'] * n,
            '1M': rng.normal(0, 5, n), '3M': rng.normal(0, 8, n),
            '6M': rng.normal(0, 12, n), 'ytd': rng.normal(0, 15, n),
            '1MSTD': rng.uniform(0.005, 0.03, n),
            '3MSTD': rng.uniform(0.005, 0.03, n),
            '6MSTD': rng.uniform(0.005, 0.03, n),
            'YTDSTD': rng.uniform(0.005, 0.03, n),
            'beta': rng.uniform(0.4, 2.0, n),
            'div_yield': rng.uniform(0, 6, n), 'pe': rng.uniform(5, 60, n),
            'pb': rng.uniform(0.5, 20, n), 'psales': rng.uniform(0.5, 15, n),
            'pcf': rng.uniform(2, 40, n), 'roe': rng.uniform(-0.2, 1.5, n),
            'cfd': rng.uniform(0, 3, n), 'debt_equity': rng.uniform(0, 4, n),
            'fcf': rng.uniform(-5, 20, n),
        })

    def _run(self, frame=None, frequency='1M', universe='sp500'):
        from analyzer.analyzer_utils import factor_tools
        with patch.object(factor_tools.data_getter, 'load_factor_metrics',
                          return_value=self._frame() if frame is None else frame):
            return factor_tools.get_factor_ranks(frequency, universe)

    def test_pack_carries_every_key_the_page_reads_and_no_interest_coverage(self):
        from analyzer.analyzer_utils import factor_tools
        payload = self._run()
        expected = {'pe', 'ps', 'pb', 'pcf', 'div', 'fcf', 'roe', 'de', 'cfd',
                    'beta', 'stdevone', 'stdevthree', 'stdevsix', 'stdevytd',
                    'sectors'}
        self.assertEqual(set(payload['data']), expected)
        self.assertNotIn('int_cov', payload['data'])
        self.assertEqual(set(factor_tools.FACTOR_COLUMNS), expected)

    def test_each_pack_has_the_four_fields_the_charter_reads(self):
        for key, pack in self._run()['data'].items():
            with self.subTest(metric=key):
                self.assertEqual(set(pack),
                                 {'buckets', 'values', 'bucket_holdings', 'bucket_keys'})
                self.assertEqual(len(pack['buckets']), len(pack['values']))
                self.assertEqual(pack['bucket_keys'], pack['buckets'])

    def test_no_stock_is_dropped_from_the_last_bucket(self):
        """The legacy loop sliced before deciding to jump i to len(data), so a
        remainder tail landed in no bucket at all."""
        frame = self._frame(n=205)
        pack = self._run(frame=frame)['data']['pe']
        total = sum(len(v) for v in pack['bucket_holdings'].values())
        self.assertEqual(total, 205)

    def test_ten_buckets_above_a_hundred_rows_and_five_at_or_below(self):
        """Two universes, so the second call cannot hit the first's cache entry."""
        self.assertEqual(
            len(self._run(frame=self._frame(n=205), universe='sp500')['data']['pe']['buckets']), 10)
        self.assertEqual(
            len(self._run(frame=self._frame(n=80), universe='nas')['data']['pe']['buckets']), 5)

    def test_beta_buckets_rank_on_beta_not_price_to_cash_flow(self):
        """Every legacy frequency method read beta = self.get_pcf_metrics(...)."""
        frame = self._frame()
        payload = self._run(frame=frame)['data']
        beta_top = [s['metric'] for s in payload['beta']['bucket_holdings']['Q1']]
        pcf_top = [s['metric'] for s in payload['pcf']['bucket_holdings']['Q1']]
        self.assertNotEqual(beta_top, pcf_top)
        self.assertAlmostEqual(max(beta_top), frame['beta'].max(), places=6)

    def test_bucket_value_is_the_equal_weighted_mean_return(self):
        """prod(1 + w*r) - 1 compounds one asset across time; aggregating many
        assets within one period is a weighted sum."""
        frame = self._frame(n=20)
        pack = self._run(frame=frame)['data']['pe']
        top = pack['bucket_holdings']['Q1']
        expected = sum(s['return'] for s in top) / len(top) / 100
        self.assertAlmostEqual(pack['values'][0], round(expected * 100, 2), places=2)

    def test_buckets_are_ordered_by_the_metric_descending(self):
        pack = self._run()['data']['pe']
        first = [s['metric'] for s in pack['bucket_holdings']['Q1']]
        last = [s['metric'] for s in pack['bucket_holdings'][pack['buckets'][-1]]]
        self.assertGreater(min(first), max(last))

    def test_nulls_are_dropped_per_metric_not_per_row(self):
        """One null pe must not remove the stock from the roe chart."""
        frame = self._frame(n=120)
        frame.loc[0, 'pe'] = np.nan
        payload = self._run(frame=frame)['data']
        pe_count = sum(len(v) for v in payload['pe']['bucket_holdings'].values())
        roe_count = sum(len(v) for v in payload['roe']['bucket_holdings'].values())
        self.assertEqual(pe_count, 119)
        self.assertEqual(roe_count, 120)

    def test_a_column_too_sparse_to_bucket_returns_an_empty_pack(self):
        """The legacy int(len/5) == 0 path raised ZeroDivisionError."""
        frame = self._frame(n=120)
        frame['cfd'] = np.nan
        frame.loc[:1, 'cfd'] = [1.0, 2.0]
        pack = self._run(frame=frame)['data']['cfd']
        self.assertEqual(pack['buckets'], [])
        self.assertEqual(pack['bucket_holdings'], {})

    def test_sectors_are_grouped_not_bucketed(self):
        pack = self._run()['data']['sectors']
        self.assertEqual(sorted(pack['buckets']), sorted(self.SECTORS))

    def test_unknown_universe_and_frequency_raise_key_error(self):
        from analyzer.analyzer_utils import factor_tools
        with self.assertRaises(KeyError):
            factor_tools.get_factor_ranks('1M', 'not_a_universe')
        with self.assertRaises(KeyError):
            factor_tools.get_factor_ranks('9M', 'sp500')

    def test_empty_snapshot_raises_key_error(self):
        with self.assertRaises(KeyError):
            self._run(frame=pd.DataFrame())

    def test_result_is_served_from_cache_on_the_second_call(self):
        from analyzer.analyzer_utils import factor_tools
        with patch.object(factor_tools.data_getter, 'load_factor_metrics',
                          return_value=self._frame()) as loader:
            factor_tools.get_factor_ranks('1M', 'sp500')
            factor_tools.get_factor_ranks('1M', 'sp500')
        self.assertEqual(loader.call_count, 1)
