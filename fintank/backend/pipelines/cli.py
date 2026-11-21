"""python -m pipelines <command> — the pipeline's command line.

On AWS the containers run `run`, `publish`, `news`, `earnings` and
`earnings-backfill`. Everything else is for Franc's terminal, with
AWS_PROFILE=fintank set.

ANTHROPIC_API_KEY is read from the process environment only (the ECS secret on
AWS), never from a .env file; missing means "unset", and an unset key makes no
Claude call."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import traceback

from pipelines import publish as publishing
from pipelines import state
from pipelines.notify import Notifier, complete_message, crash_message
from pipelines.report import RunReport
from pipelines.runner import RunContext, make_run_id, resolve_mode, run_weekly
from pipelines.store import (LocalStore, S3Store, aws_client, default_state_bucket,
                             live_bucket, run_key)

WEEKLY_MACHINE = "fintank-weekly-data-run"
NEWS_MACHINE = "fintank-daily-news"
EARNINGS_MACHINE = "fintank-daily-earnings"
EARNINGS_BACKFILL_MACHINE = "fintank-earnings-backfill"
CRASH_EMAIL_COMMANDS = ("run", "publish", "news", "earnings", "earnings-backfill")
BACKFILL_STEPS = ("submit", "check", "stage", "publish", "discarded")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m pipelines")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="weekly data run (the AWS task's entry point)")
    run.add_argument("--mode", choices=["lean", "full", "auto"], default="auto")
    run.add_argument("--run-id")
    run.add_argument("--dry-run", action="store_true",
                     help="local data only: no state pull/push, nothing staged, no "
                          "emails. Fetchers still write to the local data folder.")
    run.add_argument("--limit", type=int, help="symbols per list (smoke test)")

    pub = sub.add_parser("publish", help="copy a run's staged files to the live bucket")
    pub.add_argument("run_id")

    news = sub.add_parser("news", help="daily news run (the AWS task's entry point)")
    news.add_argument("--run-id")
    news.add_argument("--dry-run", action="store_true")
    searching = news.add_mutually_exclusive_group()
    searching.add_argument("--search", dest="search", action="store_true", default=None,
                           help="run the SerpAPI topics even on a non-search day")
    searching.add_argument("--no-search", dest="search", action="store_false",
                           help="skip the SerpAPI topics even on a search day")

    earn = sub.add_parser("earnings", help="daily earnings notes (the AWS task's entry point)")
    earn.add_argument("--run-id")
    earn.add_argument("--no-claude", action="store_true",
                      help="every step except the paid Claude call; writes the requests")
    earn.add_argument("--dry-run", action="store_true",
                      help="local stores only; implies --no-claude")
    backfill = sub.add_parser("earnings-backfill",
                              help="one backfill step (the backfill state machine's tasks)")
    backfill.add_argument("step", choices=BACKFILL_STEPS)
    backfill.add_argument("--run-id", required=True)
    backfill.add_argument("--no-claude", action="store_true")
    backfill.add_argument("--from-results", metavar="RUN_ID",
                          help="stage: re-check that run's saved results; no Claude call")

    start = sub.add_parser("start", help="start the weekly state machine now")
    start.add_argument("--mode", choices=["lean", "full"], required=True)
    start.add_argument("--limit", type=int)
    start.add_argument("--run-id", help="resume this run instead of starting a new one")
    start_news = sub.add_parser("start-news", help="start the news state machine now")
    start_news.add_argument("--search", action="store_true",
                            help="include the SerpAPI topics even on a non-search day")
    start_earn = sub.add_parser("start-earnings", help="start the daily earnings machine now")
    start_earn.add_argument("--no-claude", action="store_true")
    start_backfill = sub.add_parser("start-earnings-backfill",
                                    help="start the earnings backfill machine")
    start_backfill.add_argument("--no-claude", action="store_true",
                                help="free end-to-end test: builds the requests, no Claude")
    pull_note = sub.add_parser("pull-note", help="withdraw one published earnings note")
    pull_note.add_argument("symbol")
    pull_note.add_argument("quarter", help="<FY>-Q<n>, e.g. 2026-Q3")

    for name, text in (("approve", "publish a held run"),
                       ("discard", "throw a held run away"),
                       ("rollback", "restore every live file a run changed")):
        cmd = sub.add_parser(name, help=text)
        cmd.add_argument("run_id")
        if name == "rollback":
            cmd.add_argument("--yes", action="store_true")
            cmd.add_argument("--force", action="store_true",
                             help="roll back even though a later run changed the "
                                  "same files (restores this run's 'before' versions)")

    seed = sub.add_parser("seed-state", help="one time: upload local JSON state to AWS")
    seed.add_argument("--force", action="store_true",
                      help="overwrite state the bucket already holds")
    pull = sub.add_parser("pull-state", help="replace local state with the AWS copy")
    pull.add_argument("--yes", action="store_true")
    sub.add_parser("status", help="recent executions and run verdicts")
    return parser


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _data_root() -> str:
    from pipelines.stock_pipeline import DEFAULT_DATA_ROOT
    return os.getenv("PIPELINE_DATA_ROOT") or DEFAULT_DATA_ROOT


def _always_hold() -> bool:
    return os.getenv("ALWAYS_HOLD", "false").lower() == "true"


def cmd_run(args) -> int:
    from pipelines.stock_pipeline import StockDataPipeline

    p = StockDataPipeline()
    now = _utcnow()
    mode = resolve_mode(args.mode, now.date())
    run_id = args.run_id or make_run_id(mode, now)
    if args.dry_run:
        store, s3, bucket, notifier = LocalStore(os.path.join(p.root, ".runs")), None, None, None
    else:
        s3 = aws_client("s3")
        bucket = default_state_bucket()
        store, notifier = S3Store(bucket, s3), Notifier()
    ctx = RunContext(pipeline=p, store=store, run_id=run_id, mode=mode,
                     dry_run=args.dry_run, limit=args.limit, s3=s3, state_bucket=bucket,
                     notifier=notifier, always_hold=_always_hold(), today=now.date())
    report = run_weekly(ctx)
    print(report.summary())
    print(json.dumps({"run_id": run_id, "verdict": report.verdict}))
    return 0


def cmd_publish(args) -> int:
    s3, bucket = aws_client("s3"), default_state_bucket()
    result = publishing.publish(s3, bucket, live_bucket(), args.run_id)
    report = RunReport.from_dict(S3Store(bucket, s3).get_json(
        run_key(args.run_id, "report.json")))
    Notifier().send(*complete_message(report, result, bucket))
    print(json.dumps(result))
    return 0


def cmd_news(args) -> int:
    from pipelines.news import run_news
    from pipelines.stock_pipeline import BACKEND_DIR, env_values

    # Read, never exported (backend/.env's legacy AWS key must not reach boto3).
    env = env_values(os.path.join(BACKEND_DIR, ".env"))   # local runs; absent on AWS
    fmp_key = env("FMP_API")
    serp_key = env("SERPAPI_KEY") or env("SERP_API")
    if not (fmp_key and serp_key):
        raise SystemExit("FMP_API and SERPAPI_KEY must be set")
    root = _data_root()
    run_id = args.run_id or f"news-{_utcnow():%Y%m%d-%H%M}"
    if args.dry_run:
        store, upload, notifier, bucket = LocalStore(os.path.join(root, ".runs")), None, None, None
    else:
        s3, bucket, live = aws_client("s3"), default_state_bucket(), live_bucket()
        store, notifier = S3Store(bucket, s3), Notifier()

        def upload(path, key):
            s3.upload_file(path, live, key)
    report = run_news(run_id, fmp_key, serp_key, os.path.join(root, "news_json_articles"),
                      store, upload=upload, notifier=notifier,
                      notify_all=os.getenv("NEWS_NOTIFY", "all") == "all",
                      state_bucket=bucket, dry_run=args.dry_run, search=args.search)
    print(report.summary())
    return 0


def _claude_key() -> str:
    # Spend safety: the environment only, never a .env file.
    return os.environ.get("ANTHROPIC_API_KEY") or "unset"


def _earnings_keys() -> tuple[str, str]:
    from pipelines.stock_pipeline import BACKEND_DIR, env_values

    env = env_values(os.path.join(BACKEND_DIR, ".env"))   # FMP only; local runs
    fmp_key = env("FMP_API")
    if not fmp_key:
        raise SystemExit("FMP_API must be set")
    return fmp_key, _claude_key()


def _earnings_stores(dry_run):
    """(state store, live store, notifier, state bucket)."""
    if dry_run:
        root = _data_root()
        return LocalStore(os.path.join(root, ".runs")), LocalStore(root), None, None
    s3, bucket = aws_client("s3"), default_state_bucket()
    return S3Store(bucket, s3), S3Store(live_bucket(), s3), Notifier(), bucket


def cmd_earnings(args) -> int:
    from pipelines import earnings

    fmp_key, claude_key = _earnings_keys()
    no_claude = args.no_claude or args.dry_run
    if args.dry_run:
        claude_key = "unset"
    store, live, notifier, bucket = _earnings_stores(args.dry_run)
    run_id = args.run_id or f"earnings-{_utcnow():%Y%m%d-%H%M}"
    report = earnings.run_daily(run_id, fmp_key, claude_key, store, live, batch_client=None,
                                no_claude=no_claude, notifier=notifier,
                                state_bucket=bucket)
    print(report.summary())
    return 0


def _claude_client(claude_key):
    from pipelines.earnings_claude import AnthropicBatchClient, has_key

    if not has_key(claude_key):
        raise SystemExit("ANTHROPIC_API_KEY is unset; this step needs Claude")
    return AnthropicBatchClient(claude_key)


def cmd_earnings_backfill(args) -> int:
    from pipelines import earnings_backfill as backfill

    run_id = args.run_id
    fmp_key, claude_key = _earnings_keys() if args.step == "submit" else (None, _claude_key())
    store, live, _, _ = _earnings_stores(False)
    if args.step == "submit":
        result = backfill.backfill_submit(run_id, fmp_key, claude_key, store, live,
                                          batch_client=None, no_claude=args.no_claude)
    elif args.step == "check":
        result = backfill.backfill_check(run_id, store, batch_client=_claude_client(claude_key))
    elif args.step == "stage":
        client = None if args.from_results else _claude_client(claude_key)
        result = backfill.backfill_stage(run_id, store, batch_client=client,
                                         from_results=args.from_results)
    elif args.step == "publish":
        result = {"published": backfill.backfill_publish(run_id, store, live)}
    else:
        backfill.backfill_discarded(run_id, store)
        result = {"discarded": run_id}
    print(json.dumps(result))
    return 0


def cmd_pull_note(args) -> int:
    from pipelines import earnings

    s3 = aws_client("s3")
    live, state = S3Store(live_bucket(), s3), S3Store(default_state_bucket(), s3)
    try:
        earnings.pull_note(live, args.symbol, args.quarter, lock_store=state)
    except KeyError:
        raise SystemExit(f"{args.symbol} has no {args.quarter} note") from None
    except RuntimeError as e:
        raise SystemExit(f"pull-note refused: {e}; try again when the run ends") from None
    print(f"withdrew {args.symbol} {args.quarter}; the site drops it within the hour "
          "(the notes cache lasts 3600 s)")
    return 0


def _machine_arn(sfn, name) -> str:
    for page in sfn.get_paginator("list_state_machines").paginate():
        for machine in page["stateMachines"]:
            if machine["name"] == name:
                return machine["stateMachineArn"]
    raise SystemExit(f"state machine {name} not found — is the stack deployed?")


def cmd_start(args) -> int:
    sfn = aws_client("stepfunctions")
    payload = {"mode": args.mode}
    if args.limit:
        payload["limit"] = args.limit
    if args.run_id:
        payload["run_id"] = args.run_id
    response = sfn.start_execution(stateMachineArn=_machine_arn(sfn, WEEKLY_MACHINE),
                                   input=json.dumps(payload))
    print(f"started {response['executionArn']}")
    return 0


def cmd_start_news(args) -> int:
    sfn = aws_client("stepfunctions")
    payload = {"search": True} if args.search else {}
    response = sfn.start_execution(stateMachineArn=_machine_arn(sfn, NEWS_MACHINE),
                                   input=json.dumps(payload))
    print(f"started {response['executionArn']}")
    return 0


def cmd_start_earnings(args) -> int:
    sfn = aws_client("stepfunctions")
    machine = (EARNINGS_BACKFILL_MACHINE if args.command == "start-earnings-backfill"
               else EARNINGS_MACHINE)
    payload = {"no_claude": True} if args.no_claude else {}
    response = sfn.start_execution(stateMachineArn=_machine_arn(sfn, machine),
                                   input=json.dumps(payload))
    print(f"started {response['executionArn']}")
    return 0


def _approval_token(run_id) -> str:
    token = S3Store(default_state_bucket(), aws_client("s3")).get_json(
        run_key(run_id, "approval-token.json"))
    if not token:
        raise SystemExit(f"{run_id} is not waiting for approval")
    if isinstance(token, str):
        # Step Functions' putObject JSON-encodes the Body string it is given, so
        # the file holds a JSON string wrapping the object.
        token = json.loads(token)
    return token["task_token"]


def cmd_approve(args) -> int:
    aws_client("stepfunctions").send_task_success(
        taskToken=_approval_token(args.run_id), output=json.dumps({"decision": "approve"}))
    print(f"approved {args.run_id} — publishing now; you'll get an email when it's done")
    return 0


def cmd_discard(args) -> int:
    aws_client("stepfunctions").send_task_failure(
        taskToken=_approval_token(args.run_id), error="Discarded",
        cause="discarded from the command line")
    print(f"discarded {args.run_id} — nothing was published")
    return 0


def cmd_rollback(args) -> int:
    if not args.yes:
        answer = input(f"Restore every live file {args.run_id} changed? "
                       "Type the run id to confirm: ")
        if answer.strip() != args.run_id:
            print("aborted")
            return 1
    try:
        count = publishing.rollback(aws_client("s3"), default_state_bucket(),
                                    live_bucket(), args.run_id, force=args.force)
    except RuntimeError as e:
        raise SystemExit(f"rollback refused: {e}") from None
    print(f"restored {count} files")
    return 0


def cmd_seed_state(args) -> int:
    root = _data_root()
    s3, bucket = aws_client("s3"), default_state_bucket()
    existing = s3.list_objects_v2(Bucket=bucket, Prefix=state.STATE_PREFIX)
    archives = [o["Key"] for o in existing.get("Contents", [])
                if o["Key"].endswith(state.SUFFIX)]
    if archives and not args.force:
        print(f"s3://{bucket} already holds state ({len(archives)} archives, e.g. "
              f"{archives[0]}) — seeding again would overwrite what the runs have "
              "fetched since. Re-run with --force if that is really what you want.")
        return 1
    units = state.state_units(root)
    print(f"uploading {len(units)} state folders from {root} (this takes a while)")
    state.push(s3, bucket, root)
    return 0


def cmd_pull_state(args) -> int:
    root = _data_root()
    if not args.yes:
        print(f"pull-state REPLACES these folders under {root} with the AWS copy:\n  "
              + "\n  ".join(state.state_units(root) or ["(none yet)"])
              + "\nRe-run with --yes to continue.")
        return 1
    state.pull(aws_client("s3"), default_state_bucket(), root)
    return 0


def cmd_status(args) -> int:
    sfn = aws_client("stepfunctions")
    for name in (WEEKLY_MACHINE, NEWS_MACHINE):
        print(name)
        executions = sfn.list_executions(stateMachineArn=_machine_arn(sfn, name),
                                         maxResults=10)["executions"]
        for e in executions:
            print(f"  {e['startDate']:%Y-%m-%d %H:%M}  {e['status']:<10} {e['name']}")
    store = S3Store(default_state_bucket(), aws_client("s3"))
    print("recent runs")
    prefixes = sorted(store.list_prefixes("runs/"), key=lambda p: p.split("-", 1)[-1])
    for prefix in prefixes[-10:]:
        run_id = prefix.split("/")[1]
        verdict = (store.get_json(run_key(run_id, "verdict.json"))
                   or store.get_json(run_key(run_id, "report.json")) or {})
        print(f"  {run_id:<26} {verdict.get('verdict') or '-'}")
    return 0


COMMANDS = {
    "run": cmd_run, "publish": cmd_publish, "news": cmd_news,
    "earnings": cmd_earnings, "earnings-backfill": cmd_earnings_backfill,
    "pull-note": cmd_pull_note,
    "start": cmd_start, "start-news": cmd_start_news,
    "start-earnings": cmd_start_earnings, "start-earnings-backfill": cmd_start_earnings,
    "approve": cmd_approve, "discard": cmd_discard, "rollback": cmd_rollback,
    "seed-state": cmd_seed_state, "pull-state": cmd_pull_state, "status": cmd_status,
}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args) or 0
    except Exception:
        # The state machine also reports failures, but whether ECS marks a
        # non-zero exit as failed is not something to rely on — so the
        # container says so itself.
        if args.command in CRASH_EMAIL_COMMANDS and not getattr(args, "dry_run", False):
            run_id = getattr(args, "run_id", None) or "?"
            try:
                Notifier().send(*crash_message(args.command, run_id,
                                               traceback.format_exc()))
            except Exception:  # noqa: BLE001 — never mask the original error
                traceback.print_exc()
        raise
