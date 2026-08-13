"""Tests for the price data layer. The single I/O seam is monkeypatched so
nothing here touches S3, FMP or Redis."""
from unittest import TestCase
from unittest.mock import patch

import pandas as pd
import pyarrow as pa

from utils.StockCalculations import GetData


class LoadStockPricesColumnsTests(TestCase):
    """`columns=` is pushed into the parquet reader, not applied afterwards."""

    def _table(self):
        return pa.table({
            'date': pd.to_datetime(['2020-01-02', '2020-01-03']),
            'adjClose': [100.0, 101.0],
            'volume': [1_000, 1_100],
        })

    def test_columns_are_passed_through_to_the_parquet_reader(self):
        getter = GetData()
        with patch('utils.StockCalculations.pq.read_table', return_value=self._table()) as reader:
            getter.load_stock_prices('AAPL', columns=['date', 'adjClose'])

        self.assertEqual(reader.call_args.kwargs['columns'], ['date', 'adjClose'])

    def test_omitting_columns_reads_every_column(self):
        getter = GetData()
        with patch('utils.StockCalculations.pq.read_table', return_value=self._table()) as reader:
            getter.load_stock_prices('AAPL')

        self.assertIsNone(reader.call_args.kwargs['columns'])

    def test_date_is_returned_as_a_string_column(self):
        getter = GetData()
        with patch('utils.StockCalculations.pq.read_table', return_value=self._table()):
            frame = getter.load_stock_prices('AAPL', columns=['date', 'adjClose'])

        self.assertIn('date', frame.columns)
        self.assertEqual(frame['date'].tolist(), ['2020-01-02', '2020-01-03'])


import numpy as np
from django.test import SimpleTestCase, override_settings

from backtester.engine import prices as prices_module
from backtester.engine.config import PriceDataUnavailable

LOCMEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'backtester-prices-tests',
    }
}


def _series(dates, values):
    return pd.Series(values, index=pd.DatetimeIndex(dates), dtype=float)


def _bdates(count, start='2020-01-01'):
    return pd.bdate_range(start, periods=count)


def _fake_loader(mapping, provenance='s3'):
    """Stand-in for the S3/FMP seam. Unknown symbols raise, as S3 does."""
    def loader(symbol):
        if symbol not in mapping:
            raise FileNotFoundError(symbol)
        return mapping[symbol], provenance
    return loader


