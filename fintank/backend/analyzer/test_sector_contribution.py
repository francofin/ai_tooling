"""Pure sector-contribution arithmetic. No Django, no S3, no Redis -- hand-built
frames with numbers checkable on paper, following the test_technical_indicators.py
convention.

The maths under test: an index's return is the weighted sum of its constituents'
returns, so a sector's *contribution* is its members' weights times their returns,
expressed in percentage points of index return. That is a different question from
the equal-weighted sector average already served by factor_tools._sector_pack(),
which answers "how did the typical stock in this sector do" rather than "how much
did this sector move the index".
"""
from unittest import TestCase

import numpy as np
import pandas as pd

from analyzer.analyzer_utils import index_tools as it


def frames(rows, weights_sum_override=None):
    """Build the two frames the real loaders return, from one list of tuples.

    rows: (symbol, sector, weight, ytd, one_month)
    Mirrors the real column names: constituents use `asset`/`weightPercentage`,
    factor_metrics uses `symbol`/`sector`/`ytd`/`1M`.
    """
    constituents = pd.DataFrame({
        'asset': [r[0] for r in rows],
        'weightPercentage': [r[2] for r in rows],
        'updated': ['2026-08-01'] * len(rows),
    })
    metrics = pd.DataFrame({
        'symbol': [r[0] for r in rows],
        'sector': [r[1] for r in rows],
        'ytd': [r[3] for r in rows],
        '1M': [r[4] for r in rows],
        'as_of': ['2026-08-28'] * len(rows),
    })
    return constituents, metrics


def by_sector(window_payload):
    """{sector: contribution_pp} from a window's contribution records."""
    return {r['sector']: r['contribution_pp'] for r in window_payload['contribution']}


class ContributionArithmeticTests(TestCase):

    def test_weights_summing_to_one_hundred_contribute_exactly(self):
        # Tech: 50% at +10, 30% at -5  ->  5.0 - 1.5 = 3.5pp
        # Energy: 20% at +20           ->  4.0pp
        c, m = frames([
            ('AAA', 'Technology', 50.0, 10.0, 1.0),
            ('BBB', 'Technology', 30.0, -5.0, 1.0),
            ('CCC', 'Energy', 20.0, 20.0, 1.0),
        ])
        out = it._sector_contribution(c, m)
        self.assertEqual(by_sector(out['windows']['ytd']), {'Technology': 3.5, 'Energy': 4.0})

    def test_contributions_sum_to_the_index_return(self):
        c, m = frames([
            ('AAA', 'Technology', 50.0, 10.0, 1.0),
            ('BBB', 'Technology', 30.0, -5.0, 1.0),
            ('CCC', 'Energy', 20.0, 20.0, 1.0),
        ])
        out = it._sector_contribution(c, m)
        self.assertAlmostEqual(out['windows']['ytd']['index_return_pp'], 7.5, places=6)

    def test_weights_are_renormalised_when_they_do_not_sum_to_one_hundred(self):
        # Same ratios scaled to 80: the answer must be identical to the 100 case.
        c, m = frames([
            ('AAA', 'Technology', 40.0, 10.0, 1.0),
            ('BBB', 'Technology', 24.0, -5.0, 1.0),
            ('CCC', 'Energy', 16.0, 20.0, 1.0),
        ])
        out = it._sector_contribution(c, m)
        self.assertEqual(by_sector(out['windows']['ytd']), {'Technology': 3.5, 'Energy': 4.0})

    def test_each_window_is_computed_independently(self):
        # 1M differs from ytd, so the two windows must not share a result.
        c, m = frames([
            ('AAA', 'Technology', 60.0, 10.0, -2.0),
            ('BBB', 'Energy', 40.0, 5.0, 3.0),
        ])
        out = it._sector_contribution(c, m)
        self.assertEqual(by_sector(out['windows']['ytd']), {'Technology': 6.0, 'Energy': 2.0})
        self.assertEqual(by_sector(out['windows']['1M']), {'Technology': -1.2, 'Energy': 1.2})


