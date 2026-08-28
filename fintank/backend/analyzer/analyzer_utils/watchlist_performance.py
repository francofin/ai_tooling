"""Period-return maths for the watchlist performance panel.

Every number here is derived from the daily price series that
``CorePerformanceTools.get_stock_price_data`` already caches per symbol, so this
module performs no network or S3 access of its own and adds no FMP calls. See
``docs/superpowers/plans/2026-08-22-watchlist-performance.md``.

The functions are deliberately pure -- they take dates and prices and return
numbers -- so the calendar edge cases can be exercised without Redis, S3 or a
database.
"""

from datetime import date, datetime, timedelta

# Calendar offsets for each labelled period. YTD is handled separately because it
# anchors to a date rather than a lookback, and 1D is handled separately because
# it means "the previous close", not "24 hours ago" -- over a weekend those give
# different answers and only the former is meaningful for a daily series.
PERIOD_OFFSETS = {
    "1W": timedelta(days=7),
    "1M": timedelta(days=30),
    "3M": timedelta(days=91),
    "1Y": timedelta(days=365),
}

PERIOD_ORDER = ["1D", "1W", "1M", "3M", "YTD", "1Y"]


def _to_date(value):
    """Parse a date that may arrive as a date, a datetime, or an ISO string.

    The parquet writes 'YYYY-MM-DD' strings, ProfileStock.date_added is an aware
    datetime, and tests pass date objects.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    # Tolerate full timestamps ('2026-03-04T11:20:00Z') as well as bare dates.
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _pct_change(start, end):
    """Percentage move from start to end, or None if it cannot be computed.

    A zero or negative start price would make the ratio meaningless rather than
    merely large, so those return None instead of an enormous number.
    """
    if start is None or end is None:
        return None
    try:
        start = float(start)
        end = float(end)
    except (TypeError, ValueError):
        return None
    if start <= 0:
        return None
    return round((end - start) / start * 100, 2)


def index_on_or_after(dates, target):
    """Position of the first date >= target, or None if every date precedes it.

    Used for the since-added lookup: a stock added on a Saturday has no bar of
    its own, so the first trading day after it is the correct starting point.

    `dates` must be ascending, which is how the parquet stores them.
    """
    target = _to_date(target)
    if target is None or not dates:
        return None
    lo, hi = 0, len(dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if _to_date(dates[mid]) < target:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(dates) else None


def index_on_or_before(dates, target):
    """Position of the last date <= target, or None if every date follows it.

    Used for the lookback periods: '1 month ago' lands on a weekend often enough
    that anchoring to the closest earlier trading day is the only sane reading.
    """
    target = _to_date(target)
    if target is None or not dates:
        return None
    lo, hi = 0, len(dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if _to_date(dates[mid]) <= target:
            lo = mid + 1
        else:
            hi = mid
    return lo - 1 if lo > 0 else None


def period_returns(dates, prices):
    """Labelled percentage returns ending at the most recent close.

    Returns a dict keyed by PERIOD_ORDER. A period whose start date predates the
    available history maps to None rather than being silently anchored to the
    first bar -- reporting a 1Y return computed over four months would be wrong
    in a way the reader could not see.
    """
    result = {label: None for label in PERIOD_ORDER}
    if not dates or not prices or len(dates) != len(prices):
        return result

    last_index = len(prices) - 1
    latest = prices[last_index]
    last_date = _to_date(dates[last_index])
    if latest is None or last_date is None:
        return result

    # 1D is the previous bar, whatever calendar gap precedes it.
    if last_index >= 1:
        result["1D"] = _pct_change(prices[last_index - 1], latest)

    first_date = _to_date(dates[0])
    for label, offset in PERIOD_OFFSETS.items():
        start_target = last_date - offset
        # Refuse to report a period the history cannot cover.
        if first_date is None or start_target < first_date:
            continue
        i = index_on_or_before(dates, start_target)
        if i is not None:
            result[label] = _pct_change(prices[i], latest)

    # YTD anchors to the last close of the previous year, so January reports the
    # move from the year's opening level rather than a near-zero number.
    ytd_anchor = date(last_date.year - 1, 12, 31)
    if first_date is not None and ytd_anchor >= first_date:
        i = index_on_or_before(dates, ytd_anchor)
        if i is not None:
            result["YTD"] = _pct_change(prices[i], latest)

    return result


def since_added_return(dates, prices, date_added):
    """Return since the stock joined the watchlist.

    ``truncated`` marks the case where the stock was added before the available
    history begins: the number is still useful but covers a shorter window than
    the added date implies, and the UI says so rather than overstating it.

    Returns None when there is no close at or after the added date -- a stock
    added today has no completed bar yet, and rendering 0.00% would read as
    'flat' rather than 'not yet measurable'.
    """
    added = _to_date(date_added)
    if added is None or not dates or not prices or len(dates) != len(prices):
        return None

    first_date = _to_date(dates[0])
    truncated = first_date is not None and added < first_date

    start_index = 0 if truncated else index_on_or_after(dates, added)
    if start_index is None:
        return None

    last_index = len(prices) - 1
    if start_index >= last_index:
        # Added on or after the most recent close: nothing has elapsed yet.
        return None

    change = _pct_change(prices[start_index], prices[last_index])
    if change is None:
        return None

    return {
        "date": str(dates[start_index])[:10],
        "start_price": float(prices[start_index]),
        "return": change,
        "truncated": truncated,
    }
