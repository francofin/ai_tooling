"""Request validation. Pure -- no Django, no numpy beyond the weight vector."""
from unittest import TestCase

from backtester.engine.config import (
    BacktestRequest,
    Holding,
    RequestValidationError,
    normalized_payload,
    optimizer_config,
    validate_request,
)


def _payload(**overrides):
    payload = {'holdings': [{'symbol': 'aapl'}, {'symbol': 'VTI'}]}
    payload.update(overrides)
    return payload


class ValidateRequestTests(TestCase):

    def test_symbols_are_uppercased_and_defaults_applied(self):
        request = validate_request(_payload())

        self.assertEqual([h.symbol for h in request.holdings], ['AAPL', 'VTI'])
        self.assertEqual(request.benchmark_symbol, 'SPY')
        self.assertEqual(request.initial_amount, 10_000.0)
        self.assertEqual(request.weighting_scheme, 'equal')
        self.assertEqual(request.backtest_mode, 'fixed')
        self.assertEqual(request.rebalance_frequency, 'annual')
        self.assertEqual(request.covariance_method, 'ledoit_wolf')
        self.assertEqual(request.inception_policy, 'phase_in')
        self.assertTrue(request.long_only)

    def test_empty_holdings_are_rejected(self):
        with self.assertRaises(RequestValidationError) as caught:
            validate_request(_payload(holdings=[]))
        self.assertIn('at least one holding', str(caught.exception))

    def test_duplicate_symbols_are_rejected(self):
        with self.assertRaises(RequestValidationError) as caught:
            validate_request(_payload(holdings=[{'symbol': 'AAPL'}, {'symbol': 'aapl'}]))
        self.assertIn('AAPL', str(caught.exception))

    def test_unknown_weighting_scheme_is_rejected(self):
        with self.assertRaises(RequestValidationError):
            validate_request(_payload(weighting_scheme='magic'))

    def test_unknown_rebalance_frequency_is_rejected(self):
        with self.assertRaises(RequestValidationError):
            validate_request(_payload(rebalance_frequency='hourly'))

    def test_custom_weights_are_normalized_to_sum_to_one(self):
        request = validate_request(_payload(
            weighting_scheme='custom',
            holdings=[{'symbol': 'A', 'target_weight': 3.0},
                      {'symbol': 'B', 'target_weight': 1.0}],
        ))

        self.assertAlmostEqual(request.holdings[0].target_weight, 0.75)
        self.assertAlmostEqual(request.holdings[1].target_weight, 0.25)

    def test_negative_custom_weight_is_rejected_when_long_only(self):
        with self.assertRaises(RequestValidationError) as caught:
            validate_request(_payload(
                weighting_scheme='custom',
                holdings=[{'symbol': 'A', 'target_weight': -0.5},
                          {'symbol': 'B', 'target_weight': 1.5}],
            ))
        self.assertIn('negative', str(caught.exception))

    def test_custom_weights_summing_to_zero_are_rejected(self):
        with self.assertRaises(RequestValidationError):
            validate_request(_payload(
                weighting_scheme='custom',
                holdings=[{'symbol': 'A', 'target_weight': 0.0},
                          {'symbol': 'B', 'target_weight': 0.0}],
            ))

    def test_infeasible_max_weight_is_rejected_before_the_solver_sees_it(self):
        with self.assertRaises(RequestValidationError) as caught:
            validate_request(_payload(max_weight=0.2, holdings=[
                {'symbol': 'A'}, {'symbol': 'B'}, {'symbol': 'C'}]))
        self.assertIn('max_weight', str(caught.exception))

    def test_infeasible_min_weight_is_rejected(self):
        with self.assertRaises(RequestValidationError) as caught:
            validate_request(_payload(min_weight=0.6))
        self.assertIn('min_weight', str(caught.exception))

    def test_start_date_after_end_date_is_rejected(self):
        with self.assertRaises(RequestValidationError):
            validate_request(_payload(start_date='2020-01-01', end_date='2019-01-01'))

    def test_dates_are_parsed_from_iso_strings(self):
        request = validate_request(_payload(start_date='2015-06-01', end_date='2020-06-01'))

        self.assertEqual(request.start_date.year, 2015)
        self.assertEqual(request.end_date.year, 2020)

    def test_malformed_date_is_rejected(self):
        with self.assertRaises(RequestValidationError):
            validate_request(_payload(start_date='last tuesday'))

    def test_non_positive_initial_amount_is_rejected(self):
        with self.assertRaises(RequestValidationError):
            validate_request(_payload(initial_amount=0))

    def test_negative_transaction_cost_is_rejected(self):
        with self.assertRaises(RequestValidationError):
            validate_request(_payload(transaction_cost_bps=-1))

    def test_lookback_shorter_than_two_days_is_rejected(self):
        with self.assertRaises(RequestValidationError):
            validate_request(_payload(lookback_days=1))


class MinHistoryDefaultTests(TestCase):
    """§5: the optimizer schemes need a complete rectangular covariance block."""

    def test_equal_and_custom_need_one_day(self):
        self.assertEqual(validate_request(_payload()).min_history_days, 1)
        self.assertEqual(validate_request(_payload(
            weighting_scheme='custom',
            holdings=[{'symbol': 'A', 'target_weight': 1.0}],
        )).min_history_days, 1)

    def test_optimizer_schemes_need_a_full_lookback(self):
        for scheme in ('inverse_vol', 'min_variance', 'risk_parity', 'max_sharpe'):
            with self.subTest(scheme=scheme):
                request = validate_request(_payload(weighting_scheme=scheme))
                self.assertEqual(request.min_history_days, request.lookback_days)

    def test_an_explicit_min_history_days_wins(self):
        request = validate_request(_payload(weighting_scheme='min_variance',
                                            min_history_days=30))
        self.assertEqual(request.min_history_days, 30)


class NormalizedPayloadTests(TestCase):
    """The hash must be stable across key order and symbol casing."""

    def test_two_equivalent_requests_normalize_identically(self):
        one = validate_request({'holdings': [{'symbol': 'aapl'}, {'symbol': 'vti'}],
                                'benchmark_symbol': 'spy'})
        two = validate_request({'benchmark_symbol': 'SPY',
                                'holdings': [{'symbol': 'AAPL'}, {'symbol': 'VTI'}]})

        self.assertEqual(normalized_payload(one), normalized_payload(two))

    def test_holding_order_is_significant(self):
        one = validate_request(_payload(holdings=[{'symbol': 'A'}, {'symbol': 'B'}]))
        two = validate_request(_payload(holdings=[{'symbol': 'B'}, {'symbol': 'A'}]))

        self.assertNotEqual(normalized_payload(one), normalized_payload(two))

    def test_payload_is_json_serializable(self):
        import json
        json.dumps(normalized_payload(validate_request(
            _payload(start_date='2020-01-01'))), sort_keys=True)


class OptimizerConfigTests(TestCase):

    def test_config_carries_the_constraint_block(self):
        request = validate_request(_payload(max_weight=0.6, min_weight=0.05,
                                            risk_free_rate=0.02, long_only=True))
        config = optimizer_config(request)

        self.assertEqual(config.max_weight, 0.6)
        self.assertEqual(config.min_weight, 0.05)
        self.assertEqual(config.risk_free_rate, 0.02)
        self.assertTrue(config.long_only)
        self.assertIsNone(config.custom_weights)

    def test_custom_weights_are_attached_when_supplied(self):
        request = validate_request(_payload())
        config = optimizer_config(request, custom_weights=[0.3, 0.7])

        self.assertEqual(list(config.custom_weights), [0.3, 0.7])