class MissingDataTests(TestCase):
    """factor_metrics genuinely carries NaN returns -- 74 of 1955 on r2000 --
    so this is the common path, not an edge case."""

    def test_a_nan_return_is_excluded_and_the_rest_renormalised(self):
        # CCC has no ytd, so ytd renormalises over AAA+BBB (80 -> 62.5/37.5):
        #   0.625 * 10 + 0.375 * -5 = 6.25 - 1.875 = 4.375
        c, m = frames([
            ('AAA', 'Technology', 50.0, 10.0, 1.0),
            ('BBB', 'Technology', 30.0, -5.0, 1.0),
            ('CCC', 'Energy', 20.0, np.nan, 1.0),
        ])
        out = it._sector_contribution(c, m)
        ytd = by_sector(out['windows']['ytd'])
        self.assertAlmostEqual(ytd['Technology'], 4.375, places=6)
        self.assertNotIn('Energy', ytd)

    def test_a_window_with_a_nan_does_not_disturb_the_other_window(self):
        c, m = frames([
            ('AAA', 'Technology', 50.0, np.nan, 4.0),
            ('BBB', 'Energy', 50.0, 8.0, 2.0),
        ])
        out = it._sector_contribution(c, m)
        # ytd: only BBB survives, renormalised to 100% -> 8.0
        self.assertAlmostEqual(by_sector(out['windows']['ytd'])['Energy'], 8.0, places=6)
        # 1M: both survive at 50/50 -> 2.0 and 1.0
        self.assertEqual(by_sector(out['windows']['1M']), {'Technology': 2.0, 'Energy': 1.0})

    def test_non_finite_returns_never_reach_the_payload(self):
        """The RQP.TO incident: inf sails through `v != v` and 500s at DRF render
        time after the view already returned 200. See json_safe's docstring."""
        c, m = frames([
            ('AAA', 'Technology', 50.0, np.inf, 1.0),
            ('BBB', 'Energy', 50.0, 4.0, 1.0),
        ])
        out = it._sector_contribution(c, m)
        flat = [r['contribution_pp'] for r in out['windows']['ytd']['contribution']]
        for value in flat:
            self.assertTrue(value is None or np.isfinite(value), f'non-finite leaked: {value}')

    def test_a_constituent_absent_from_metrics_is_reported_not_silently_dropped(self):
        c = pd.DataFrame({'asset': ['AAA', 'BBB'], 'weightPercentage': [70.0, 30.0],
                          'updated': ['2026-08-01'] * 2})
        m = pd.DataFrame({'symbol': ['AAA'], 'sector': ['Technology'],
                          'ytd': [10.0], '1M': [1.0], 'as_of': ['2026-08-28']})
        out = it._sector_contribution(c, m)
        self.assertEqual(out['matched']['count'], 1)
        self.assertEqual(out['matched']['total'], 2)
        self.assertAlmostEqual(out['matched']['weight_pct'], 70.0, places=6)

    def test_an_empty_join_returns_an_empty_payload_rather_than_raising(self):
        c = pd.DataFrame({'asset': ['ZZZ'], 'weightPercentage': [100.0],
                          'updated': ['2026-08-01']})
        m = pd.DataFrame({'symbol': ['AAA'], 'sector': ['Technology'],
                          'ytd': [10.0], '1M': [1.0], 'as_of': ['2026-08-28']})
        out = it._sector_contribution(c, m)
        self.assertEqual(out['matched']['count'], 0)
        self.assertEqual(out['windows']['ytd']['contribution'], [])
        self.assertIsNone(out['windows']['ytd']['index_return_pp'])

    def test_zero_total_weight_does_not_divide_by_zero(self):
        c, m = frames([
            ('AAA', 'Technology', 0.0, 10.0, 1.0),
            ('BBB', 'Energy', 0.0, 5.0, 1.0),
        ])
        out = it._sector_contribution(c, m)
        self.assertEqual(out['windows']['ytd']['contribution'], [])
        self.assertIsNone(out['windows']['ytd']['index_return_pp'])


