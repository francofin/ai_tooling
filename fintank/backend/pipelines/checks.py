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
    "attribution": {"window", "level", "key", "contribution_pp"},
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


def _capped(status: str, name: str, warn_only: dict) -> str:
    """A FAIL for a name in a WARN_ONLY_* table becomes that name's status."""
    return warn_only.get(name, status) if status == FAIL else status


def check_build_stage(result: StageResult) -> CheckResult:
    """check_fetch (used for fetch and build stages alike), except that a
    WARN_ONLY_STAGES stage is capped at its own status."""
    out = check_fetch(result)
    out.status = _capped(out.status, result.name, t.WARN_ONLY_STAGES)
    return out


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
            status = _capped(FAIL, name, t.WARN_ONLY_DATASETS)
        elif ratio < t.COUNT_RATIO_WARN:
            status = WARN
        else:
            status = PASS
        out.append(CheckResult(f"counts.{name}", status, round(ratio, 4),
                               t.COUNT_RATIO_WARN, f"{now} vs {base} last published"))
    return out


def check_minimums(counts: dict) -> list[CheckResult]:
    """Absolute floors for site-wide outputs — catches a truncated build even on
    the first publish, when check_counts has no baseline. A WARN_ONLY_DATASETS
    dataset below its floor is capped at its own status."""
    out = []
    for name, floor in sorted(t.MIN_COUNTS.items()):
        now = counts.get(name, 0)
        status = _capped(FAIL, name, t.WARN_ONLY_DATASETS) if now < floor else PASS
        out.append(CheckResult(f"minimum.{name}", status, now,
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


def check_attribution(detail: dict,
                      expected_lists: int = len(cfg.CONSTITUENT_PROXY_ETFS)) -> list[CheckResult]:
    """Per list: price coverage, the sectors-equal-index identity, non-finite
    values and the residual against the proxy ETF, worst window shown. Every
    problem is t.ATTRIBUTION_FAILURE_STATUS (WARN in v1)."""
    bad = t.ATTRIBUTION_FAILURE_STATUS
    lists = {sub: info for sub, info in detail.items()
             if isinstance(info, dict) and "windows" in info}
    out = [CheckResult("attribution.lists", bad if len(lists) < expected_lists else PASS,
                       len(lists), expected_lists,
                       f"{len(lists)} of {expected_lists} lists attributed")]
    for sub, info in sorted(lists.items()):
        windows = info["windows"]
        name = f"attribution.{sub}"

        floor = (t.ATTRIBUTION_MIN_COVERAGE_LONG_TAIL if sub in t.ATTRIBUTION_LONG_TAIL
                 else t.ATTRIBUTION_MIN_COVERAGE)
        # Joined names are priced (they listed mid-window); only unattributed
        # weight is missing data.
        w, cov = min(((w, v.get("priced_weight_pct", v["covered_weight_pct"]))
                      for w, v in windows.items()), key=lambda x: x[1])
        out.append(CheckResult(f"{name}.coverage", bad if cov < floor else PASS,
                               round(cov, 2), floor, f"{cov:.1f}% of weight priced ({w})"))

        w, err = max(((w, v["identity_error_pp"]) for w, v in windows.items()),
                     key=lambda x: x[1])
        out.append(CheckResult(f"{name}.identity",
                               bad if err > t.ATTRIBUTION_IDENTITY_TOL_PP else PASS,
                               err, t.ATTRIBUTION_IDENTITY_TOL_PP,
                               f"sectors vs index / weights vs 100%: {err:.2e}pp ({w})"))

        nf = sum(v["non_finite"] for v in windows.values())
        out.append(CheckResult(f"{name}.non_finite", bad if nf else PASS, nf, 0,
                               f"{nf} non-finite served values"))

        residuals = {w: v["residual_pp"] for w, v in windows.items()
                     if v["residual_pp"] is not None}
        if not residuals:
            out.append(CheckResult(f"{name}.residual", PASS, None, None, "no reference"))
            continue
        w, res = max(residuals.items(), key=lambda x: abs(x[1]))
        if sub in t.ATTRIBUTION_UNCHECKED_RESIDUAL:
            out.append(CheckResult(f"{name}.residual", PASS, res, None,
                                   f"{res:+.2f}pp vs ETF ({w}); local currency, not checked"))
            continue
        note = ""
        if sub in t.ATTRIBUTION_MIGRATING:
            skipped = {k: residuals.pop(k) for k in t.ATTRIBUTION_LONG_WINDOWS & set(residuals)}
            if skipped:
                note = "; " + ", ".join(f"{k} {v:+.2f}pp" for k, v in skipped.items()) + \
                       " not checked (reconstitution)"
            if not residuals:
                out.append(CheckResult(f"{name}.residual", PASS, res, None, note.lstrip("; ")))
                continue
            w, res = max(residuals.items(), key=lambda x: abs(x[1]))
        column = 1 if sub in t.ATTRIBUTION_SMALL else 0
        over = {w: abs(r) * 100 for w, r in residuals.items()
                if abs(r) * 100 > t.ATTRIBUTION_RESIDUAL_WARN_BP.get(w, (150, 250))[column]}
        out.append(CheckResult(f"{name}.residual", bad if over else PASS, res, None,
                               f"worst {res:+.2f}pp vs ETF ({w})"
                               + (f"; over limit: {', '.join(over)}" if over else "") + note))
    return out


def check_fund_finder(detail: dict, previous: dict | None) -> list[CheckResult]:
    """Fund finder build detail (build_fund_finder) against the thresholds;
    `previous` is the last published run's detail, for the ADR-link drop.
    Every problem is t.FUND_FINDER_FAILURE_STATUS (WARN at first)."""
    bad = t.FUND_FINDER_FAILURE_STATUS
    out = []

    n = detail.get("funds_with_rows", 0)
    out.append(CheckResult("fund_finder.funds", bad if n < t.FUND_MIN_FUNDS else PASS,
                           n, t.FUND_MIN_FUNDS,
                           f"{n:,} of {detail.get('funds', 0):,} funds have holdings"))

    outside = detail.get("weight_sum_outside", [])
    out.append(CheckResult("fund_finder.weight_sum", bad if outside else PASS,
                           len(outside), 0,
                           f"{len(outside)} funds' weights sum outside 90–110%"
                           + (": " + ", ".join(outside[:20]) if outside else "")))

    for sym, cc in sorted(detail.get("crosscheck", {}).items()):
        name = f"fund_finder.crosscheck.{sym}"
        if not cc["in_universe"]:
            out.append(CheckResult(name, PASS, None, None,
                                   "no fund FMP lists is in our universe"))
            continue
        floor = 100 * t.FUND_CROSSCHECK_PRESENT
        low = cc["present_pct"] < floor or cc["weight_ok_pct"] < floor
        out.append(CheckResult(
            name, bad if low else PASS, round(cc["present_pct"], 2), floor,
            f"of {cc['in_universe']} in-universe funds FMP lists: "
            f"{cc['present_pct']:.1f}% in the lookup, {cc['weight_ok_pct']:.1f}% "
            f"within {t.FUND_CROSSCHECK_WEIGHT_PP}pp"))

    pairs = detail.get("adr_pairs", {})
    broken = sorted(adr for adr in ("TSM", "ASML", "NVO")
                    if not (pairs.get(adr) or {}).get("adr")
                    or pairs[adr]["adr"] != pairs[adr].get("home"))
    out.append(CheckResult("fund_finder.adr_pairs", bad if broken else PASS,
                           len(broken), 0,
                           "not linked to the home line: " + ", ".join(broken)
                           if broken else "TSM, ASML, NVO link to their home lines"))

    pct = detail.get("adr_link_pct", 0.0)
    base = (previous or {}).get("adr_link_pct")
    if base is None:
        out.append(CheckResult("fund_finder.adr_links", PASS, round(pct, 2), None,
                               f"{pct:.1f}% of ADRs linked; no baseline"))
    else:
        drop = base - pct
        out.append(CheckResult(
            "fund_finder.adr_links", bad if drop > t.FUND_ADR_LINK_DROP_PP else PASS,
            round(pct, 2), t.FUND_ADR_LINK_DROP_PP,
            f"{pct:.1f}% of ADRs linked (last published {base:.1f}%)"))

    left = sorted(set(detail.get("unexpanded", [])) | set(detail.get("deep_chains", [])))
    out.append(CheckResult("fund_finder.look_through", bad if left else PASS,
                           len(left), 0,
                           f"{len(left)} funds still hold a fund not looked through"
                           + (": " + ", ".join(left[:20]) if left else "")))

    xeqt = detail.get("xeqt_asset_rows", 0)
    out.append(CheckResult("fund_finder.xeqt", bad if xeqt <= t.FUND_XEQT_MIN_ROWS else PASS,
                           xeqt, t.FUND_XEQT_MIN_ROWS,
                           f"XEQT.TO has {xeqt:,} holding rows with an asset"))
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
