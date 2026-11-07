import numpy as np
import pandas as pd
import pytest

from pipelines.factor_windows import (ATTRIBUTION_WINDOWS, WINDOWS, calendar_start,
                                      window_return_and_std)


def _series(dates, values):
    return pd.Series(values, index=pd.to_datetime(dates))


def test_one_month_return_is_a_percent():
    dates = pd.bdate_range("2026-06-01", "2026-08-05")
    prices = _series(dates, np.linspace(100.0, 110.0, len(dates)))
    ret, _ = window_return_and_std(prices, "1M")
    # anchor is the last trading day on or before 2026-07-05
    anchor = prices.asof(pd.Timestamp("2026-07-05"))
    assert ret == pytest.approx((prices.iloc[-1] / anchor - 1) * 100)
    assert ret > 1.0  # a percent, not a decimal fraction


def test_ytd_anchors_on_the_last_close_of_the_prior_year():
    dates = ["2025-12-30", "2025-12-31", "2026-01-02", "2026-01-05"]
    prices = _series(dates, [50.0, 100.0, 105.0, 120.0])
    ret, _ = window_return_and_std(prices, "ytd")
    assert ret == pytest.approx(20.0)  # 120 / 100 - 1


def test_std_is_daily_decimal_not_annualised():
    dates = pd.bdate_range("2026-01-02", "2026-08-05")
    rng = np.random.default_rng(0)
    prices = _series(dates, 100 * np.cumprod(1 + rng.normal(0, 0.01, len(dates))))
    _, std = window_return_and_std(prices, "6M")
    assert 0.001 < std < 0.05  # daily scale; annualised would be ~0.16


def test_january_does_not_crash_on_month_underflow():
    """date(year, month - 3, day) raised ValueError here in the legacy code."""
    dates = pd.bdate_range("2025-06-02", "2026-01-15")
    prices = _series(dates, np.linspace(100.0, 120.0, len(dates)))
    ret, std = window_return_and_std(prices, "3M")
    assert ret is not None and std is not None


def test_day_31_does_not_crash_on_short_target_month():
    """date(2026, 2, 31) raised ValueError in the legacy code."""
    dates = pd.bdate_range("2025-06-02", "2026-08-31")
    prices = _series(dates, np.linspace(100.0, 120.0, len(dates)))
    ret, _ = window_return_and_std(prices, "6M")
    assert ret is not None


def test_window_longer_than_history_returns_none_not_a_partial_number():
    dates = pd.bdate_range("2026-07-20", "2026-08-05")
    prices = _series(dates, np.linspace(100.0, 105.0, len(dates)))
    assert window_return_and_std(prices, "6M") == (None, None)


def test_empty_series_returns_none():
    assert window_return_and_std(pd.Series(dtype=float), "1M") == (None, None)


def test_window_labels_cover_the_frontend_periods():
    assert set(WINDOWS) == {"1M", "3M", "6M"}


def test_calendar_start_matches_each_attribution_window():
    t = pd.Timestamp("2026-11-13")
    starts = {k: calendar_start(t, v) for k, v in ATTRIBUTION_WINDOWS.items()}
    assert list(starts) == ["1W", "2W", "1M", "3M", "ytd", "1Y"]
    assert starts == {"1W": pd.Timestamp("2026-11-06"), "2W": pd.Timestamp("2026-10-30"),
                      "1M": pd.Timestamp("2026-10-13"), "3M": pd.Timestamp("2026-08-13"),
                      "ytd": pd.Timestamp("2025-12-31"), "1Y": pd.Timestamp("2025-11-13")}


def test_month_end_offset_clamps():
    assert (calendar_start(pd.Timestamp("2026-03-31"), pd.DateOffset(months=1))
            == pd.Timestamp("2026-02-28"))


def test_factor_windows_unchanged():
    assert WINDOWS == {"1M": 1, "3M": 3, "6M": 6}
