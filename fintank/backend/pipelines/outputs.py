"""Every file a run produces for the live bucket, and the exact key it goes
to. The keys reproduce what the upload_* methods in stock_pipeline.py write —
the site reads these, so a key change is a site outage."""
from __future__ import annotations

import os
from dataclasses import dataclass

from pipelines.stock_pipeline import cfg

# Publish order: per-symbol data first, the aggregates the site reads as
# "LIVE" last, so a page never sees new aggregates before their inputs.
DATASET_ORDER = ["constituents", "index_prices", "stock_prices", "fundamentals",
                 "revenue_segments", "contr_to_var", "factor_metrics",
                 "profile_aggregates", "econ"]


@dataclass(frozen=True)
class Output:
    local_path: str
    key: str
    dataset: str


def _files(folder: str) -> list[str]:
    if not os.path.isdir(folder):
        return []
    return sorted(f for f in os.listdir(folder)
                  if os.path.isfile(os.path.join(folder, f)))


def collect_outputs(p) -> list[Output]:
    out = []

    def add(folder, prefix, dataset):
        out.extend(Output(os.path.join(folder, name), f"{prefix}/{name}", dataset)
                   for name in _files(folder))

    add(os.path.join(p.index_root, "constituents"), "index_data/constituents",
        "constituents")
    for freq in ("daily", "monthly"):
        add(os.path.join(p.index_prices_dir, freq),
            f"index_data/index_prices_v2/{freq}", "index_prices")
    # upload_stock_prices drops the sub-universe folder from the key.
    for freq in ("daily", "monthly"):
        for sub in cfg.ALL_SUB_UNIVERSES:
            add(p.price_parquet_dir(freq, sub), f"stock_data/stock_prices/{freq}",
                "stock_prices")
    # upload_fundamentals drops it too.
    for data_type in cfg.FUNDAMENTALS_DATASETS:
        for sub in cfg.ALL_SUB_UNIVERSES:
            add(os.path.join(p.parquet_root, data_type, sub),
                f"stock_data/{data_type}", "fundamentals")
    add(p.revenue_segments_dir, "stock_data/revenue_segments", "revenue_segments")
    add(p.contr_to_var_dir, "index_data/contr_to_var", "contr_to_var")
    add(p.factor_metrics_dir, "stock_data/factor_metrics", "factor_metrics")
    for name in p.PROFILE_AGGREGATES:
        path = os.path.join(p.parquet_root, name, f"{name}.parquet")
        if os.path.isfile(path):
            out.append(Output(path, f"stock_data/{name}/{name}.parquet",
                              "profile_aggregates"))
    add(p.econ_dir, "econ_data", "econ")
    add(os.path.join(p.econ_dir, "relative_perf"), "econ_data/relative_perf", "econ")

    # A symbol in two lists maps to one key with identical content: keep the first.
    seen, unique = set(), []
    for output in out:
        if output.key not in seen:
            seen.add(output.key)
            unique.append(output)
    return unique
