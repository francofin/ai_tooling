# Automated Data Pipeline on AWS

**Status:** Implemented on branch feat/data-pipeline (see docs/superpowers/plans/2026-10-14-automated-data-pipeline.md for rulings R1–R11)
**Replaces:** running `lean_run.ipynb`, `full_run.ipynb` and `news_updater.ipynb` by hand

---

## Context

Fintank's market data lake on `s3://thetradingfloor` is refreshed by hand from notebooks
in `backend/class_files/`:

- `lean_run.ipynb` — prices, TTM ratios, sector/index prices, builds, econ. ~38,750 FMP
  calls, ~2.2 h, ~75,700 S3 objects.
- `full_run.ipynb` — the lean run plus profiles, statements, quarterly ratios/metrics and
  revenue segments. ~121,600 FMP calls, ~6.8 h, ~139,100 S3 objects.
- `news_updater.ipynb` — 24 SerpAPI searches plus 4 FMP news feeds → 28 JSON files under
  `news_json_articles/`.

All logic lives in `class_files/stock_pipeline.py` and `pipeline_config.py`. Problems with
the current setup:

1. **Not in git.** `.gitignore:58` ignores all of `/backend/class_files`, code included.
2. **Hardcoded secrets.** `news_updater.ipynb` embeds FMP, SerpAPI and OpenAI keys and an
   AWS access key pair. The same AWS key is the one in `backend/.env` and in four other
   notebooks.
3. **No gate before S3.** Fetchers only *print* `N saved, M failed`; the "hundreds of
   failures means a degraded feed — stop" rule lives in a human's head. Uploads overwrite
   live keys in place over hours, so a crash leaves S3 half old, half new. The news
   uploader swallows every error (`except: pass`) and writes a file even when the fetch
   came back empty.
4. **Manual and local.** Runs need Franc's machine on and a person at the notebook.
5. **Constituents are skipped.** `refresh_constituents()` / `upload_constituents()` are
   commented out in both notebooks.

## Goals

- Weekly market-data run and daily news run, fully automatic, on AWS. Nothing runs on
  Franc's machine once live.
- Every run validated before anything reaches the live bucket; every check recorded.
- Publish automatically when all checks pass; hold for one-command approval when any
  check warns or fails; never publish a crashed run.
- Email when a run starts, is held, completes or fails — including when it never starts.
- Cheap: target under $20/month all in.
- Infrastructure as code (AWS CDK, Python), reproducible and removable.

## Non-goals

- Deploying the Django backend or the Next.js frontend.
- The stale `/financial-statements/` aggregates (no pipeline stage produces them; deferred
  until the backend loader is cut over, as both notebooks note).
- A web UI for approvals (the CLI command is the approval surface; an emailed approve link
  can come later).

---

## Schedule

All times UTC (no daylight-saving drift between AWS and Celery).

| Job | When | Runs |
|---|---|---|
| `weekly-data-run` | Saturdays 10:00 | `mode=auto`: day-of-month 1–7 → **full**, otherwise **lean**. Constituents refreshed first either way. |
| `daily-news` | Daily 09:30 | Fetch → check → upload passing files |

Either job can also be started by hand with an explicit mode (Step Functions console or
`python -m pipelines start --mode full`).

**Go-live guard:** `ALWAYS_HOLD=true` for the first three weekly runs — they hold for
approval even when every check passes. Flipped to `false` by changing one CDK context value.

---

## Architecture

Everything in `us-east-1` (where `thetradingfloor` lives).

