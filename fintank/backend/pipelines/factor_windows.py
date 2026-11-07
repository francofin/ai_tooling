"""Trading-day window returns for the factor metrics producer.

Kept as a module rather than a notebook cell so it can be unit-tested: this
is where all three legacy window bugs lived --

  1. date(year, month - 3, day) raised ValueError in Jan-Jun and on days
     29-31, swallowed by a bare except, so symbols silently vanished.
  2. A 240-calendar-day fetch window truncated YTD after ~Aug 28 with no
     error, understating both the return and the stdev.
  3. Prices came from historical-chart/1day, which carries no adjClose, so
     returns were dividend-blind. Callers here pass adjClose.

Returns are PERCENT (5.42 == 5.42%), matching what the backend divides by
100. Stdev is DAILY DECIMAL, matching the legacy frame the factor page
renders in its bucket-holdings tables.
"""
import pandas as pd

WINDOWS = {"1M": 1, "3M": 3, "6M": 6}

# Index attribution windows (pipelines/attribution.py). Kept apart from WINDOWS,
# which shapes the factor_metrics schema; both share calendar_start so the two
# can never disagree on where a window begins. None means year to date.
ATTRIBUTION_WINDOWS = {
    "1W": pd.DateOffset(days=7),
    "2W": pd.DateOffset(days=14),
    "1M": pd.DateOffset(months=1),
    "3M": pd.DateOffset(months=3),
    "ytd": None,
    "1Y": pd.DateOffset(years=1),
}


def calendar_start(as_of, offset):
    """Calendar start of a window ending at `as_of`: as_of - offset, or the
    prior year's Dec 31 when offset is None. The caller resolves it to a
    trading day."""
    if offset is None:
        return pd.Timestamp(year=as_of.year - 1, month=12, day=31)
    return as_of - offset


def _anchor_date(as_of, label):
    """Calendar start of the window; the caller resolves it to a trading day."""
    return calendar_start(
        as_of, None if label == "ytd" else pd.DateOffset(months=WINDOWS[label]))


def window_return_and_std(adj_close, label):
    """(percent return, daily decimal stdev) over `label`, or (None, None).

    The anchor is the last trading day at or before the calendar start --
    Series.asof, so a weekend or holiday start resolves backwards instead of
    raising. A window whose anchor predates the first print yields (None,
    None) rather than a partial-window number.
    """
    if adj_close is None or len(adj_close) < 2:
        return None, None

    prices = adj_close.dropna().sort_index()
    if len(prices) < 2:
        return None, None

    as_of = prices.index[-1]
    anchor = _anchor_date(as_of, label)
    if anchor < prices.index[0]:
        return None, None

    anchor_price = prices.asof(anchor)
    if pd.isna(anchor_price) or anchor_price == 0:
        return None, None

    window = prices.loc[anchor:]
    if len(window) < 2:
        return None, None

    period_return = (prices.iloc[-1] / anchor_price - 1) * 100
    daily_std = window.pct_change().std()

    if pd.isna(period_return):
        return None, None
    return float(period_return), (None if pd.isna(daily_std) else float(daily_std))
