# Recent changes and how we operate now

Last updated 2026-10-25. Read this first in a new session, then the linked docs for detail.

## TL;DR

- Market data is no longer refreshed from the notebooks. It runs on **AWS** (ECS Fargate + Step Functions), on a schedule, and every run is **checked before anything reaches the live bucket** `thetradingfloor`.
- **Weekly data run**: Saturdays 10:00 UTC (06:00 Toronto in summer, 05:00 in winter). Lean run normally; **full** run when the Saturday falls on days 1–7 of the month.
- **Daily news run**: 09:30 UTC. Tests each file, uploads only the ones that pass, no approval needed.
- Weekly runs currently **hold for manual approval** even when every check passes (`always_hold`). After 3 clean weekly runs, redeploy with `-c always_hold=false` so clean runs publish themselves.
- Price downloads are **incremental** since 2026-10-18 (commit `c333bd0`), after FMP's monthly bandwidth cap was hit.

## Where things live

| What | Where |
|---|---|
| Pipeline package (fetch, checks, staging, publish, news, CLI) | `backend/pipelines/` |
| Runbook (every command, what each email means) | `backend/pipelines/README.md` |
| Design + full AWS setup walkthrough | `docs/superpowers/specs/2026-10-14-automated-data-pipeline-design.md` |
| Implementation plan (rulings R1–R11) | `docs/superpowers/plans/2026-10-14-automated-data-pipeline.md` |
| AWS infrastructure (CDK, Python) | `infra/` (`app.py`, `pipeline_stack.py`, `statemachines/*.asl.json`) |
| Notebooks (`full_run`, `lean_run`, `news_updater`) | `backend/class_files/`: kept for exploration, **upload cells removed**; originals in `class_files/notebook_backups/` |

## AWS at a glance