```
EventBridge Scheduler (Sat 10:00 UTC)
  └─► Step Functions: weekly-data-run
        1. Lock          — refuse to start if another weekly run is RUNNING
        2. NotifyStarted — SNS email
        3. RunPipeline   — ECS Fargate task (.sync), ≤ 12 h
             pull state → refresh constituents → fetch → build → checks
             → stage changed outputs + report → push state
             (1 automatic retry, resuming at the failed stage)
        4. Choice on verdict
             PASS (and not ALWAYS_HOLD) ─────────────────────────┐
             WARN / FAIL / ALWAYS_HOLD → NotifyHeld → WaitForApproval
                                          (S3 putObject .waitForTaskToken, 7-day timeout)
                                          approve ─────────────────┤
                                          discard / timeout → NotifyDiscarded (end)
        5. Publish       — ECS Fargate task (.sync): server-side copy staged → live
        6. NotifyComplete
      Catch (any state) → NotifyFailed

EventBridge Scheduler (daily 09:30 UTC)
  └─► Step Functions: daily-news
        NotifyStarted → RunNews (Fargate .sync, ≤ 30 min) → NotifyComplete
      Catch → NotifyFailed

EventBridge rule: Step Functions execution FAILED / TIMED_OUT / ABORTED → SNS
Scheduler dead-letter queue (SQS) + CloudWatch alarm on queue depth > 0 → SNS
```

### Why these services

| Need | Service | Why |
|---|---|---|
| Run 2–8 h of Python | **ECS Fargate** | No server to maintain, no time limit (Lambda caps at 15 min), billed per second only while running. Up to 200 GiB ephemeral disk. |
| Order stages, branch on checks, wait for approval | **Step Functions (Standard)** | Native `.sync` ECS integration (waits for the task), `.waitForTaskToken` for human approval up to a year, full execution history = audit log. |
| Cron | **EventBridge Scheduler** | Free tier covers it; retries and a dead-letter queue built in. |
| Email | **SNS** email subscription | First 1,000 emails/month free. |
| Secrets | **SSM Parameter Store** SecureString | Free (standard tier); injected into the container by ECS. |
| AWS access from the container | **ECS task role** | No access keys in code or `.env` on AWS. |
| Logs | **CloudWatch Logs** | 30-day retention. |
| Infra | **AWS CDK (Python)** in `fintank/infra/` | One `cdk deploy`; builds and pushes the container image itself. |

### Networking

Fargate tasks run in the account's **default VPC, public subnets, with a public IP**, and a
security group with **no inbound rules**. This avoids a NAT gateway (~$32/month). A free
**S3 gateway VPC endpoint** carries all S3 traffic.

### Buckets

| Bucket | Purpose | Settings |
|---|---|---|
| `thetradingfloor` (existing) | Live data the site reads | **Versioning turned on**; lifecycle rule expires noncurrent versions after 30 days. CDK imports it, does not own it. |
| `fintank-pipeline-<account-id>` (new) | Working state, staging, run reports, approval tokens | Private, encrypted, block public access, versioning on, lifecycle: `runs/` expires after 90 days, noncurrent versions after 14 days. |

State bucket layout:

```
state/                      # the master copy of raw pipeline inputs
  stock_data_json/<dataset>.tar.zst      # one archive per data type folder
  index_data.tar.zst
  econ_data.tar.zst
  path_helpers.tar.zst
runs/<run-id>/
  progress.json             # completed stages — drives resume
  report.json               # every check, every count, timings
  stage/<live-key>          # only the files that differ from live
  publish-manifest.json     # written by Publish: key, old VersionId, new VersionId
  approval-token.json       # written by WaitForApproval
```

**Run ID:** `<mode>-<YYYYMMDD>-<HHMM>`, e.g. `lean-20261017-1000`.

---

## Code

The pipeline moves out of the git-ignored `class_files/` into a tracked package. Data stays
where it is locally (`class_files/`) and at `/data` in the container, chosen by
`PIPELINE_DATA_ROOT`.

```
backend/pipelines/
  __init__.py
  __main__.py          # CLI
  stock_pipeline.py    # moved from class_files/, changes listed below
  pipeline_config.py   # moved from class_files/, unchanged
  thresholds.py        # every check threshold in one place
  runner.py            # lean/full stage lists, resume, stage results
  checks.py            # one small function per check
  report.py            # run report model + JSON writer
  state.py             # pull/push state archives
  publish.py           # diff vs live, stage, publish, rollback
  notify.py            # SNS publish (stdout when SNS_TOPIC_ARN unset)
  news.py              # rewritten news fetcher + checks
  Dockerfile
  tests/
backend/.dockerignore   # MUST exclude class_files/ (48 GB) and .venv/
infra/                  # CDK app (fintank/infra/)
  app.py
  pipeline_stack.py
  cdk.json
  requirements.txt
```

