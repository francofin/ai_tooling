import numpy as np
import pandas as pd
import pytest

from pipelines.attribution import COLUMNS, common_end_date, compute_attribution, index_stats

END = "2026-11-13"   # a Friday


def _frame(n, columns, end=END):
    """Business-day price frame; each column is a list (len n) or a scalar."""
    dates = pd.bdate_range(end=end, periods=n)
    return pd.DataFrame({k: (v if np.ndim(v) else [v] * n) for k, v in columns.items()},
                        index=dates, dtype=float)


def _linear(n, start, stop):
    return list(np.linspace(start, stop, n))


def _rows(out, window, level):
    return out[(out.window == window) & (out.level == level)].set_index("key")


def _index(out, window):
    return out[(out.window == window) & (out.level == "index")].iloc[0]


def _attrib(prices, weights, holdings_date=None, sectors=None, **kw):
    weights = pd.Series(weights, dtype=float)
    sectors = pd.Series(sectors if sectors is not None else
                        {s: "Tech" for s in weights.index}, dtype=object)
    holdings_date = pd.Timestamp(holdings_date or prices.index[-1])
    return compute_attribution(prices, weights, sectors, holdings_date, **kw)


def _three_names(n=300):
    return _frame(n, {"A": _linear(n, 100, 140), "B": _linear(n, 100, 80),
                      "C": _linear(n, 50, 75)})


def test_output_has_the_schema_columns_in_order():
    out = _attrib(_three_names(), {"A": .5, "B": .3, "C": .2})
    assert list(out.columns) == COLUMNS


def test_holdings_at_end_matches_closed_form():
    prices = _three_names()
    w_t = pd.Series({"A": .5, "B": .3, "C": .2})
    out = _attrib(prices, w_t)
    for window in ("1W", "1M", "3M"):
        cons = _rows(out, window, "constituent")
        start, end = cons["start_date"].iloc[0], cons["end_date"].iloc[0]
        r = prices.loc[end] / prices.loc[start] - 1
        one_plus_r = 1 / (w_t / (1 + r)).sum()
        assert _index(out, window)["return_pct"] == pytest.approx((one_plus_r - 1) * 100, abs=1e-10)
        expected_c = one_plus_r * w_t * r / (1 + r) * 100
        assert cons["contribution_pp"].sort_index().to_numpy() == pytest.approx(
            expected_c.sort_index().to_numpy(), abs=1e-10)


def test_old_end_weight_method_is_biased_by_weighted_variance():
    out = _attrib(_three_names(), {"A": .5, "B": .3, "C": .2})
    cons = _rows(out, "1Y", "constituent")
    w0, wt = cons["weight_start_pct"] / 100, cons["weight_end_pct"] / 100
    r = cons["return_pct"] / 100
    big_r = (w0 * r).sum()
    assert (wt * r).sum() - big_r == pytest.approx(
        (w0 * (r - big_r) ** 2).sum() / (1 + big_r), abs=1e-12)


def test_two_names_hand_computed():
    n = 30
    prices = _frame(n, {"A": [100.0] * (n - 1) + [120.0], "B": [100.0] * (n - 1) + [90.0]})
    out = _attrib(prices, {"A": .5, "B": .5}, holdings_date="2026-11-06")
    cons = _rows(out, "1W", "constituent")
    assert cons.loc["A", "weight_start_pct"] == pytest.approx(50.0)
    assert _index(out, "1W")["contribution_pp"] == pytest.approx(5.0)
    assert cons.loc["A", "contribution_pp"] == pytest.approx(10.0)
    assert cons.loc["B", "contribution_pp"] == pytest.approx(-5.0)
    assert cons.loc["A", "weight_end_pct"] == pytest.approx(60 / 1.05)
    assert cons.loc["B", "weight_end_pct"] == pytest.approx(45 / 1.05)


def test_stale_holdings_drift_forward_to_window_start():
    # A doubles after the holdings date (Oct 23) and before the 1W start (Nov 6).
    dates = pd.bdate_range(end=END, periods=30)
    a = [50.0 if d <= pd.Timestamp("2026-10-23") else 100.0 for d in dates]
    prices = pd.DataFrame({"A": a, "B": 100.0}, index=dates)
    out = _attrib(prices, {"A": .5, "B": .5}, holdings_date="2026-10-23")
    assert _rows(out, "1W", "constituent").loc["A", "weight_start_pct"] == pytest.approx(200 / 3)


def test_holdings_date_after_price_end_uses_last_row():
    prices = _three_names()
    late = _attrib(prices, {"A": .5, "B": .3, "C": .2},
                   holdings_date=pd.Timestamp(END) + pd.Timedelta(days=3))
    at_end = _attrib(prices, {"A": .5, "B": .3, "C": .2})
    pd.testing.assert_series_equal(
        late["contribution_pp"].reset_index(drop=True),
        at_end["contribution_pp"].reset_index(drop=True))
    assert np.isfinite(_index(late, "1M")["contribution_pp"])