- Account `137315715959`, region `us-east-1`, CDK stack `FintankPipeline`.
- Credentials: IAM Identity Center SSO profile **`fintank`**. Sessions last about 8h; on any auth error (including CDK's `KeyError: 'CDK_DEFAULT_ACCOUNT'`) run `aws sso login --profile fintank`.
- State bucket `fintank-pipeline-137315715959`:
  - `state/`: raw JSON inputs as `.tar.zst` archives. Each run pulls them and pushes back what changed.
  - `state/live-manifest.json`: what is live, used to diff each run.
  - `runs/<run-id>/`: report, staged files, verdict.
- Secrets: SSM SecureString `/fintank/pipeline/{FMP_API,FRED_API,SERPAPI_KEY}`.
- Alerts: SNS topic `fintank-pipeline-alerts` emails the owner (start, held, published, failed, news).
- Logs: CloudWatch log group `/fintank/pipeline`.
- The live bucket has versioning on, with a 30-day noncurrent-version lifecycle; that's what makes `rollback` possible.

## Operating commands

Run pipeline commands from `fintank/backend`, prefixed with `AWS_PROFILE=fintank ../../.venv/bin/python -m pipelines`:

| Situation | Command |
|---|---|
| Held email looks right | `approve <run-id>` (copy the id from the email) |
| Held email shows a real problem | `discard <run-id>` (unanswered runs auto-discard after 7 days) |
| What's waiting / recent runs | `status` |
| Undo a published run | `rollback <run-id>` |
| Start a run now | `start --mode lean` or `start --mode full` |
| Resume a failed run | `start --mode lean --run-id <run-id>` (finished stages are skipped) |
| News now | `start-news` (`--search` also spends 24 SerpAPI searches) |

**Deploy** from `fintank/infra`. Every deploy must repeat **all** flags in use, because an omitted flag reverts to its default and that turns the schedules off:

```bash
cdk deploy --profile fintank -c alert_email=<owner email> -c news_schedule=on -c weekly_schedule=on
```

Other flags: `-c always_hold=false` (auto-publish clean runs), `-c news_notify=warnings_only`, `-c s3_endpoint=off`.

## What changed recently (newest first)

- **2026-10-25: Oct 24 run** (`lean-20261024-1000`) was the first incremental run.
  - Downloaded **702.8 MB in total** (previously tens of GB).
  - `fetch_stock_prices`: 10,497 recent window / 134 restated / 4 new.
  - 4h40m.
  - Its only warnings were GDP/GDPC1 staleness. The data was correct; the limit was too tight, so it was raised 200 → 240 days (`f1eea95`, needs redeploy).
- **2026-10-18: incremental price download** (`c333bd0`).
  - FMP returned 429 "Bandwidth Limit Reach" for every call, including the Django site's live calls. The cause was the pipeline re-downloading full history from 1999: about 2.5 MB × about 19k symbols, so roughly 25–45 GB per run.
  - Now a symbol with saved history downloads only from 10 days before its last saved date, about 3 KB.
  - If the overlapping rows' `close`/`adjClose` moved (a split or dividend restated history), that symbol is re-downloaded in full and the file replaced. New symbols, and symbols with no recent rows, download in full.
  - Run emails now show bytes per stage, a **"Downloaded from APIs"** total, and a `fetch_stock_prices: N recent window, N restated, N new` line.
  - An FMP data boost was bought as a stopgap. It can be removed once runs are confirmed at a few GB.
- **2026-10-18: first real lean run published** (`lean-20261017-2100`, 87,621 files, 84 pass / 1 warn). Weekly and news schedules enabled; Celery beat restarted.
- **2026-10-17: safety checks** (`be53b50`):
  - build-stage failure rates;
  - minimum row/file counts for site-wide outputs (`thresholds.MIN_COUNTS`);
  - factor coverage of at least 80% of each constituent list.
  These catch truncated aggregates, e.g. a `--limit` run.
- **2026-10-17: news split** (`5e6ad07`). The FMP news feeds run daily. The 24 SerpAPI topics run only on days 1, 4, 7, …, 28 (`news.SEARCH_DAYS`), because the SerpAPI plan is 250 searches/month. Widen `SEARCH_DAYS` if the plan is upgraded.
- **2026-10-17: other fixes.**
  - Discontinued FRED series `CPGRLE01USM659N` dropped (`44b0467`).
  - `GetPrices.py` reads FMP/FRED keys from env (`03976bb`).
  - CLI reads the double-encoded approval token (`1198518`).
- **2026-10-17: key rotation.** FMP key and AWS access key rotated. The old AWS key is deactivated and should be deleted around 2026-10-24. Keys still in old notebooks/commits are dead copies. SerpAPI and FRED were not rotated.
- **Unrelated frontend commits on main:**
  - new drawn logo / favicon / OG card (`f3113ac`);
  - heatmap caps the Russell universes to 250 strongest and weakest (`211acd5`);
  - editor watcher excludes the data lake (`bcf30cb`).

## Known quirks

- **`WARN prices.non_positive — XNDX`** appears every week. `XNDX` is an ETF-holding symbol whose FMP feed returns point changes, not prices. It's harmless; a skip list in `pipeline_config.py` was offered but not built.
- **Runtime**: the first lean run took 5h04m; it should be much shorter with incremental prices. The run task times out at 12h, so watch the first **full** run on **Sat 2026-11-07**.
- **Celery beat** refreshes the Django cache from the bucket at fixed UTC times: news 10:00, profiles and econ 20:00. A publish shows on the site after the next refresh.
- **News** emails go out for every run unless `news_notify=warnings_only`.

## Next steps / open items

1. Approve `lean-20261024-1000` if not yet done; redeploy for `f1eea95`. Next run Sat 2026-10-31.
2. Delete the deactivated old AWS access key (around 2026-10-24).
3. After 3 clean weekly runs (Oct 24, Oct 31, Nov 7): redeploy with `-c always_hold=false`.
4. Decide whether to drop the FMP data boost once real usage is known.
5. Optional:
   - XNDX skip list;
   - rescale `adjClose` locally on dividend-only restatements to cut bandwidth further;
   - friendlier `infra/app.py` error when SSO has expired;
   - IAM hygiene (8 old IAM users with active keys, no MFA);
   - rotate SerpAPI/FRED keys;
   - an approve button (would need an authenticated endpoint).
6. Watch the `consumer_trends` and `communications` news topics; reword `SEARCH_TERMS` if they keep failing.

## Working rules for sessions

- **Servers:** never start Django, Celery, `npm run dev` or other background processes; name what's needed and let the owner start it.
- **Notebooks:** never execute or Run-All the notebooks in `class_files/`; their cells make real fetches.
- **AWS:** limit yourself to read-only calls (`list`, `describe`, `s3 ls/cp` to scratch). The owner runs deploys, approvals, discards, rollbacks and pushes.
- **Secrets:** never print or ask for secrets. Keys come from `backend/.env` locally and SSM on AWS.
- **Tests:**
  - `cd backend && ../../.venv/bin/python -m pytest pipelines/tests -q`
  - `cd infra && .venv/bin/python -m pytest -q`
  - `cd backend && ../../.venv/bin/python manage.py test`