### Changes to `stock_pipeline.py`

- `root` defaults to `PIPELINE_DATA_ROOT`, falling back to `class_files/` so notebooks keep
  working.
- Fetchers return a `StageResult(name, attempted, saved, failed, no_data, errors,
  failed_symbols)` in addition to writing manifests. Printing stays.
- AWS credentials: if `AWS_ACCESS_KEY_ID` is unset, the boto3 default chain is used (task
  role on AWS). Same for the bucket name default.
- Build stages are unchanged, but **every run rebuilds every parquet from the merged
  JSON** (lean and full alike). Builds are local and need no API calls; this means state
  only has to carry raw JSON, and the diff-before-publish step (below) keeps a lean run from
  re-uploading unchanged fundamentals.
- `.env` loading stays for local use; on AWS every value comes from the environment.

The notebooks are updated to `from pipelines.stock_pipeline import StockDataPipeline` and
have their `upload_*` cells removed: once AWS holds the master state, a local upload could
overwrite newer data with older. Local exploration starts with `python -m pipelines
pull-state`.

### Stage lists (`runner.py`)

| # | Stage | Lean | Full |
|---|---|---|---|
| 1 | `pull_state` | ✓ | ✓ |
| 2 | `refresh_constituents` (fallback: keep existing lists) | ✓ | ✓ |
| 3 | `fetch_stock_prices(from_date="1999-01-01")` | ✓ | ✓ |
| 4 | `fetch_etf_prices(from_date="1999-01-01")` | ✓ | ✓ |
| 5 | `fetch_profiles`, `fetch_etf_profiles` | | ✓ |
| 6 | `fetch_financial_statements` | | ✓ |
| 7 | `fetch_ratios` | | ✓ |
| 8 | `fetch_ttm_ratios` | ✓ | ✓ |
| 9 | `fetch_revenue_segments` | | ✓ |
| 10 | `fetch_sector_history(from_date="2010-01-01")` | ✓ | ✓ |
| 11 | `fetch_index_prices()` | ✓ | ✓ |
| 12 | `fetch_fred_series` | ✓ | ✓ |
| 13 | `build_price_parquets`, `build_fundamentals_parquets`, `build_profile_aggregate`, `build_factor_metrics`, `build_contr_to_var`, `build_econ_parquets`, `build_relative_performance` | ✓ | ✓ |
| 14 | `run_checks` | ✓ | ✓ |
| 15 | `stage_outputs` (diff vs live, upload changed files to `runs/<id>/stage/`) | ✓ | ✓ |
| 16 | `push_state` | ✓ | ✓ |

`push_state` also runs **after each fetch stage** for the datasets that stage touched, and
`progress.json` records the stage as complete. A crashed task retried by Step Functions
(one automatic retry) or by `python -m pipelines resume <run-id>` skips completed stages,
so a crash at hour 5 does not re-pay 5 hours of FMP calls.

