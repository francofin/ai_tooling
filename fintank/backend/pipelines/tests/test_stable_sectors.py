"""Sector snapshot and ETF sector exposure on FMP stable. Fakes only: no network."""
import datetime

from pipelines.tests.helpers import load_fixture


def counting_ticks(pipeline):
    ticks = []
    pipeline.limiter = type("L", (), {"tick": lambda self: ticks.append(1)})()
    return ticks


def snapshot_driver(pipeline, by_date):
    """by_date: {date string: {exchange: rows}}; records every url."""
    urls = []

    def get(url, timeout=30):
        urls.append(url)
        d = url.split("date=")[1].split("&")[0]
        ex = url.split("exchange=")[1].split("&")[0]
        return by_date.get(d, {}).get(ex, [])
    pipeline._get = get
    return urls


def test_snapshot_weekday_uses_today_two_calls(pipeline):
    nyse, nasdaq = load_fixture("sector_snapshot_nyse"), load_fixture("sector_snapshot_nasdaq")
    urls = snapshot_driver(pipeline, {"2026-11-20": {"NYSE": nyse, "NASDAQ": nasdaq}})
    ticks = counting_ticks(pipeline)
    rows, message = pipeline.get_sector_snapshot(today=datetime.date(2026, 11, 20))
    assert len(rows) == 11 and isinstance(message, str)
    assert len(urls) == 2 and len(ticks) == 2
    assert all("/stable/sector-performance-snapshot?" in u and "date=2026-11-20" in u for u in urls)
    assert "exchange=NYSE" in urls[0] and "exchange=NASDAQ" in urls[1]


def test_snapshot_weekend_uses_previous_friday(pipeline):
    nyse, nasdaq = load_fixture("sector_snapshot_nyse"), load_fixture("sector_snapshot_nasdaq")
    urls = snapshot_driver(pipeline, {"2026-11-20": {"NYSE": nyse, "NASDAQ": nasdaq}})
    rows, _ = pipeline.get_sector_snapshot(today=datetime.date(2026, 11, 22))  # Sunday
    assert len(rows) == 11 and len(urls) == 2 and "date=2026-11-20" in urls[0]


def test_snapshot_retries_previous_weekday_when_both_empty(pipeline):
    nyse, nasdaq = load_fixture("sector_snapshot_nyse"), load_fixture("sector_snapshot_nasdaq")
    urls = snapshot_driver(pipeline, {"2026-11-19": {"NYSE": nyse, "NASDAQ": nasdaq}})
    ticks = counting_ticks(pipeline)
    rows, _ = pipeline.get_sector_snapshot(today=datetime.date(2026, 11, 20))
    assert len(rows) == 11 and len(urls) == 4 and len(ticks) == 4
    assert "date=2026-11-19" in urls[2]


def test_snapshot_retry_from_monday_goes_to_friday(pipeline):
    urls = snapshot_driver(pipeline, {})
    rows, _ = pipeline.get_sector_snapshot(today=datetime.date(2026, 11, 23))  # Monday
    assert rows == [] and len(urls) == 4 and "date=2026-11-20" in urls[2]


def test_snapshot_one_exchange_empty_still_works(pipeline):
    nyse = load_fixture("sector_snapshot_nyse")
    urls = snapshot_driver(pipeline, {"2026-11-20": {"NYSE": nyse}})
    rows, _ = pipeline.get_sector_snapshot(today=datetime.date(2026, 11, 20))
    assert len(rows) == 11 and len(urls) == 2


def test_sector_exposure_accepts_float_weights(pipeline, monkeypatch):
    from pipelines import stock_pipeline as sp
    monkeypatch.setattr(sp.cfg, "CONSTITUENT_PROXY_ETFS", {"sp500_const": "SPY"})
    raw = load_fixture("etf_sector_weightings_spy")
    urls = []

    def get(url, timeout=30):
        urls.append(url)
        return raw
    pipeline._get = get
    ticks = counting_ticks(pipeline)
    df = pipeline.get_index_sector_exposure("sp500_const")
    assert "/stable/etf/sector-weightings?symbol=SPY" in urls[0] and len(urls) == 1
    assert len(ticks) == 1
    assert len(df) == 11 and df["weight"].is_monotonic_decreasing
    assert df["weight"].iloc[0] == max(r["weightPercentage"] for r in raw)