def _mixed(n=300):
    """Covered names in two sectors and none, one joined name, one stale name."""
    prices = _frame(n, {"A": _linear(n, 100, 130), "B": _linear(n, 100, 90),
                        "C": _linear(n, 20, 21), "D": _linear(n, 10, 30),
                        "S": _linear(n, 5, 6)})
    prices.iloc[:-40, prices.columns.get_loc("D")] = np.nan      # lists ~2 months ago
    prices.iloc[-7:, prices.columns.get_loc("S")] = np.nan       # stopped printing
    weights = {"A": .35, "B": .25, "C": .15, "D": .1, "S": .05, "USD": .04, "ZZZZ": .06}
    sectors = {"A": "Tech", "B": "Energy", "C": None, "D": "Tech", "S": "Energy"}
    return prices, weights, sectors


def test_identity_sectors_equal_index_and_buckets_sum_to_100():
    prices, weights, sectors = _mixed()
    out = _attrib(prices, weights, sectors=sectors)
    for window in out.window.unique():
        idx = _index(out, window)
        sectors_pp = out[(out.window == window) & (out.level == "sector")]["contribution_pp"]
        assert sectors_pp.sum() == pytest.approx(idx["contribution_pp"], abs=1e-9)
        buckets = out[(out.window == window)
                      & out.level.isin(["joined", "unattributed", "non_equity"])]
        assert idx["covered_weight_pct"] + buckets["weight_end_pct"].sum() == pytest.approx(100, abs=1e-9)


def test_missing_start_price_is_joined_not_contributing():
    prices, weights, sectors = _mixed()
    out = _attrib(prices, weights, sectors=sectors)
    joined = _rows(out, "3M", "joined")
    assert list(joined.index) == ["D"]
    assert np.isnan(joined.loc["D", "contribution_pp"])
    first = prices["D"].dropna().iloc[0]
    assert joined.loc["D", "return_pct"] == pytest.approx((prices["D"].iloc[-1] / first - 1) * 100)
    assert joined.loc["D", "weight_end_pct"] == pytest.approx(10.0)   # share of declared
    assert "D" in _rows(out, "1M", "constituent").index                # listed before the 1M start


def test_start_gap_within_grace_is_a_data_gap():
    n = 60
    prices = _frame(n, {"A": _linear(n, 100, 110), "B": _linear(n, 100, 105)})
    start = pd.Timestamp("2026-10-13")                  # 1M calendar start, a Tuesday
    gap = (prices.index <= start + pd.offsets.BDay(1))  # first print 2 sessions after
    prices.loc[gap, "B"] = np.nan
    out = _attrib(prices, {"A": .5, "B": .5})
    cons = _rows(out, "1M", "constituent")
    first = prices["B"].dropna().iloc[0]
    assert cons.loc["B", "return_pct"] == pytest.approx((prices["B"].iloc[-1] / first - 1) * 100)


def test_unpriced_symbols_split_into_non_equity_and_unattributed():
    weights = {"A": .5, "B": .3, "USD": .05, "XTSLA": .05, "ESZ6": .04, "CAD": .03, "ZZZZ": .03}
    out = _attrib(_three_names(), weights)
    ne, un = _rows(out, "1M", "non_equity").iloc[0], _rows(out, "1M", "unattributed").iloc[0]
    assert (ne["count"], un["count"]) == (4, 1)
    assert ne["weight_end_pct"] == pytest.approx(17.0)
    assert un["weight_end_pct"] == pytest.approx(3.0)


def test_weights_summing_to_80_or_120_give_identical_contributions():
    prices = _three_names()
    base = {"A": .5, "B": .3, "C": .2}
    a = _attrib(prices, {k: v * .8 for k, v in base.items()})
    b = _attrib(prices, {k: v * 1.2 for k, v in base.items()})
    np.testing.assert_allclose(a["contribution_pp"], b["contribution_pp"], rtol=1e-12)


def test_zero_nan_and_all_zero_weights():
    prices = _three_names()
    out = _attrib(prices, {"A": .5, "B": 0.0, "C": np.nan})
    assert set(out[out.level == "constituent"].key) == {"A"}
    assert _index(out, "1M")["covered_weight_pct"] == pytest.approx(100.0)
    empty = _attrib(prices, {"A": 0.0, "B": 0.0})
    assert empty.empty and list(empty.columns) == COLUMNS


def test_null_sector_is_unclassified_and_single_name_sector_is_kept():
    prices, weights, sectors = _mixed()
    out = _attrib(prices, weights, sectors=sectors)
    sec = _rows(out, "1M", "sector")
    assert set(sec.index) == {"Tech", "Energy", "Unclassified"}
    assert sec.loc["Unclassified", "count"] == 1
    assert _rows(out, "1M", "constituent").loc["C", "sector"] == "Unclassified"