A failed `refresh_constituents` is never fatal: each list that fails or shrinks keeps its
existing file (today's behaviour) and is recorded as a warning. Only lists that refreshed
*and* changed are staged for upload.

### Diff before publish (`publish.py`)

- For each output file, compute SHA-256 locally and compare with
  `state/live-manifest.json` (`{key: sha256}`), which every publish and rollback keeps
  current; published objects also carry `x-amz-meta-sha256`. Missing metadata
  (objects uploaded before this work) → treated as changed, so the first run publishes
  everything once.
- Only changed files go to `runs/<id>/stage/`.
- **Publish** is a separate small Fargate task: server-side `CopyObject` from stage to the
  live key (with the sha256 metadata), recording each key's previous and new `VersionId`
  in `publish-manifest.json`. No local data needed, so it runs fine days later after an
  approval.
- Publish order puts the "LIVE" datasets last (factor metrics, profile aggregates, econ),
  so the site never sees new aggregates before their per-symbol files.
- **Rollback:** `python -m pipelines rollback <run-id>` restores each key in the publish
  manifest to its previous version (or deletes it if it was new).
- Implementation must confirm parquet output is byte-deterministic for identical input
  (same pyarrow version). If it is not, the diff falls back to comparing the decoded
  table, or every parquet uploads each run (~$0.70/run — acceptable, not a blocker).

### Checks (`checks.py`, thresholds in `thresholds.py`)

Each check returns `CheckResult(name, status: pass|warn|fail, value, threshold, detail)`.
The run verdict is the worst status. Exceptions are not checks: a crash fails the
execution and nothing is published.

| Area | Check | Warn | Fail |
|---|---|---|---|
| Constituents | Each list vs its previous file | grew > 50% | shrank > 50% (old list kept) or fetch failed |
| Fetch | Failed symbols per fetch stage (revenue segments: `errors` only; `no data` is normal) | > 2% | > 10% |
| Freshness | Modal last price date per sub-universe vs last NYSE trading day | 1 trading day behind | > 1 trading day behind |
| Builds | Every parquet opens and has its expected columns | — | any unreadable / missing columns |
| Builds | Row count per dataset vs last *published* run's report | < 98% | < 90% |
| Factor metrics | Stale-symbol count `S` per sub-universe | doubled vs last run | > 10% of universe |
| Prices | `adjClose <= 0`; one-day move > 80% not explained by a split | `adjClose ≤ 0`; or > 1% of symbols with a > 80% one-day move (moves are always listed) | — |
| Econ | Last observation date per FRED series | older than its expected lag | — |
| Staging | Number of changed files | — | 0 changed files on a run whose prices fetch succeeded (something is wrong with the diff) |

"Last published run" comes from the newest `report.json` whose run was published, so a
held-then-discarded run never becomes the baseline.

### News (`news.py`)

A rewrite of the notebook's `GetNewsArticles`, same 24 search terms and 4 FMP feeds, same
S3 keys (`news_json_articles/<name>_articles.json`) so `news/getNews.py` is untouched.

- Keys from the environment (`FMP_API`, `SERPAPI_KEY`). The unused OpenAI key is dropped.
- Per-request timeouts and one retry; errors are recorded, never swallowed.
- Per file checks: ≥ 50 articles for FMP feeds, ≥ 3 for search topics; required fields present (title, url, date — field names
  differ between FMP and SerpAPI and are mapped per source); newest article ≤ 3 days old
  (FMP) / ≤ 7 days (search); duplicates by URL removed.
- A file that fails is **not uploaded** — yesterday's file stays live. The run is marked
  `warn` if any file failed, `fail` if more than half did. News publishes passing files
  automatically; there is no approval hold.
- Implementation must confirm SerpAPI's `bing_news` engine still returns results (Microsoft
  retired the Bing Search APIs in 2025) and pick a replacement engine if not. 24
  searches/day ≈ 730/month, which needs a paid SerpAPI plan.

### CLI (`python -m pipelines ...`)

| Command | Does |
|---|---|
| `run --mode lean\|full\|auto [--run-id ID] [--dry-run] [--limit N]` | The weekly task's entry point. `--dry-run`: everything except staging/state push. `--limit N`: N symbols per list (smoke test). |
| `start --mode M --run-id <id>` | Resume a run in a fresh execution |
| `publish <run-id>` | The publish task's entry point |
| `news [--dry-run]` | The news task's entry point |
| `start --mode lean\|full [--limit N]` | Start the weekly state machine by hand (uses `AWS_PROFILE`, like every command that talks to AWS) |
| `start-news` | Start the daily-news state machine by hand |
| `approve <run-id>` / `discard <run-id>` | Read `approval-token.json`, call `SendTaskSuccess` / `SendTaskFailure` |
| `rollback <run-id>` | Restore the live keys a publish changed |
| `seed-state` | One-time: archive local `class_files/` JSON and upload to `state/` |
| `pull-state` | Download the master state into local `class_files/` |
| `status` | Last 10 executions of each job with verdict and report link |

### Notifications (`notify.py`)

One SNS topic, `fintank-pipeline-alerts`, with Franc's email subscribed.

