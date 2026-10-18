"""The record of one run: every stage's counts and timing, every check, and
the verdict. Saved as runs/<run-id>/report.json and summarised in emails."""
from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import asdict, dataclass, field, fields

from pipelines.checks import CheckResult, verdict
from pipelines.results import StageResult


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1000:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1000
    return f"{n:.2f} GB"


def _fmt_seconds(seconds: float) -> str:
    minutes = int(seconds // 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m" if hours else f"{minutes}m{int(seconds % 60):02d}s"


@dataclass
class RunReport:
    run_id: str
    job: str                      # "weekly" | "news"
    mode: str                     # "lean" | "full" | "news"
    started_at: str
    dry_run: bool = False
    finished_at: str | None = None
    stages: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    factor_staleness: dict = field(default_factory=dict)
    staged_files: int = 0
    verdict: str | None = None

    def add_stage(self, result: StageResult, seconds: float, downloaded: int = 0) -> None:
        entry = result.to_dict()
        entry["seconds"] = round(seconds, 1)
        entry["bytes"] = downloaded
        self.stages = [s for s in self.stages if s["name"] != result.name] + [entry]

    def stage(self, name: str) -> dict | None:
        return next((s for s in self.stages if s["name"] == name), None)

    def add_checks(self, results) -> None:
        self.checks.extend(r.to_dict() for r in results)

    def finish(self, verdict_override: str | None = None) -> None:
        self.verdict = verdict_override or verdict(CheckResult(**c) for c in self.checks)
        self.finished_at = now_iso()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RunReport":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})

    def summary(self) -> str:
        lines = [f"Run {self.run_id} ({self.job}, {self.mode}) — verdict: "
                 f"{(self.verdict or 'n/a').upper()}"]
        if self.dry_run:
            lines.append("DRY RUN — nothing was staged or published.")
        timing = f"Started {self.started_at}"
        if self.finished_at:
            elapsed = (dt.datetime.fromisoformat(self.finished_at)
                       - dt.datetime.fromisoformat(self.started_at)).total_seconds()
            timing += f", finished {self.finished_at} ({_fmt_seconds(elapsed)})"
        lines += [timing, "", "Stages:"]
        for s in self.stages:
            size = f"  {_fmt_bytes(s['bytes'])}" if s.get("bytes") else ""
            lines.append(
                f"  {s['name']:<30} {s['attempted']:>6} attempted {s['saved']:>6} saved "
                f"{s['failed']:>5} failed ({s.get('failure_rate', 0):.1%})  "
                f"{_fmt_seconds(s.get('seconds', 0))}{size}")
        total = sum(s.get("bytes", 0) for s in self.stages)
        if total:
            lines.append(f"Downloaded from APIs: {_fmt_bytes(total)}")
        for s in self.stages:
            d = s.get("detail") or {}
            if "incremental" in d:
                lines.append(f"{s['name']}: {d['incremental']} recent window, "
                             f"{d['restated']} restated (full re-download), "
                             f"{d['full']} new")
        tally = Counter(c["status"] for c in self.checks)
        lines += ["", f"Checks: {tally.get('pass', 0)} pass, {tally.get('warn', 0)} warn, "
                      f"{tally.get('fail', 0)} fail"]
        for c in self.checks:
            if c["status"] != "pass":
                lines.append(f"  {c['status'].upper()} {c['name']} — {c['detail']}")
        if self.staged_files:
            lines += ["", f"Files that differ from live: {self.staged_files}"]
        return "\n".join(lines)
