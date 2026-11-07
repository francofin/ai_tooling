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
import json
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


# --- Precomputed attribution (pipelines/attribution.py output) ---------------

from unittest.mock import MagicMock, patch  # noqa: E402


def attribution_frame(windows=('ytd', '1M')):
    """A long frame shaped like index_data/attribution/{sub}_attribution.parquet:
    12 Tech/Energy constituents, one joined name, unattributed and non-equity
    buckets, per window."""
    rows = []
    names = [(f"S{i:02d}", 'Tech' if i % 2 else 'Energy', 1 / 12, 12.0 - 2 * i) for i in range(12)]
    for w in windows:
        base = {'window': w, 'start_date': pd.Timestamp('2025-12-31'),
                'end_date': pd.Timestamp('2026-11-13'), 'holdings_date': pd.Timestamp('2026-11-12')}
        contrib = {s: wt * r for s, _, wt, r in names}
        total = sum(contrib.values())
        rows.append({**base, 'level': 'index', 'key': '__index__', 'return_pct': total,
                     'contribution_pp': total, 'weight_start_pct': 100.0, 'count': 12,
                     'return_basis': 'price', 'currency_basis': 'USD', 'ref_symbol': 'SPY',
                     'ref_return_pct': total - 0.1, 'residual_pp': 0.1,
                     'covered_weight_pct': 97.0, 'breadth_up': 6, 'breadth_pct_up': 50.0,
                     'breadth_pct_beat': 41.7, 'median_return_pct': 1.0, 'effective_n': 12.0,
                     'names_to_50pct': 2, 'top10_contribution_pp': total, 'ew_return_pct': 1.0,
                     'cap_minus_ew_pp': total - 1.0})
        for sector in ('Tech', 'Energy'):
            members = [n for n in names if n[1] == sector]
            c = sum(contrib[s] for s, *_ in members)
            rows.append({**base, 'level': 'sector', 'key': sector, 'count': len(members),
                         'weight_start_pct': 50.0, 'contribution_pp': c, 'return_pct': c / 0.5})
        for s, sector, wt, r in names:
            rows.append({**base, 'level': 'constituent', 'key': s, 'sector': sector,
                         'weight_start_pct': wt * 100, 'return_pct': r, 'contribution_pp': contrib[s]})
        rows.append({**base, 'level': 'joined', 'key': 'NEW', 'sector': 'Tech',
                     'weight_end_pct': 1.0, 'return_pct': 40.0})
        rows.append({**base, 'level': 'unattributed', 'key': '__unattributed__',
                     'weight_end_pct': 1.5, 'count': 3})
        rows.append({**base, 'level': 'non_equity', 'key': '__non_equity__',
                     'weight_end_pct': 0.5, 'count': 1})
    return pd.DataFrame(rows)