| Email | Sent by | Contains |
|---|---|---|
| Started | state machine | job, mode, run ID |
| Held | state machine | the non-passing checks, `python -m pipelines approve <run-id>` / `discard <run-id>`, auto-discard date |
| Complete | state machine | duration, per-stage counts, check summary, files published, S3 console link to `report.json` |
| Failed | state machine Catch + EventBridge rule | failed stage, error, CloudWatch Logs link |
| Never started | Scheduler DLQ alarm | which schedule failed to fire |

News sends Started and Complete daily. `NEWS_NOTIFY=warnings_only` (CDK context) reduces it
to Held/Failed-type emails only.

Held, Complete and News emails are sent by the Python commands; Started, Failed, Discarded
and Skipped by the state machines. A crashing container command also emails directly.

### Django cache timing

Django serves S3 data from Redis and Celery refreshes those copies every 86,400 s counted
from whenever beat started, so new data can sit unseen for up to a day. Until the backend is
deployed somewhere the pipeline can reach, fix the timing in `settings.py`: switch the
relevant `CELERY_BEAT_SCHEDULE` entries to `crontab` at fixed UTC times after the AWS jobs.

| Beat entry | New schedule |
|---|---|
| `update_news_articles_daily` | daily 10:00 UTC (30 min after news) |
| `update_universe_profiles_daily` | daily 20:00 UTC (after the longest Saturday run) |
| `update_economic_data_daily` | daily 20:00 UTC |

Implementation checks the other analyzer tasks for readers of pipeline outputs and adds any
that are scheduled. When the backend is deployed, the pipeline's last state calls a Django
refresh endpoint instead (out of scope here).

### Container

`backend/pipelines/Dockerfile`, build context `backend/pipelines/` only: `python:3.12-slim`,
`pip install -r requirements.txt`, non-root user, entrypoint `python -m pipelines`.
`factor_windows.py` moved into the package so the context stays small.

### ECS task sizes

| Task | CPU | Memory | Ephemeral disk | Timeout (Step Functions) |
|---|---|---|---|---|
| `pipeline-run` | 4 vCPU | 16 GB | 150 GiB | 12 h |
| `pipeline-publish` | 0.5 vCPU | 1 GB | 20 GiB (default) | 2 h |
| `news` | 0.5 vCPU | 1 GB | 20 GiB (default) | 30 min |

Memory is sized above Franc's 7 GB WSL box because builds currently run there with swap;
implementation measures peak RSS on the first runs and the size is tuned down after.

### IAM (all created by CDK, least privilege)

| Role | Can |
|---|---|
| Task execution role | pull the image, read `/fintank/pipeline/*` parameters, write logs |
| `pipeline-run` task role | read/write state bucket; **read only** `thetradingfloor` (for the diff) |
| `pipeline-publish` task role | read state bucket `runs/*`; write `thetradingfloor` |
| `news` task role | write `thetradingfloor/news_json_articles/*` |
| State machine role | `ecs:RunTask` on the three task definitions, `iam:PassRole` for them, `sns:Publish`, `s3:PutObject` on `runs/*/approval-token.json`, EventBridge managed rule for `.sync` |
| Scheduler role | `states:StartExecution` on the two state machines |

### Cost estimate (monthly, us-east-1)

| Item | Estimate |
|---|---|
| Fargate `pipeline-run`: 3 lean (~3 h) + 1 full (~8 h) | ~$12 |
| Fargate publish + news | < $1 |
| State bucket (~10 GB compressed + run staging) | ~$0.50 |
| `thetradingfloor` noncurrent versions (30 days) | ~$1–2 |
| S3 requests (state archives, diff HEADs, changed-file copies) | ~$1–2 |
| Step Functions, Scheduler, SNS, SSM, CloudWatch Logs | < $1 |
| **Total** | **~$15–18** |

No NAT gateway, no always-on instances, no Secrets Manager.

---

## Setup instructions

Franc does every step in this section; nothing here is run by Claude.

### 0. Accounts and tools (one time)

