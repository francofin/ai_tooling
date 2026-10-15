import os
import time

import pytest

from pipelines import state


def make_tree(root):
    files = {
        "stock_data_json/stock_prices/sp500/AAA_prices.json": '{"a": 1}',
        "stock_data_json/ratios_ttm/sp500/AAA_ratios_ttm.json": "[]",
        "index_data/constituents/sp500_const_constituents.json": "[]",
        "stock_data/revenue_segments/AAA_segments.json": "{}",
        "stock_data/stock_prices/daily/sp500/AAA_prices.parquet": "not state",
    }
    for rel, text in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
    return files


def read_tree(root):
    out = {}
    for dirpath, _, names in os.walk(root):
        for name in names:
            path = os.path.join(dirpath, name)
            out[os.path.relpath(path, root)] = open(path).read()
    return out


def test_state_units(tmp_path):
    make_tree(tmp_path)
    assert state.state_units(str(tmp_path)) == [
        "stock_data_json/ratios_ttm", "stock_data_json/stock_prices",
        "index_data", "stock_data/revenue_segments"]


def test_push_then_pull_restores_state(aws, tmp_path):
    aws.create_bucket(Bucket="state")
    src = tmp_path / "src"
    files = make_tree(src)
    pushed = state.push(aws, "state", str(src))
    assert len(pushed) == 4
    dest = tmp_path / "dest"
    restored = state.pull(aws, "state", str(dest))
    assert sorted(restored) == sorted(pushed)
    expected = {k: v for k, v in files.items() if not k.startswith("stock_data/stock_prices")}
    assert read_tree(dest) == expected


def test_push_since_only_sends_changed_units(aws, tmp_path):
    aws.create_bucket(Bucket="state")
    make_tree(tmp_path)
    old = time.time() - 3600
    for dirpath, _, names in os.walk(tmp_path):
        for name in names:
            os.utime(os.path.join(dirpath, name), (old, old))
    marker = time.time() - 60
    with open(tmp_path / "stock_data_json/stock_prices/sp500/AAA_prices.json", "w") as f:
        f.write('{"a": 2}')
    assert state.push(aws, "state", str(tmp_path), since=marker) == [
        "stock_data_json/stock_prices"]


def test_pull_replaces_local_unit(aws, tmp_path):
    aws.create_bucket(Bucket="state")
    make_tree(tmp_path)
    state.push(aws, "state", str(tmp_path))
    stray = tmp_path / "index_data/constituents/stray.json"
    stray.write_text("[]")
    state.pull(aws, "state", str(tmp_path))
    assert not stray.exists()
