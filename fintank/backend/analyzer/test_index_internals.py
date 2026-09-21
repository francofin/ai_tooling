"""Pure index-internals extraction. No Django, no S3, no Redis -- hand-built
frames, following the test_technical_indicators.py convention.

The internals live in the same parquet get_index_series already opens: 32 of the
51 columns are {30,60,90,120,1_yr,3_yr} x {volatility, return_to_risk,
number_of_up_days, number_of_down_days, up_down_days}. Only the latest row is
wanted -- the strip is a snapshot, and shipping six more full series would bloat
a payload that is inlined into the page by getServerSideProps.
"""
from unittest import TestCase

import numpy as np
import pandas as pd

from analyzer.analyzer_utils import index_tools as it


def frame(rows):
    """Rows of {column: value}, oldest first, with a date column."""
    df = pd.DataFrame(rows)
    df.insert(0, 'date', [f'2026-08-{i + 1:02d}' for i in range(len(rows))])
    return df


def full_row(**overrides):
    """One row carrying every column the three displayed windows read."""
    row = {
        '30_day_volatility': 0.20, '30_day_return_to_risk': 1.10,
        'number_of_up_days_30': 12, 'number_of_down_days_30': 8, 'up_down_days_30': 1.5,
        '90_day_volatility': 0.18, '90_day_return_to_risk': 0.90,
        'number_of_up_days_90': 35, 'number_of_down_days_90': 25, 'up_down_days_90': 1.4,
        '1_yr_volatility': 0.16, '1_yr_return_to_risk': 1.30,
        'number_of_up_days_1_yr': 140, 'number_of_down_days_1_yr': 110,
        'up_down_days_1_yr': 1.2727,
    }
    row.update(overrides)
    return row


def window(payload, key):
    for entry in payload:
        if entry['key'] == key:
            return entry
    raise AssertionError(f'window {key} not in {[e["key"] for e in payload]}')


class ExtractionTests(TestCase):

    def test_the_latest_row_is_used_not_the_first(self):
        df = frame([
            full_row(**{'30_day_volatility': 0.99}),
            full_row(**{'30_day_volatility': 0.11}),
        ])
        self.assertAlmostEqual(window(it._latest_internals(df), '30')['volatility'], 0.11)

    def test_all_three_windows_are_returned_in_order(self):
        payload = it._latest_internals(frame([full_row()]))
        self.assertEqual([e['key'] for e in payload], ['30', '90', '1_yr'])

    def test_each_window_carries_its_five_metrics(self):
        entry = window(it._latest_internals(frame([full_row()])), '90')
        self.assertAlmostEqual(entry['volatility'], 0.18)
        self.assertAlmostEqual(entry['return_to_risk'], 0.90)
        self.assertEqual(entry['up_days'], 35)
        self.assertEqual(entry['down_days'], 25)
        self.assertAlmostEqual(entry['up_down_ratio'], 1.4)

    def test_the_year_window_reads_the_1_yr_column_names(self):
        """Naming is asymmetric: `30_day_volatility` but `1_yr_volatility`.
        Building the column name from a single f-string pattern silently yields
        None for the long window."""
        entry = window(it._latest_internals(frame([full_row()])), '1_yr')
        self.assertAlmostEqual(entry['volatility'], 0.16)
        self.assertEqual(entry['up_days'], 140)

    def test_day_counts_come_back_as_ints_not_floats(self):
        entry = window(it._latest_internals(frame([full_row()])), '30')
        self.assertIsInstance(entry['up_days'], int)
        self.assertIsInstance(entry['down_days'], int)


class MissingDataTests(TestCase):

    def test_a_missing_column_becomes_none_rather_than_raising(self):
        row = full_row()
        del row['90_day_return_to_risk']
        entry = window(it._latest_internals(frame([row])), '90')
        self.assertIsNone(entry['return_to_risk'])
        self.assertAlmostEqual(entry['volatility'], 0.18)

    def test_a_window_with_no_columns_at_all_is_omitted(self):
        row = {k: v for k, v in full_row().items() if not k.startswith('1_yr')
               and not k.endswith('_1_yr')}
        payload = it._latest_internals(frame([row]))
        self.assertEqual([e['key'] for e in payload], ['30', '90'])

    def test_infinite_up_down_ratio_never_reaches_the_payload(self):
        """A window with zero down days divides by zero. json_safe's docstring
        records this exact column family doing it on a placid bond ETF."""
        df = frame([full_row(**{'up_down_days_30': np.inf, 'number_of_down_days_30': 0})])
        entry = window(it._latest_internals(df), '30')
        self.assertIsNone(entry['up_down_ratio'])
        self.assertEqual(entry['down_days'], 0)

    def test_nan_metrics_become_none(self):
        df = frame([full_row(**{'30_day_volatility': np.nan})])
        self.assertIsNone(window(it._latest_internals(df), '30')['volatility'])

    def test_an_empty_frame_returns_an_empty_list(self):
        self.assertEqual(it._latest_internals(pd.DataFrame()), [])

    def test_a_frame_with_no_internals_columns_returns_an_empty_list(self):
        df = pd.DataFrame({'date': ['2026-08-01'], 'adjClose': [100.0]})
        self.assertEqual(it._latest_internals(df), [])

    def test_payload_carries_no_nan_or_inf_anywhere(self):
        df = frame([full_row(**{'30_day_volatility': np.nan, 'up_down_days_90': np.inf})])
        payload = it._latest_internals(df)
        for entry in payload:
            for key, value in entry.items():
                if isinstance(value, float):
                    self.assertTrue(np.isfinite(value), f'{entry["key"]}.{key} = {value}')

    def test_payload_is_json_serialisable(self):
        import json
        json.dumps(it._latest_internals(frame([full_row()])))
