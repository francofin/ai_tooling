"""Run checks. Each function is pure (it reads files it is handed, never the
network) and returns CheckResult(s). The run's verdict is the worst status.

Exceptions are never turned into checks: a crash fails the run, and a failed
run publishes nothing."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass

from pipelines import thresholds as t
from pipelines.results import StageResult
from pipelines.stock_pipeline import FACTOR_METRICS_COLUMNS, cfg

PASS, WARN, FAIL = "pass", "warn", "fail"
_RANK = {PASS: 0, WARN: 1, FAIL: 2}

# Columns a parquet must carry, per output dataset. Datasets not listed are
# only checked for being readable (mapped fundamentals keep whatever FMP sent).
REQUIRED_COLUMNS = {
    "stock_prices": {"adjClose", "returns"},
    "index_prices": {"adjClose", "returns"},
    "factor_metrics": set(FACTOR_METRICS_COLUMNS),
    "profile_aggregates": set(cfg.FIELD_MAPPINGS["long_profiles"].values()),
}


@dataclass
class CheckResult:
    name: str
    status: str
    value: object = None
    threshold: object = None
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def verdict(results) -> str:
    worst = PASS
    for result in results:
        if _RANK[result.status] > _RANK[worst]:
            worst = result.status
    return worst


def check_constituents(result: StageResult) -> list[CheckResult]:
    out = []
    for key, info in sorted(result.detail.get("lists", {}).items()):
        name = f"constituents.{key}"
        if info["status"] == "kept":
            out.append(CheckResult(name, FAIL, None, None,
                                   f"refresh failed, previous list kept: {info['error']}"))
            continue
        previous, new = info["previous"], info["new"]
        if previous and new / previous - 1 > t.CONSTITUENT_GROWTH_WARN:
            out.append(CheckResult(name, WARN, new, t.CONSTITUENT_GROWTH_WARN,
                                   f"grew {previous} → {new}"))
        else:
            out.append(CheckResult(name, PASS, new, None, f"{previous} → {new}"))
    return out


def check_fetch(result: StageResult) -> CheckResult:
    rate = result.failure_rate
    if rate > t.FETCH_FAILURE_FAIL:
        status = FAIL
    elif rate > t.FETCH_FAILURE_WARN:
        status = WARN
    else:
        status = PASS
    detail = f"{result.failed} of {result.attempted} failed"
    if result.failed_items:
        detail += ": " + ", ".join(result.failed_items[:10])
    return CheckResult(f"{result.name}.failure_rate", status, round(rate, 4),
                       t.FETCH_FAILURE_WARN, detail)


def recent_nyse_sessions(today: dt.date, days: int = 30) -> list[dt.date]:
    """Completed NYSE sessions in the `days` before `today` (today excluded: a
    run during market hours must not expect today's close)."""
    import pandas_market_calendars as mcal

    schedule = mcal.get_calendar("NYSE").schedule(
        start_date=today - dt.timedelta(days=days),
        end_date=today - dt.timedelta(days=1))
    return [ts.date() for ts in schedule.index]


def check_freshness(modal_dates: dict, sessions: list[dt.date]) -> list[CheckResult]:
    out = []
    for sub, modal in sorted(modal_dates.items()):
        name = f"freshness.{sub}"
        if modal is None:
            out.append(CheckResult(name, FAIL, None, t.FRESHNESS_WARN_SESSIONS,
                                   "no price files"))
            continue
        last = dt.date.fromisoformat(modal)
        behind = sum(1 for s in sessions if s > last)
        if behind == 0:
            status = PASS
        elif behind <= t.FRESHNESS_WARN_SESSIONS:
            status = WARN
        else:
            status = FAIL
        out.append(CheckResult(name, status, behind, t.FRESHNESS_WARN_SESSIONS,
                               f"modal last date {last}, {behind} NYSE session(s) behind"))
    return out


def _parquet_columns(path) -> set:
    import pyarrow.parquet as pq

    return set(pq.read_schema(path).names)


def check_outputs_readable(outputs, read_schema=None) -> list[CheckResult]:
    """One result per dataset: every parquet opens and has its required
    columns; every JSON parses."""
    read_schema = read_schema or _parquet_columns
    bad, seen = {}, {}
    for output in outputs:
        seen[output.dataset] = seen.get(output.dataset, 0) + 1
        try:
            if output.local_path.endswith(".parquet"):
                columns = read_schema(output.local_path)      # raises if unreadable
                missing = REQUIRED_COLUMNS.get(output.dataset, set()) - columns
                if missing:
                    raise ValueError(f"missing columns {sorted(missing)}")
            else:
                with open(output.local_path) as f:
                    json.load(f)
        except Exception as e:  # noqa: BLE001 — any unreadable file is a finding
            bad.setdefault(output.dataset, []).append(f"{output.local_path}: {e}")
    out = []
    for dataset in sorted(seen):
        problems = bad.get(dataset, [])
        out.append(CheckResult(
            f"readable.{dataset}", FAIL if problems else PASS, len(problems), 0,
            f"{len(problems)} of {seen[dataset]} unreadable"
            + (": " + "; ".join(problems[:5]) if problems else "")))
    return out


def check_counts(current: dict, baseline: dict | None) -> list[CheckResult]:
    if not baseline:
        return [CheckResult("counts", PASS, None, None, "no published baseline yet")]
    out = []
    for name, base in sorted(baseline.items()):
        if not base:
            continue
        now = current.get(name, 0)
        ratio = now / base
        if ratio < t.COUNT_RATIO_FAIL:
            status = FAIL
        elif ratio < t.COUNT_RATIO_WARN:
            status = WARN
        else:
            status = PASS
        out.append(CheckResult(f"counts.{name}", status, round(ratio, 4),
                               t.COUNT_RATIO_WARN, f"{now} vs {base} last published"))
    return out


def check_minimums(counts: dict) -> list[CheckResult]:
    """Absolute floors for site-wide outputs — catches a truncated build even on
    the first publish, when check_counts has no baseline."""
    out = []
    for name, floor in sorted(t.MIN_COUNTS.items()):
        now = counts.get(name, 0)
        out.append(CheckResult(f"minimum.{name}", FAIL if now < floor else PASS, now,
                               floor, f"{now:,} (minimum {floor:,})"))
    return out


def check_factor_coverage(lists: dict, members: dict) -> list[CheckResult]:
    """Factor rows per list against the list's constituent count."""
    out = []
    for sub, info in sorted(lists.items()):
        total = members.get(sub)
        if not total:
            continue
        share = info["rows"] / total
        out.append(CheckResult(
            f"factor_coverage.{sub}", FAIL if share < t.FACTOR_MIN_COVERAGE else PASS,
            round(share, 4), t.FACTOR_MIN_COVERAGE,
            f"{info['rows']:,} rows for {total:,} constituents ({share:.0%})"))
    return out


def check_factor_staleness(current: dict, baseline: dict | None) -> list[CheckResult]:
    out = []
    for sub, info in sorted(current.items()):
        rows, stale = info["rows"], info["stale"]
        share = stale / rows if rows else 0.0
        base = (baseline or {}).get(sub, {}).get("stale")
        if share > t.STALE_SHARE_FAIL:
            status = FAIL
        elif (base is not None and stale >= t.STALE_GROWTH_WARN * base
              and stale - base >= t.STALE_GROWTH_MIN_DELTA):
            status = WARN
        else:
            status = PASS
        out.append(CheckResult(f"factor_staleness.{sub}", status, stale,
                               t.STALE_SHARE_FAIL,
                               f"{stale} of {rows} stale (last published: {base})"))
    return out


def check_price_sanity(series_by_symbol) -> list[CheckResult]:
    non_positive, jumps, checked = [], [], 0
    for symbol, adj_close in series_by_symbol:
        checked += 1
        recent = adj_close.dropna().iloc[-(t.PRICE_RECENT_ROWS + 1):]
        if (recent <= 0).any():
            non_positive.append(symbol)
        if (recent.pct_change().abs() > t.PRICE_JUMP).any():
            jumps.append(symbol)
    share = len(jumps) / checked if checked else 0.0
    return [
        CheckResult("prices.non_positive", WARN if non_positive else PASS,
                    len(non_positive), 0, ", ".join(non_positive[:20])),
        CheckResult("prices.large_moves",
                    WARN if share > t.PRICE_JUMP_SHARE_WARN else PASS,
                    len(jumps), t.PRICE_JUMP_SHARE_WARN,
                    f"{len(jumps)} of {checked} symbols moved more than "
                    f"{t.PRICE_JUMP:.0%} in a day recently"
                    + (": " + ", ".join(jumps[:20]) if jumps else "")),
    ]


def check_econ(last_dates: dict, today: dt.date) -> list[CheckResult]:
    out = []
    for sid, last in sorted(last_dates.items()):
        limit = t.ECON_MAX_LAG_DAYS.get(sid, t.ECON_DEFAULT_MAX_LAG_DAYS)
        lag = (today - dt.date.fromisoformat(last)).days
        out.append(CheckResult(f"econ.{sid}", WARN if lag > limit else PASS, lag,
                               limit, f"last observation {last}, {lag} days ago"))
    return out


def check_staging(changed: int, prices_saved: int) -> CheckResult:
    if changed == 0 and prices_saved > 0:
        return CheckResult("staging", FAIL, 0, None,
                           "no file differs from live although prices were fetched")
    return CheckResult("staging", PASS, changed, None, f"{changed} files differ from live")
