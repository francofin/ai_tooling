from datetime import datetime, time
import pytz
from zoneinfo import ZoneInfo
from django.utils import timezone
from datetime import timedelta
import pandas_market_calendars as mcal

NY_TZ = ZoneInfo("America/New_York")
NYSE = mcal.get_calendar("NYSE")


def is_market_open_now():
    now = timezone.now().astimezone(NY_TZ)

    # Check weekday
    if now.weekday() >= 5:  # Saturday/Sunday
        return False

    # Check holiday / trading day
    schedule = NYSE.schedule(
        start_date=now.date(),
        end_date=now.date()
    )

    if schedule.empty:
        return False

    market_open = schedule.iloc[0]["market_open"].tz_convert(NY_TZ)
    market_close = schedule.iloc[0]["market_close"].tz_convert(NY_TZ)

    return market_open <= now <= market_close

def get_effective_market_date():
    """
    Returns:
        date object representing:
        - today if market is open
        - last trading day if market is closed
    """
    now = timezone.now().astimezone(NY_TZ)
    today = now.date()

    if is_market_open_now():
        return today

    # Look back far enough to cover long weekends/holidays
    start = today - timedelta(days=10)

    schedule = NYSE.schedule(start_date=start, end_date=today)

    if schedule.empty:
        raise RuntimeError("No NYSE trading days found")

    # Last trading day before now
    last_trading_day = schedule.index[-1].date()
    return last_trading_day