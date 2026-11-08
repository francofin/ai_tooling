# Recent changes and how we operate now

Last updated 2026-11-08. Read this first in a new session, then the linked docs for detail.

## TL;DR

- Market data is no longer refreshed from the notebooks. It runs on **AWS** (ECS Fargate + Step Functions), on a schedule, and every run is **checked before anything reaches the live bucket** `thetradingfloor`.
- **Weekly data run**: Saturdays 10:00 UTC (06:00 Toronto in summer, 05:00 in winter). Lean run normally; **full** run when the Saturday falls on days 1–7 of the month.
- **Daily news run**: 09:30 UTC. Tests each file, uploads only the ones that pass, no approval needed.
- Weekly runs currently **hold for manual approval** even when every check passes (`always_hold`). After 3 clean weekly runs, redeploy with `-c always_hold=false` so clean runs publish themselves.
- Price downloads are **incremental** since 2026-10-18 (commit `c333bd0`), after FMP's monthly bandwidth cap was hit.
- **Index return attribution** is deployed (2026-11-08, `ed5daf4`). The first run that builds it is the lean run on **Sat 2026-11-14**; see "Where we are" below.

## Where we are (2026-11-08)

- **Index attribution: built and deployed, not yet run on AWS.**
  - Spec `docs/superpowers/specs/2026-11-07-index-attribution-design.md`, plan `docs/superpowers/plans/2026-11-07-index-attribution.md` (all tasks done; Brinson attribution is deferred to a later version).
  - Merged to `main` as a fast-forward of `feat/index-attribution` (`b0c8e42..ed5daf4`) and pushed 2026-11-08. CDK deployed the same day: task definitions `fintank-run`, `fintank-publish`, `fintank-news` are at **revision 7**.
  - Holdings snapshots (phase 0) went live 2026-11-07 (`1811f8f`). The first 8 are in `s3://thetradingfloor/index_data/constituents_history/{sub}/2026-11-06.json`. One is added per weekly run; they can't be back-filled.
  - Decisions: price return; local currency for msci_eafe / msci_sm (CAD for the TSX lists, USD otherwise); windows 1W, 2W, 1M, 3M, YTD, 1Y; v1 = sectors, top/bottom 10 names, breadth, concentration, cap-weighted minus equal-weighted.
  - Pipeline: `pipelines/attribution.py` (maths), `StockDataPipeline.build_index_attribution` (stage), `checks.check_attribution` (WARN-only), output `index_data/attribution/{sub}_attribution.parquet`.
  - Django: `analyzer/analyzer_utils/index_tools.py` reads the parquet (cache key `...:v2`) and falls back to the old live calculation (`source: "live"`, YTD and 1M only) until the file exists. Frontend: `src/componentsLegacy/IndexDetail/SectorContribution.js` ("Return Attribution").
  - Local smoke run (8 lists, about 2.5 min): large caps within 0.7pp of their ETF; small-cap YTD/1Y trail their ETF by 5 to 17pp because members that graduate to a bigger index drop out of the snapshot. That residual is reported, not checked, and the page labels those windows "approximate".
