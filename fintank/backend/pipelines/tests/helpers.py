"""Small builders for fixture data shaped like FMP payloads on disk."""
import json
import os

import pandas as pd


def write_constituents(p, key, symbols):
    path = p.constituents_path(key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump([{"asset": s, "weightPercentage": 100 / len(symbols)}
                   for s in symbols], f)


def price_rows(end, n=40, start_price=100.0):
    """FMP 'historical' rows, newest first, the last one on business day `end`."""
    days = pd.bdate_range(end=end, periods=n)
    rows = []
    for i, day in enumerate(days):
        price = start_price + i
        rows.append({"date": day.strftime("%Y-%m-%d"), "open": price,
                     "high": price, "low": price, "close": price,
                     "adjClose": price, "volume": 1000})
    return list(reversed(rows))


def write_price_json(p, sub, symbol, end, n=40):
    folder = p.json_dir("stock_prices", sub)
    os.makedirs(folder, exist_ok=True)
    with open(f"{folder}{symbol}_prices.json", "w") as f:
        json.dump({"symbol": symbol, "historical": price_rows(end, n)}, f)