1. **Budget alert.** AWS console → *Billing and Cost Management* → *Budgets* → *Create
   budget* → *Monthly cost budget* → $25 → alert at 80% and 100% to your email.
2. **Root account MFA.** Console (as root) → account menu → *Security credentials* →
   *Assign MFA device*. Stop using root after this.
3. **An admin login that is not root.** *IAM Identity Center* → *Enable* (region
   us-east-1) → *Users* → *Add user* (your email) → *Permission sets* → *Create* →
   *Predefined: AdministratorAccess* → *AWS accounts* → select the account → *Assign* the
   user with that permission set. Accept the invite email, set a password and MFA. Note the
   **AWS access portal URL**.
4. **AWS CLI v2 in WSL.**
   ```bash
   curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
   unzip awscliv2.zip && sudo ./aws/install && aws --version
   aws configure sso   # session name: fintank, start URL: the portal URL,
                       # region: us-east-1, profile name: fintank
   aws sso login --profile fintank
   aws sts get-caller-identity --profile fintank   # prints your account id
   ```
5. **Docker.** Docker Desktop for Windows → *Settings* → *Resources* → *WSL integration* →
   enable for your distro. Check with `docker run hello-world` in WSL.
6. **Node 20+ and the CDK CLI.**
   ```bash
   node --version            # install Node 20+ via nvm if missing
   npm install -g aws-cdk
   cdk --version
   cdk bootstrap aws://<account-id>/us-east-1 --profile fintank
   ```

### 1. Rotate the exposed keys

The keys in `news_updater.ipynb` must be treated as compromised. Order matters because the
backend uses the same FMP and AWS keys.

1. **FMP:** generate a new key in the FMP dashboard → put it in `backend/.env` (`FMP_API`)
   → it goes into SSM in step 2 → revoke the old key.
2. **SerpAPI:** regenerate the key at serpapi.com → SSM in step 2. Confirm the plan covers
   ~730 searches/month.
3. **OpenAI:** revoke the key in the OpenAI dashboard (the news job does not use it).
4. **AWS access key `AKIAR76F…`:** it is also `backend/.env`'s key. IAM → the user that
   owns it → *Create access key* → put the new pair in `backend/.env` → restart Django and
   Celery → confirm the site still loads S3 data → *Deactivate* the old key → after a week
   with nothing broken, *Delete* it. The pipeline on AWS uses its task role and needs no key.
5. Remove the hardcoded keys from the five notebooks that contain them (`news_updater`,
   `portfolio_analyzer`, `get_stock_data`, `fintank_data_getter`, `homepage_data`) — they
   are git-ignored, but they are still plaintext on disk.

### 2. Store the secrets

```bash
for name in FMP_API FRED_API SERPAPI_KEY; do
  read -rsp "$name: " value; echo
  aws ssm put-parameter --profile fintank --region us-east-1 \
    --name "/fintank/pipeline/$name" --type SecureString --value "$value" --overwrite
done
aws ssm get-parameters-by-path --path /fintank/pipeline --profile fintank \
  --query "Parameters[].Name"
```

(`read -s` keeps the values out of shell history.)

### 3. Turn on versioning for the live bucket

CDK imports `thetradingfloor` rather than owning it, so this is done once by hand:

```bash
aws s3api put-bucket-versioning --profile fintank --bucket thetradingfloor \
  --versioning-configuration Status=Enabled
```

The 30-day noncurrent-version lifecycle rule is added in the console: S3 →
`thetradingfloor` → *Management* → *Create lifecycle rule* → *Apply to all objects* →
*Permanently delete noncurrent versions of objects* → 30 days.

### 4. Test locally (before anything runs on AWS)

From `fintank/backend`:

```bash
cd fintank/backend
uv pip install --python ../../.venv/bin/python -r pipelines/requirements-dev.txt
../../.venv/bin/python -m pytest pipelines/tests -q
python -m pipelines run --mode lean --dry-run --limit 5
python -m pipelines news --dry-run
```

The news dry run is also where SerpAPI's `bing_news` engine gets confirmed — if every
`news.<topic>` check says "fetch failed", the engine needs replacing before go-live.

### 5. Deploy

