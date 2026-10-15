"""The weekly run: which stages, in what order, with resume.

Fetch stages (and the constituent refresh) are checkpointed: when one
finishes, the state folders it changed are pushed to the state bucket and
progress.json records it, so a retried run skips it. Build stages are never
checkpointed — their outputs live on the container's disk, so a fresh
container rebuilds them from the pulled JSON."""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

from pipelines import state
from pipelines.checks import (PASS, CheckResult, check_constituents, check_counts,
                              check_econ, check_factor_staleness, check_fetch,
                              check_freshness, check_outputs_readable,
                              check_price_sanity, check_staging, recent_nyse_sessions)
from pipelines.notify import held_message
from pipelines.outputs import collect_outputs
from pipelines.publish import diff_outputs, stage_changed
from pipelines.report import RunReport, now_iso
from pipelines.results import StageResult
from pipelines.store import LAST_PUBLISHED_REPORT, LIVE_MANIFEST, S3Store, run_key

BUILD_STAGES = [
    "build_price_parquets", "build_fundamentals_parquets", "build_profile_aggregate",
    "build_factor_metrics", "build_contr_to_var", "build_econ_parquets",
    "build_relative_performance",
]
LEAN_STAGES = [
    "refresh_constituents", "fetch_stock_prices", "fetch_etf_prices",
    "fetch_ttm_ratios", "fetch_sector_history", "fetch_index_prices",
    "fetch_fred_series", *BUILD_STAGES,
]
FULL_STAGES = [
    "refresh_constituents", "fetch_stock_prices", "fetch_etf_prices",
    "fetch_profiles", "fetch_etf_profiles", "fetch_financial_statements",
    "fetch_ratios", "fetch_ttm_ratios", "fetch_revenue_segments",
    "fetch_sector_history", "fetch_index_prices", "fetch_fred_series", *BUILD_STAGES,
]
CHECKPOINTED = frozenset(s for s in FULL_STAGES if s not in BUILD_STAGES)

# The arguments the notebooks used. A full-history price window costs the same
# number of calls and avoids the gap and split-seam problems (see
# fetch_stock_prices.__doc__).
FROM_DATES = {"fetch_stock_prices": "1999-01-01", "fetch_etf_prices": "1999-01-01",
              "fetch_sector_history": "2010-01-01"}
LIMITABLE = frozenset({
    "fetch_stock_prices", "fetch_etf_prices", "fetch_profiles", "fetch_etf_profiles",
    "fetch_financial_statements", "fetch_ratios", "fetch_ttm_ratios",
    "fetch_revenue_segments", "build_price_parquets", "build_fundamentals_parquets",
    "build_factor_metrics",
})


def resolve_mode(mode: str, today: dt.date) -> str:
    if mode in ("lean", "full"):
        return mode
    if mode == "auto":
        return "full" if today.day <= 7 else "lean"
    raise ValueError(f"unknown mode {mode!r}")


def make_run_id(mode: str, now: dt.datetime) -> str:
    return f"{mode}-{now:%Y%m%d-%H%M}"


def stages_for(mode: str) -> list[str]:
    return FULL_STAGES if mode == "full" else LEAN_STAGES


def call_stage(p, name, limit=None) -> StageResult:
    kwargs = {}
    if name in FROM_DATES:
        kwargs["from_date"] = FROM_DATES[name]
    if limit is not None and name in LIMITABLE:
        kwargs["limit"] = limit
    return getattr(p, name)(**kwargs)


@dataclass
class RunContext:
    pipeline: object
    store: object                  # LocalStore (dry run) or S3Store
    run_id: str
    mode: str
    dry_run: bool = False
    limit: int | None = None
    s3: object = None              # S3 client; unused in dry runs
    state_bucket: str | None = None
    notifier: object = None
    always_hold: bool = False
    today: dt.date = field(default_factory=dt.date.today)
    log: object = print


