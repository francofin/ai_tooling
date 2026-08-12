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
