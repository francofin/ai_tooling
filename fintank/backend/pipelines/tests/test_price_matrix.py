import os

import pandas as pd


def _write(p, sub, symbol, close, n=300, end="2026-11-13"):
    """A daily price parquet shaped like build_price_parquets' output."""
    folder = p.price_parquet_dir("daily", sub)
    os.makedirs(folder, exist_ok=True)
    dates = pd.bdate_range(end=end, periods=n)
    frame = pd.DataFrame({"close": [close + i for i in range(n)],
                          "adjClose": [close + i - 0.5 for i in range(n)]},
                         index=dates.strftime("%Y-%m-%d"))
    frame.index.name = "date"
    frame.to_parquet(os.path.join(folder, f"{symbol}_prices.parquet"))
    return dates


def test_matrix_reads_close_since_a_date(pipeline):
    dates = _write(pipeline, "sp500", "AAA", 100.0)
    prices, missing = pipeline._load_adj_close_matrix(
        "sp500", ["AAA"], column="close", since=dates[-100])
    assert missing == [] and len(prices) == 100
    assert prices.index[0] == dates[-100].strftime("%Y-%m-%d")   # index as stored
    assert prices["AAA"].iloc[-1] == 100.0 + 299


def test_any_folder_finds_a_symbol_saved_under_another_list(pipeline):
    _write(pipeline, "tsx", "X.TO", 10.0)
    _write(pipeline, "tsx_small_cap", "Y.TO", 20.0)
    prices, missing = pipeline._load_adj_close_matrix(
        "tsx_small_cap", ["X.TO", "Y.TO", "Z.TO"], column="close", any_folder=True)
    assert set(prices.columns) == {"X.TO", "Y.TO"} and missing == ["Z.TO"]


def test_own_folder_wins_when_a_symbol_is_in_two(pipeline):
    _write(pipeline, "sp500", "MRNA", 100.0)
    _write(pipeline, "msci_sm", "MRNA", 500.0)
    prices, _ = pipeline._load_adj_close_matrix("msci_sm", ["MRNA"], column="close",
                                                any_folder=True)
    assert prices["MRNA"].iloc[0] == 500.0 + 200        # default lookback=100 rows
    index = pipeline._price_file_index("sp500")
    assert index["MRNA"].endswith(os.path.join("sp500", "MRNA_prices.parquet"))


def test_contr_to_var_call_unchanged(pipeline):
    _write(pipeline, "sp500", "AAA", 100.0)
    prices, missing = pipeline._load_adj_close_matrix("sp500", ["AAA", "BBB"])
    assert len(prices) == 100 and missing == ["BBB"]
    assert prices["AAA"].iloc[-1] == 100.0 + 299 - 0.5   # adjClose