class PipelinePayloadTests(TestCase):

    def test_pipeline_payload_keeps_the_existing_contract(self):
        payload = it._payload_from_attribution(attribution_frame())
        for key in ('weights_as_of', 'returns_as_of', 'matched', 'windows'):
            self.assertIn(key, payload)
        self.assertEqual(payload['weights_as_of'], '2026-11-12')
        self.assertEqual(payload['returns_as_of'], '2026-11-13')
        self.assertEqual(set(payload['matched']), {'count', 'total', 'weight_pct'})
        window = payload['windows']['ytd']
        self.assertEqual(set(window['breadth']), {'positive', 'total', 'pct'})
        record = window['contribution'][0]
        self.assertEqual(set(record) >= {'sector', 'weight_pct', 'contribution_pp',
                                         'average_return', 'count'}, True)
        self.assertAlmostEqual(window['index_return_pp'],
                               sum(r['contribution_pp'] for r in window['contribution']))
        tech = next(r for r in window['contribution'] if r['sector'] == 'Tech')
        self.assertAlmostEqual(tech['average_return'], np.mean([12.0 - 2 * i for i in range(1, 12, 2)]))

    def test_pipeline_payload_adds_windows_in_order(self):
        payload = it._payload_from_attribution(attribution_frame(('ytd', '1W', '1Y')))
        self.assertEqual(payload['windows_available'], ['1W', 'ytd', '1Y'])
        self.assertEqual(payload['source'], 'pipeline')
        self.assertEqual((payload['return_basis'], payload['currency_basis']), ('price', 'USD'))
        self.assertEqual(payload['holdings_as_of'], '2026-11-12')

    def test_top_and_bottom_contributors_are_ten_each_and_sorted(self):
        window = it._payload_from_attribution(attribution_frame())['windows']['1M']
        top, bottom = window['top_contributors'], window['bottom_contributors']
        self.assertEqual((len(top), len(bottom)), (10, 10))
        self.assertEqual(top[0]['symbol'], 'S00')
        self.assertEqual(bottom[0]['symbol'], 'S11')
        self.assertEqual([r['contribution_pp'] for r in top],
                         sorted((r['contribution_pp'] for r in top), reverse=True))
        self.assertEqual(set(top[0]), {'symbol', 'sector', 'weight_start_pct',
                                       'return_pct', 'contribution_pp'})

    def test_window_extras(self):
        window = it._payload_from_attribution(attribution_frame())['windows']['ytd']
        self.assertEqual(window['reconciliation']['ref_symbol'], 'SPY')
        self.assertAlmostEqual(window['coverage']['joined_pct'], 1.0)
        self.assertAlmostEqual(window['coverage']['unattributed_pct'], 1.5)
        self.assertEqual(window['concentration']['names_to_50pct'], 2)

    def test_payload_has_no_non_finite(self):
        frame = attribution_frame()
        frame.loc[frame.level == 'index', 'ref_return_pct'] = np.inf
        frame.loc[frame.level == 'index', 'residual_pp'] = np.nan
        payload = it._payload_from_attribution(frame)
        json.dumps(payload, allow_nan=False)


class SectorContributionSourceTests(TestCase):

    def setUp(self):
        self.cache = MagicMock()
        self.cache.get.return_value = None
        patcher = patch.object(it, 'cache', self.cache)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_cache_key_is_v2(self):
        with patch.object(it.data_getter, 'load_index_attribution',
                          return_value=attribution_frame(), create=True):
            it.get_index_sector_contribution('sp500')
        key = self.cache.set.call_args[0][0]
        self.assertEqual(key, 'index:sector_contribution:sp500:v2')
        self.assertEqual(self.cache.set.call_args[1]['timeout'], it.CACHE_TTL)

    def test_missing_parquet_falls_back_to_live_with_short_ttl(self):
        constituents, metrics = frames([('A', 'Tech', 60, 10.0, 1.0), ('B', 'Energy', 40, -5.0, 2.0)])
        with patch.object(it.data_getter, 'load_index_attribution',
                          side_effect=FileNotFoundError('no file'), create=True), \
             patch.object(it.data_getter, 'get_index_constituents',
                          return_value=constituents.to_dict('records')), \
             patch.object(it.data_getter, 'load_factor_metrics', return_value=metrics):
            payload = it.get_index_sector_contribution('sp500')
        self.assertEqual(payload['source'], 'live')
        self.assertEqual(payload['windows_available'], ['ytd', '1M'])
        self.assertEqual(self.cache.set.call_args[1]['timeout'], it.FALLBACK_TTL)
        self.assertEqual(it.FALLBACK_TTL, 900)

    def test_both_sources_missing_raises_key_error(self):
        with patch.object(it.data_getter, 'load_index_attribution',
                          side_effect=FileNotFoundError('no file'), create=True), \
             patch.object(it.data_getter, 'get_index_constituents', return_value=[]):
            with self.assertRaises(KeyError):
                it.get_index_sector_contribution('sp500')

    def test_null_sector_is_unclassified_in_live_path(self):
        constituents, metrics = frames([('A', None, 60, 10.0, 1.0), ('B', 'Energy', 40, -5.0, 2.0)])
        payload = it._sector_contribution(constituents, metrics)
        sectors = by_sector(payload['windows']['ytd'])
        self.assertIn('Unclassified', sectors)
        self.assertAlmostEqual(sum(sectors.values()), payload['windows']['ytd']['index_return_pp'])