def test_zero_or_inf_price_never_emits_inf():
    n = 300
    prices = _three_names(n)
    prices["D"] = 0.0
    prices.iloc[-20:, prices.columns.get_loc("D")] = 10.0
    prices.iloc[-1, prices.columns.get_loc("A")] = np.inf
    out = _attrib(prices, {"A": .4, "B": .3, "C": .2, "D": .1})
    numeric = out.select_dtypes("number").to_numpy(dtype=float, na_value=np.nan)
    assert not np.isinf(numeric).any()
    assert "D" not in _rows(out, "3M", "constituent").index


def test_window_before_first_print_is_omitted():
    out = _attrib(_three_names(200), {"A": .5, "B": .3, "C": .2})
    assert "1Y" not in set(out.window) and "3M" in set(out.window)


def test_windows_come_out_in_definition_order():
    out = _attrib(_three_names(), {"A": .5, "B": .3, "C": .2})
    assert list(dict.fromkeys(out.window)) == ["1W", "2W", "1M", "3M", "ytd", "1Y"]


def test_holiday_anchor_resolves_backwards_like_asof():
    prices = _three_names(60).set_axis(pd.bdate_range(end="2026-11-04", periods=60))
    out = _attrib(prices, {"A": .5, "B": .3, "C": .2})
    # 1M calendar start is Sunday 2026-10-04 → the window starts Friday 2026-10-02
    assert _index(out, "1M")["start_date"] == pd.Timestamp("2026-10-02")


def test_ragged_calendars_end_on_majority_date():
    n = 40
    prices = _frame(n, {s: _linear(n, 100, 110) for s in "ABCDE"})
    prices.iloc[-2:, prices.columns.get_loc("D")] = np.nan   # 2 sessions behind
    prices.iloc[-7:, prices.columns.get_loc("E")] = np.nan   # 7 sessions behind
    assert common_end_date(prices) == prices.index[-1]
    out = _attrib(prices, {s: .2 for s in "ABCDE"})
    assert "D" in _rows(out, "1W", "constituent").index
    assert _rows(out, "1W", "unattributed").iloc[0]["count"] == 1


def test_index_stats_hand_computed():
    r = pd.Series({"A": 10.0, "B": -5.0, "C": 2.0, "D": 0.0})
    w0 = pd.Series({"A": .4, "B": .3, "C": .2, "D": .1})
    s = index_stats(r, w0, w0 * r)                     # R = 2.9
    assert s["breadth_up"] == 2 and s["breadth_pct_up"] == 50.0
    assert s["breadth_pct_beat"] == 25.0               # only A beats 2.9
    assert s["median_return_pct"] == pytest.approx(1.0)
    assert s["effective_n"] == pytest.approx(1 / .30)
    assert s["ew_return_pct"] == pytest.approx(1.75)
    assert s["cap_minus_ew_pp"] == pytest.approx(1.15)
    assert s["names_to_50pct"] == 1                    # A alone = 4.0 >= 1.45
    assert s["top10_contribution_pp"] == pytest.approx(2.9)


def test_names_to_50pct_is_none_near_zero_return():
    r = pd.Series({"A": 1.0, "B": -0.4})
    w0 = pd.Series({"A": .5, "B": .5})
    assert index_stats(r, w0, w0 * r)["names_to_50pct"] is None   # R = 0.3pp


def test_negative_return_counts_detractors_first():
    r = pd.Series({"A": -20.0, "B": -2.0, "C": 3.0, "D": -1.0})
    w0 = pd.Series({"A": .25, "B": .25, "C": .25, "D": .25})
    s = index_stats(r, w0, w0 * r)                     # R = -5.0; A alone = -5.0
    assert s["names_to_50pct"] == 1
    assert s["top10_contribution_pp"] == pytest.approx(-5.0)


def test_index_rows_carry_the_stats():
    out = _attrib(_three_names(), {"A": .5, "B": .3, "C": .2})
    idx = _index(out, "1M")
    assert idx["breadth_up"] == 2 and np.isfinite(idx["effective_n"])


def test_residual_against_reference():
    prices = _three_names()
    flat = pd.Series(100.0, index=prices.index)
    out = _attrib(prices, {"A": .5, "B": .3, "C": .2}, reference=flat, ref_symbol="SPY")
    idx = _index(out, "1M")
    assert idx["ref_symbol"] == "SPY" and idx["ref_return_pct"] == pytest.approx(0.0)
    assert idx["residual_pp"] == pytest.approx(idx["contribution_pp"])
    none = _index(_attrib(prices, {"A": .5, "B": .3, "C": .2}), "1M")
    assert np.isnan(none["ref_return_pct"]) and np.isnan(none["residual_pp"])