```bash
cd fintank/infra
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cdk diff   --profile fintank -c alert_email=<you@example.com>
cdk deploy --profile fintank -c alert_email=<you@example.com>
```

If the deploy fails creating `S3Endpoint` because the default VPC already has an S3
gateway endpoint, re-run with `-c s3_endpoint=off`.

`cdk deploy` builds the container image, pushes it to ECR and creates everything in the
Architecture section. Both schedules are created **disabled**.

Then: open the *AWS Notification - Subscription Confirmation* email and click *Confirm
subscription*. No alerts arrive until you do.

### 6. Seed the state bucket (one time)

```bash
cd fintank/backend
AWS_PROFILE=fintank python -m pipelines seed-state
```

Archives the local JSON (~27 GB raw) and uploads it to `state/`. Run it right after your
last local run so the master copy is current.

### 7. Go live in stages

1. **News.** Start `daily-news` by hand (`python -m pipelines start-news`). Check the
   emails, the report, and the news pages. Enable its schedule:
   `cdk deploy --profile fintank -c alert_email=… -c news_schedule=on`. Watch for a week.
2. **Weekly, smoke.** `python -m pipelines start --mode lean --limit 5`. It will hold
   (`ALWAYS_HOLD`); read the report, then `discard`.
3. **Weekly, real.** `python -m pipelines start --mode lean`. Read the report, `approve`,
   check the site. Enable the `weekly-data-run` schedule:
   `cdk deploy --profile fintank -c alert_email=… -c news_schedule=on -c weekly_schedule=on`.
4. After three good held runs, set `ALWAYS_HOLD` off:
   `cdk deploy --profile fintank -c alert_email=… -c news_schedule=on -c weekly_schedule=on -c always_hold=false`.
   Every later deploy must repeat the flags in use (or set them in `infra/cdk.json`).
5. Update `CELERY_BEAT_SCHEDULE` (Django cache timing section) and restart beat.

### Day-to-day

| Situation | Do |
|---|---|
| "Held" email | Read the linked report → `python -m pipelines approve <run-id>` or `discard <run-id>` |
| "Failed" email | Open the logs link. Fix, then `python -m pipelines resume <run-id>`, or let next week's run go |
| Bad data went live | `python -m pipelines rollback <run-id>` |
| Want a full run now | `python -m pipelines start --mode full` |
| Explore data locally | `python -m pipelines pull-state` first |
| Change a threshold | edit `thresholds.py` → `cdk deploy` (rebuilds the image) |
| Turn it all off | `cdk deploy --profile fintank -c alert_email=… -c news_schedule=off -c weekly_schedule=off`, or `cdk destroy` removes everything except the state bucket (retained) and `thetradingfloor` |

---

## Testing

- **Unit tests** (`backend/pipelines/tests/`, no network, no AWS):
  - every check function at pass / warn / fail boundaries;
  - verdict = worst status; exceptions are not swallowed into checks;
  - mode `auto` → full on days 1–7, lean otherwise;
  - resume skips stages recorded in `progress.json`;
  - constituent fallback: failed or shrunk list keeps the old file and is not staged;
  - diff: sha256 match → not staged, mismatch / missing metadata → staged;
  - rollback restores previous VersionIds and deletes newly created keys;
  - news: file with < 5 articles, missing fields, stale dates or a fetch error is not
    uploaded; duplicates removed; FMP vs SerpAPI field mapping.
  S3 interactions use `moto`.
- **CDK:** `cdk synth` snapshot test plus assertions — no NAT gateway, tasks have no
  inbound security-group rules, task roles cannot write where they shouldn't, schedules
  created disabled.
- **Local smoke run** (setup step 4) and the staged go-live (step 7) are the integration
  tests.

## Open items for implementation

- Confirm parquet byte-determinism (affects diff efficiency only).
- Confirm SerpAPI `bing_news` still works; choose a replacement engine if not.
- Confirm the full import list `stock_pipeline.py` needs from `backend/utils/`.
- Measure peak memory and runtime of the first AWS runs; retune task size.
- Find any other Celery beat tasks that read pipeline outputs.