def run_weekly(ctx: RunContext, checks=None, staging=None) -> RunReport:
    checks = checks or run_checks
    staging = staging or stage_outputs
    report_key = run_key(ctx.run_id, "report.json")
    progress_key = run_key(ctx.run_id, "progress.json")

    saved = ctx.store.get_json(report_key)
    report = (RunReport.from_dict(saved) if saved else
              RunReport(ctx.run_id, "weekly", ctx.mode, now_iso(), dry_run=ctx.dry_run))
    progress = ctx.store.get_json(progress_key, {"done": []})

    if not ctx.dry_run:
        state.pull(ctx.s3, ctx.state_bucket, ctx.pipeline.root, log=ctx.log)

    for name in stages_for(ctx.mode):
        if name in progress["done"]:
            ctx.log(f"{name}: finished in an earlier attempt, skipping")
            continue
        ctx.log(f"── {name}")
        started = time.time()
        result = call_stage(ctx.pipeline, name, ctx.limit)
        report.add_stage(result, time.time() - started)
        if name in CHECKPOINTED:
            if not ctx.dry_run:
                state.push(ctx.s3, ctx.state_bucket, ctx.pipeline.root,
                           since=started, log=ctx.log)
            progress["done"].append(name)
            ctx.store.put_json(progress_key, progress)
        ctx.store.put_json(report_key, report.to_dict())

    report.checks = []          # a resumed run re-checks from scratch
    checks(ctx, report)
    staging(ctx, report)
    report.finish()
    ctx.store.put_json(report_key, report.to_dict())

    hold = report.verdict != PASS or ctx.always_hold
    ctx.store.put_json(run_key(ctx.run_id, "verdict.json"),
                       {"run_id": ctx.run_id, "verdict": report.verdict, "hold": hold})
    if hold and ctx.notifier is not None:
        ctx.notifier.send(*held_message(report, ctx.state_bucket, ctx.always_hold))
    return report


def collect_counts(outputs, stages: dict) -> dict:
    counts = dict(Counter(o.dataset for o in outputs))
    factor = stages.get("build_factor_metrics")
    if factor:
        for sub, info in factor.detail.get("lists", {}).items():
            counts[f"factor_rows.{sub}"] = info["rows"]
    profiles = stages.get("build_profile_aggregate")
    if profiles:
        for name, rows in profiles.detail.get("rows", {}).items():
            counts[f"profile_rows.{name}"] = rows
    return counts


def recent_adj_close(outputs):
    """(symbol, adjClose) for every daily stock price parquet. Unreadable files
    are skipped here — check_outputs_readable already reports them."""
    for output in outputs:
        if output.key.startswith("stock_data/stock_prices/daily/"):
            symbol = os.path.basename(output.key).removesuffix("_prices.parquet")
            try:
                series = pd.read_parquet(output.local_path, columns=["adjClose"])["adjClose"]
            except Exception:  # noqa: BLE001
                continue
            yield symbol, series


def fred_last_dates(p) -> dict:
    out = {}
    folder = p.econ_json_dir
    if not os.path.isdir(folder):
        return out
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(folder, name)) as f:
            rows = json.load(f)
        dates = [r["date"] for r in rows if isinstance(r, dict) and "date" in r]
        if dates:
            out[name.removesuffix(".json")] = max(dates)
    return out


def run_checks(ctx: RunContext, report: RunReport) -> None:
    p = ctx.pipeline
    stages = {s["name"]: StageResult.from_dict(s) for s in report.stages}
    baseline = ctx.store.get_json(LAST_PUBLISHED_REPORT) or {}
    results = []
    if "refresh_constituents" in stages:
        results += check_constituents(stages["refresh_constituents"])
    results += [check_fetch(r) for name, r in stages.items() if name.startswith("fetch_")]
    modal = {sub: info["modal_last_date"] for sub, info in p.modal_last_dates().items()}
    results += check_freshness(modal, recent_nyse_sessions(ctx.today))
    outputs = collect_outputs(p)
    results += check_outputs_readable(outputs)
    report.counts = collect_counts(outputs, stages)
    results += check_counts(report.counts, baseline.get("counts"))
    if "build_factor_metrics" in stages:
        report.factor_staleness = stages["build_factor_metrics"].detail.get("lists", {})
    results += check_factor_staleness(report.factor_staleness,
                                      baseline.get("factor_staleness"))
    results += check_price_sanity(recent_adj_close(outputs))
    results += check_econ(fred_last_dates(p), ctx.today)
    report.add_checks(results)


def stage_outputs(ctx: RunContext, report: RunReport) -> None:
    if ctx.dry_run:
        report.add_checks([CheckResult("staging", PASS, None, None,
                                       "dry run: nothing staged")])
        return
    outputs = collect_outputs(ctx.pipeline)
    live = S3Store(ctx.state_bucket, ctx.s3).get_json(LIVE_MANIFEST, {})
    changed = diff_outputs(outputs, live)
    stage_changed(ctx.s3, ctx.state_bucket, ctx.run_id, changed, log=ctx.log)
    report.staged_files = len(changed)
    prices = report.stage("fetch_stock_prices")
    report.add_checks([check_staging(len(changed), prices["saved"] if prices else 0)])