@override_settings(CACHES=LOCMEM_CACHE)
class LoadPricePanelTests(SimpleTestCase):

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        dates = _bdates(10)
        self.mapping = {
            'A': _series(dates, np.arange(100.0, 110.0)),
            # B lists five days late: the staggered-inception case of §5.
            'B': _series(dates[5:], np.arange(50.0, 55.0)),
        }

    def test_panel_spans_the_union_of_trading_dates(self):
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader(self.mapping)):
            panel = prices_module.load_price_panel(['A', 'B'])

        self.assertEqual(len(panel.prices), 10)
        self.assertEqual(list(panel.prices.columns), ['A', 'B'])

    def test_first_and_last_valid_reflect_each_symbols_own_span(self):
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader(self.mapping)):
            panel = prices_module.load_price_panel(['A', 'B'])

        self.assertEqual(panel.first_valid['A'], panel.prices.index[0])
        self.assertEqual(panel.first_valid['B'], panel.prices.index[5])
        self.assertEqual(panel.last_valid['B'], panel.prices.index[-1])

    def test_forward_fill_never_manufactures_a_price_before_first_trade(self):
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader(self.mapping)):
            panel = prices_module.load_price_panel(['A', 'B'])

        self.assertTrue(panel.prices['B'].iloc[:5].isna().all())
        self.assertFalse(panel.prices['B'].iloc[5:].isna().any())

    def test_forward_fill_bridges_a_gap_inside_a_symbols_own_span(self):
        """A holiday one exchange keeps and another does not.

        The gap has to come from the *union* of trading dates to be meaningful:
        a date on which no requested symbol traded is not a trading date at all,
        and is correctly absent from the panel rather than forward-filled.
        """
        dates = _bdates(6)
        gappy = _series(dates, [10.0, np.nan, 12.0, np.nan, 14.0, 15.0])
        complete = _series(dates, [50.0, 51.0, 52.0, 53.0, 54.0, 55.0])
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader({'A': gappy, 'B': complete})):
            panel = prices_module.load_price_panel(['A', 'B'])

        self.assertEqual(len(panel.prices), 6)
        self.assertEqual(panel.prices['A'].tolist(), [10.0, 10.0, 12.0, 12.0, 14.0, 15.0])

    def test_a_date_no_symbol_traded_on_is_absent_rather_than_filled(self):
        dates = _bdates(4)
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader(
                              {'A': _series(dates, [10.0, np.nan, 12.0, 13.0])})):
            panel = prices_module.load_price_panel(['A'])

        self.assertEqual(len(panel.prices), 3)
        self.assertEqual(panel.prices['A'].tolist(), [10.0, 12.0, 13.0])

    def test_returns_are_simple_returns_on_adjclose(self):
        dates = _bdates(3)
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader({'A': _series(dates, [100.0, 110.0, 99.0])})):
            panel = prices_module.load_price_panel(['A'])

        returns = panel.returns()
        self.assertEqual(len(returns), 3)
        self.assertAlmostEqual(returns['A'].iloc[1], 0.10)
        self.assertAlmostEqual(returns['A'].iloc[2], -0.10)

    def test_returns_are_zero_where_a_symbol_has_no_price_yet(self):
        """A pre-inception NaN must not become a NaN return that poisons the
        portfolio return; the availability mask is what excludes the asset."""
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader(self.mapping)):
            panel = prices_module.load_price_panel(['A', 'B'])

        self.assertFalse(panel.returns().isna().any().any())
        self.assertTrue((panel.returns()['B'].iloc[:5] == 0.0).all())

    def test_fmp_fallback_provenance_is_recorded(self):
        dates = _bdates(4)

        def loader(symbol):
            return _series(dates, [1.0, 2.0, 3.0, 4.0]), 'fmp'

        with patch.object(prices_module, '_fetch_symbol_series', side_effect=loader):
            panel = prices_module.load_price_panel(['ZZZZ'])

        self.assertEqual(panel.provenance['ZZZZ'], 'fmp')

    def test_a_symbol_with_no_data_anywhere_is_recorded_as_missing(self):
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader(self.mapping)):
            panel = prices_module.load_price_panel(['A', 'NOPE'])

        self.assertIn('NOPE', panel.missing)
        self.assertNotIn('NOPE', panel.prices.columns)

    def test_every_symbol_missing_raises(self):
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader({})):
            with self.assertRaises(PriceDataUnavailable) as caught:
                prices_module.load_price_panel(['NOPE', 'ALSONOPE'])

        self.assertEqual(set(caught.exception.reasons), {'NOPE', 'ALSONOPE'})

    def test_the_second_load_of_a_symbol_comes_from_cache(self):
        loader = _fake_loader(self.mapping)
        with patch.object(prices_module, '_fetch_symbol_series', side_effect=loader) as seam:
            prices_module.load_price_panel(['A'])
            panel = prices_module.load_price_panel(['A'])

        self.assertEqual(seam.call_count, 1)
        self.assertEqual(panel.provenance['A'], 'cache')

    def test_start_and_end_trim_the_panel(self):
        dates = _bdates(10)
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader(self.mapping)):
            panel = prices_module.load_price_panel(['A'], start=dates[2].date(),
                                                   end=dates[6].date())

        self.assertEqual(panel.prices.index[0], dates[2])
        self.assertEqual(panel.prices.index[-1], dates[6])


@override_settings(CACHES=LOCMEM_CACHE)
class MaskTests(SimpleTestCase):
    """§5 -- the two boolean matrices everything about inception rests on."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        dates = _bdates(20)
        self.dates = dates
        self.mapping = {
            'A': _series(dates, np.arange(100.0, 120.0)),
            'B': _series(dates[10:], np.arange(50.0, 60.0)),
            # C stops trading early: the delisting/truncation path.
            'C': _series(dates[:14], np.arange(30.0, 44.0)),
        }

    def _panel(self):
        with patch.object(prices_module, '_fetch_symbol_series',
                          side_effect=_fake_loader(self.mapping)):
            return prices_module.load_price_panel(['A', 'B', 'C'])

    def test_available_is_true_only_inside_each_symbols_span(self):
        available = self._panel().availability()

        self.assertTrue(available['A'].all())
        self.assertFalse(available['B'].iloc[9])
        self.assertTrue(available['B'].iloc[10])
        self.assertTrue(available['C'].iloc[13])
        self.assertFalse(available['C'].iloc[14])

    def test_min_history_days_of_one_makes_eligible_equal_available(self):
        panel = self._panel()

        pd.testing.assert_frame_equal(panel.eligibility(1), panel.availability())

    def test_min_history_days_delays_eligibility_beyond_availability(self):
        eligible = self._panel().eligibility(5)

        # B is available from index 10; its fifth own trading day is index 14.
        self.assertFalse(eligible['B'].iloc[13])
        self.assertTrue(eligible['B'].iloc[14])
        self.assertTrue(eligible['A'].iloc[4])
        self.assertFalse(eligible['A'].iloc[3])

    def test_eligibility_ends_with_availability_even_once_history_is_long(self):
        eligible = self._panel().eligibility(5)

        self.assertTrue(eligible['C'].iloc[13])
        self.assertFalse(eligible['C'].iloc[14])