- **Next: Sat 2026-11-14 lean run.** When the held email arrives, check:
  1. a `build_index_attribution` line with 8 saved, and the attribution check lines (WARN at worst; they can't FAIL in v1);
  2. `aws s3 ls s3://fintank-pipeline-137315715959/runs/<run-id>/stage/index_data/attribution/ --profile fintank` shows 8 parquets;
  3. copy `sp500_attribution.parquet` to scratch and check the `__index__` rows: return close to SPY (`residual_pp` within the 1W/1M limits), coverage around 99%;
  4. then `approve`. Use the real residuals to tune `ATTRIBUTION_RESIDUAL_WARN_BP` in `pipelines/thresholds.py`.
  After approval, the owner checks `/indexes/sp500` and `/indexes/msci_eafe` (owner starts the servers; the site picks up the file on the next cache miss).
- **Nov 7 full run** (`full-20261107-1000`, 9h58m, well inside the 12h limit) was held FAIL only on `fetch_ratios.failure_rate` (FMP plan refuses foreign ratios; fixed in `ed5daf4`, see below). Approved and published 2026-11-07.
- **Branches.** `main` = `origin/main` = `ed5daf4`. `frontend-fixes-and-dep-cleanup` (dual-axis peer chart, valuations table, dropped 54 deps) is 2 commits ahead of the old main, not merged; it merges cleanly with the new main. The worktree `../ai_tooling-index-attribution` (branch `feat/index-attribution`) can be removed once Nov 14 is approved: `git worktree remove ../ai_tooling-index-attribution --force && git branch -d feat/index-attribution`.

## Web hosting (not live yet)

**The site is not live until the owner finishes the server runbook `deploy/README.md`.** The old Heroku backend is deleted and the DigitalOcean app is archived.

- Planned hosting: one Lightsail 4 GB instance in `us-east-1` running Docker Compose (Caddy, web, api, worker, redis, Postgres in a container) at `/opt/fintank`. DNS in Route 53.
- Deploys: `.github/workflows/fintank-deploy.yml` on pushes to `main` (test, build images to GHCR, then SSH deploy via `deploy/deploy.sh`, only when the repo variable `DEPLOY_ENABLED` is `true`). A failed health check redeploys the previous image tag.
- Nightly Postgres backup to `s3://fintank-backups-137315715959/postgres/` via `deploy/backup_db.sh` (cron on the server, SNS email on failure).
- Local dev after this change: run `npm install` in `fintank/` (Next moved to 15.5.29) and set `DEBUG=True` in `backend/.env` (`DEBUG` now defaults to False).
- Design and decisions: `docs/AWS_HOSTING_PLAN.md`. Move to a managed database before paying users: last section of the runbook.

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

- **2026-11-08: index attribution deployed** (`ed5daf4`, merged and pushed; CDK task definitions revision 7). First AWS build on Sat 2026-11-14.
- **2026-11-07: "not on plan" is no longer a fetch failure** (`ed5daf4`, deployed 2026-11-08).
  - The first AWS full run (`full-20261107-1000`) had `fetch_ratios` fail 4,065 of 10,620 symbols (38%, so the run was held as FAIL): FMP's `/stable/ratios` answered 2,308 x 402 Payment Required and 1,163 x 429 Too Many Requests, every one a foreign listing in msci_eafe / msci_sm.
  - The per-symbol fetchers now count a 402, or a 429 on a foreign-suffixed symbol (`.T`, `.L`, `.AX`, `.HK`, ...), as `no_data` and print one "N not on plan" count per list (`detail.not_on_plan`). A 429 on a US/Canadian symbol is still a failure. Those symbols keep their previous files.
- **2026-11-07: index attribution stage** (deployed 2026-11-08).
  - New build stage `build_index_attribution` and dataset `attribution` (`index_data/attribution/{sub}_attribution.parquet`), six windows, price return, buy-and-hold weights from the holdings snapshot.
  - All its checks are WARN-only in v1; see `backend/pipelines/README.md` ("Index attribution").
  - Django reads the parquet and the index page shows it ("Return Attribution"); until the first file is published they fall back to the old live sector calculation.
- **2026-11-07: holdings history** (`1811f8f`, deployed 2026-11-07; first snapshots published with `full-20261107-1000`).
  - `refresh_constituents` saves each index list as `index_data/constituents_history/{sub}/{YYYY-MM-DD}.json`, dated by the holdings' `updated` field, and publishes it (new dataset `constituents_history`; no minimum count, `counts.*` catches a shrink).
  - Phase 0 of the index attribution plan (`docs/superpowers/plans/2026-11-07-index-attribution.md`); history can't be back-filled, so it ships first.
  - Restore procedure in `backend/pipelines/README.md` ("Holdings history").
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
- **2026-11-04: moving the web app to AWS.** Old Heroku app deleted and `thefintank-app` archived, so the site is offline until go-live. Decisions are at the top of `docs/AWS_HOSTING_PLAN.md`; build steps are in `docs/superpowers/plans/2026-11-04-aws-web-hosting.md`. `next build` now passes (`6ba9e8b`).
- **Unrelated frontend commits on main:**
  - new drawn logo / favicon / OG card (`f3113ac`);
  - heatmap caps the Russell universes to 250 strongest and weakest (`211acd5`);
  - editor watcher excludes the data lake (`bcf30cb`).

## Known quirks

- **`WARN prices.non_positive — XNDX`** appears every week. `XNDX` is an ETF-holding symbol whose FMP feed returns point changes, not prices. It's harmless; a skip list in `pipeline_config.py` was offered but not built.
- **Runtime**: the first full run (2026-11-07) took 9h58m against the 12h task timeout; the slowest stages were financial statements (2h09m), TTM ratios (1h24m), prices (1h04m) and ratios (1h02m). Watch the next full run (Sat 2026-12-05) if the universe grows.
- **FMP plan limits**: many foreign listings (msci_eafe, msci_sm) get 402/429 from `/stable/ratios`. Since `ed5daf4` they count as no data ("N not on plan" in the stage detail) and keep their previous files.
- **Celery beat** refreshes the Django cache from the bucket at fixed UTC times: news 10:00, profiles and econ 20:00. A publish shows on the site after the next refresh.
- **News** emails go out for every run unless `news_notify=warnings_only`.

## Next steps / open items

- **Bring this up with the owner at go-live: are the login limits still right?** `/admin/login/` and `/login/` allow **20 attempts an hour per address and 100 per account** (`form_login` and `form_login_account` in `AUTH_THROTTLE_RATES`, `backend/fintank_backend/settings.py`). The owner asked to be reminded of how strict this is. The account limit must stay well above the address limit, or one address can lock them out; the higher it is, the more guesses many addresses get. Ask during the go-live login check, and again before paying users. Other routes that test the same password have higher limits: see "A login gets `429`" in `deploy/README.md`.
1. Sat 2026-11-14 lean run: first index attribution build. Checklist in "Where we are" above.
2. Delete the deactivated old AWS access key (around 2026-10-24).
3. `always_hold` stays on for now: Nov 7 was held FAIL (ratios), and attribution needs a few runs of review. Redeploy with `-c always_hold=false` after three clean runs with attribution (earliest after Nov 28).
4. Decide whether to drop the FMP data boost once real usage is known.
5. Optional:
   - XNDX skip list;
   - rescale `adjClose` locally on dividend-only restatements to cut bandwidth further;
   - friendlier `infra/app.py` error when SSO has expired;
   - IAM hygiene (8 old IAM users with active keys, no MFA);
   - rotate SerpAPI/FRED keys;
   - an approve button (would need an authenticated endpoint).
6. Watch the `consumer_trends` and `communications` news topics; reword `SEARCH_TERMS` if they keep failing.
7. After three clean runs with attribution, set `ATTRIBUTION_FAILURE_STATUS = "fail"` in `pipelines/thresholds.py` and redeploy.
8. Attribution follow-ups (deferred minors from the final review; none affect the numbers on the page today):
   - `names_to_50pct` uses an absolute 0.5pp guard; add one relative to gross contribution;
   - no WARN when a window is omitted (fewer than 6 windows in a list);
   - `holdings_date` accepts impossible dates like 2026-02-30 (the list is skipped, the snapshot file is still written);
   - the snapshot is dated from the first row only;
   - duplicate asset rows in a holdings payload overwrite each other (pre-existing);
   - `count` is Int64 and can hold `pd.NA`; any new reader that dumps the raw frame must coerce it.
   - Later version: Brinson allocation/selection against a benchmark (out of v1 scope).

## Working rules for sessions

- **Servers:** never start Django, Celery, `npm run dev` or other background processes; name what's needed and let the owner start it.
- **Notebooks:** never execute or Run-All the notebooks in `class_files/`; their cells make real fetches.
- **AWS:** limit yourself to read-only calls (`list`, `describe`, `s3 ls/cp` to scratch). The owner runs deploys, approvals, discards, rollbacks and pushes.
- **Secrets:** never print or ask for secrets. Keys come from `backend/.env` locally and SSM on AWS.
- **Tests:**
  - `cd backend && ../../.venv/bin/python -m pytest pipelines/tests -q`
  - `cd infra && .venv/bin/python -m pytest -q`
  - `cd backend && ../../.venv/bin/python manage.py test`
