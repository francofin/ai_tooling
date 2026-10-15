import os

from pipelines.outputs import DATASET_ORDER, collect_outputs


def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()


def test_keys_match_the_upload_methods(pipeline):
    p, r = pipeline, pipeline.root
    touch(p.constituents_path("sp500_const"))
    touch(os.path.join(p.index_prices_dir, "daily", "sp500_prices.parquet"))
    touch(os.path.join(p.price_parquet_dir("daily", "sp500"), "AAA_prices.parquet"))
    touch(os.path.join(p.price_parquet_dir("daily", "nas"), "AAA_prices.parquet"))
    touch(os.path.join(p.parquet_root, "ratios_ttm", "sp500", "AAA_ratios_ttm.parquet"))
    touch(os.path.join(p.revenue_segments_dir, "AAA_segments.json"))
    touch(os.path.join(p.contr_to_var_dir, "sp500_contr_to_var.parquet"))
    touch(os.path.join(p.factor_metrics_dir, "sp500_metrics_returns.parquet"))
    touch(os.path.join(p.parquet_root, "company_profiles", "company_profiles.parquet"))
    touch(os.path.join(p.parquet_root, "long_profiles", "long_profiles.parquet"))
    touch(os.path.join(p.econ_dir, "cpi.parquet"))
    touch(os.path.join(p.econ_dir, "relative_perf", "eafevg.parquet"))

    keys = [(o.dataset, o.key) for o in collect_outputs(p)]
    assert keys == [
        ("constituents", "index_data/constituents/sp500_const_constituents.json"),
        ("index_prices", "index_data/index_prices_v2/daily/sp500_prices.parquet"),
        ("stock_prices", "stock_data/stock_prices/daily/AAA_prices.parquet"),  # once
        ("fundamentals", "stock_data/ratios_ttm/AAA_ratios_ttm.parquet"),
        ("revenue_segments", "stock_data/revenue_segments/AAA_segments.json"),
        ("contr_to_var", "index_data/contr_to_var/sp500_contr_to_var.parquet"),
        ("factor_metrics", "stock_data/factor_metrics/sp500_metrics_returns.parquet"),
        ("profile_aggregates", "stock_data/company_profiles/company_profiles.parquet"),
        ("profile_aggregates", "stock_data/long_profiles/long_profiles.parquet"),
        ("econ", "econ_data/cpi.parquet"),
        ("econ", "econ_data/relative_perf/eafevg.parquet"),
    ]
    assert [d for d, _ in keys] == sorted((d for d, _ in keys), key=DATASET_ORDER.index)