class BreadthTests(TestCase):

    def test_breadth_counts_positive_returns_over_names_with_data(self):
        c, m = frames([
            ('AAA', 'Technology', 25.0, 10.0, 1.0),
            ('BBB', 'Technology', 25.0, -5.0, 1.0),
            ('CCC', 'Energy', 25.0, 20.0, 1.0),
            ('DDD', 'Energy', 25.0, -1.0, 1.0),
        ])
        breadth = it._sector_contribution(c, m)['windows']['ytd']['breadth']
        self.assertEqual((breadth['positive'], breadth['total']), (2, 4))
        self.assertAlmostEqual(breadth['pct'], 50.0, places=6)

    def test_breadth_ignores_names_with_no_return_for_that_window(self):
        c, m = frames([
            ('AAA', 'Technology', 25.0, 10.0, 1.0),
            ('BBB', 'Technology', 25.0, np.nan, 1.0),
            ('CCC', 'Energy', 50.0, -3.0, 1.0),
        ])
        breadth = it._sector_contribution(c, m)['windows']['ytd']['breadth']
        self.assertEqual((breadth['positive'], breadth['total']), (1, 2))
        self.assertAlmostEqual(breadth['pct'], 50.0, places=6)

    def test_exactly_zero_is_not_counted_as_positive(self):
        c, m = frames([
            ('AAA', 'Technology', 50.0, 0.0, 1.0),
            ('BBB', 'Energy', 50.0, 1.0, 1.0),
        ])
        breadth = it._sector_contribution(c, m)['windows']['ytd']['breadth']
        self.assertEqual((breadth['positive'], breadth['total']), (1, 2))


class PayloadShapeTests(TestCase):

    def test_sectors_are_ranked_by_contribution_descending(self):
        c, m = frames([
            ('AAA', 'Technology', 20.0, 1.0, 1.0),
            ('BBB', 'Energy', 20.0, 30.0, 1.0),
            ('CCC', 'Utilities', 60.0, -2.0, 1.0),
        ])
        out = it._sector_contribution(c, m)
        ordered = [r['sector'] for r in out['windows']['ytd']['contribution']]
        self.assertEqual(ordered, ['Energy', 'Technology', 'Utilities'])

    def test_each_record_carries_the_weight_and_count_behind_it(self):
        c, m = frames([
            ('AAA', 'Technology', 50.0, 10.0, 1.0),
            ('BBB', 'Technology', 30.0, -5.0, 1.0),
            ('CCC', 'Energy', 20.0, 20.0, 1.0),
        ])
        record = by_sector_record(it._sector_contribution(c, m), 'Technology')
        self.assertAlmostEqual(record['weight_pct'], 80.0, places=6)
        self.assertEqual(record['count'], 2)

    def test_both_as_of_dates_survive_into_the_payload(self):
        """Weights and returns are four weeks apart in production (2026-08-01 vs
        2026-08-28). Reporting one date would imply a precision we do not have."""
        c, m = frames([('AAA', 'Technology', 100.0, 10.0, 1.0)])
        out = it._sector_contribution(c, m)
        self.assertEqual(out['weights_as_of'], '2026-08-01')
        self.assertEqual(out['returns_as_of'], '2026-08-28')

    def test_payload_is_json_serialisable_with_no_numpy_scalars(self):
        import json
        c, m = frames([
            ('AAA', 'Technology', 50.0, 10.0, 1.0),
            ('BBB', 'Energy', 50.0, np.nan, 1.0),
        ])
        json.dumps(it._sector_contribution(c, m))  # raises on numpy types / NaN-free check below

    def test_payload_contains_no_nan_or_inf_anywhere(self):
        c, m = frames([
            ('AAA', 'Technology', 50.0, np.nan, np.inf),
            ('BBB', 'Energy', 50.0, 4.0, 1.0),
        ])
        out = it._sector_contribution(c, m)
        self.assertFalse(_has_non_finite(out), 'payload carries NaN or inf')


def by_sector_record(payload, sector, window='ytd'):
    for record in payload['windows'][window]['contribution']:
        if record['sector'] == sector:
            return record
    raise AssertionError(f'{sector} not in {window} contribution')


def _has_non_finite(obj):
    if isinstance(obj, dict):
        return any(_has_non_finite(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(_has_non_finite(v) for v in obj)
    if isinstance(obj, float):
        return not np.isfinite(obj)
    return False
