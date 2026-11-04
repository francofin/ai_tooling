# AWS Web Hosting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the Fintank frontend, API, background jobs, Redis and Postgres on one Lightsail server, deployed from GitHub Actions, on `thefintank.com`.

**Architecture:** Docker Compose on a Lightsail 4 GB instance runs Caddy (HTTPS and routing), Next.js, Django (gunicorn), Celery (worker + beat), Redis and Postgres. GitHub Actions tests the code, pushes two images to GHCR and deploys over SSH. A nightly `pg_dump` goes to a private S3 bucket.

**Tech Stack:** Docker Compose, Caddy 2, Next.js 15 standalone, Django 5.2 + gunicorn, Celery, Redis 7, Postgres 16, GitHub Actions, GHCR, Lightsail, Route 53.

**Spec:** `docs/AWS_HOSTING_PLAN.md` (the "Decisions" block at its top overrides the rest).

## Global Constraints

- Option B first: Postgres in Compose. All database settings stay in env vars, so moving to Option A only changes `.env`.
- Database starts empty. Seed only `Stock` and `AvatarPreset`.
- Hostnames: `www.thefintank.com` serves the site, `thefintank.com` redirects to it, `api.thefintank.com` serves Django.
- Build contexts are `fintank/` (web) and `fintank/backend/` (api), never the monorepo root. Images must not contain `.env*` or `backend/class_files` (49 GB).
- `backend/utils/factor_windows.py` imports `pipelines.factor_windows`, so the api image keeps `pipelines/`.
- Local development must keep working unchanged, given `DEBUG=True` in `backend/.env`.
- No secrets in git, images or logs. The frontend has no server secrets; all its env vars are `NEXT_PUBLIC_*` and baked in at build.
- Never run `next build` in the main `fintank/` folder (it can break a running dev server). `docker build` is fine because it uses its own filesystem.
- Do not start long-lived processes on the owner's machine. Containers run only inside `deploy/smoke.sh`, which uses its own project name and always tears down. Get the owner's OK before its first run.
- The owner performs all AWS, DNS, GitHub secrets, Firebase and Stripe actions, and every push.
- Do not deploy or change anything in `infra/` or the data pipeline.

## Review Focus

1. **Empty Redis after a restart or deploy:** the first requests fall back to heavy S3/pandas work. Pages must stay up within the `api` memory limit (Task 5 smoke, Task 8 go-live check).
2. **Backup failing silently:** a dump that fails or is empty must send an alert and must not overwrite a good object (Task 6 test).
3. **Failed deploy:** a new image that fails its health check must roll back to the previous tag, and the workflow must fail (Task 5 test).
4. **Uploaded avatars disappearing:** with `DEBUG=False`, files must go to S3, not the container disk. Django 5.2 ignores the current `DEFAULT_FILE_STORAGE` (Task 1 test).
5. **Redis memory pressure evicting Celery messages:** eviction must only touch keys with a TTL, so `volatile-lru`, never `allkeys-lru` (Task 5 test).

---

### Task 1: Production Django settings

**Files:**
- Modify: `backend/fintank_backend/settings.py`, `backend/pyproject.toml`, `backend/uv.lock`, `CLAUDE.md`
- Test: `backend/fintank_backend/test_production_settings.py`

**Interfaces:**
- Produces: env vars `DEBUG`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `CACHE_REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `DATABASE_SSLMODE`, `MEDIA_S3_LOCATION`, `SECURE_HSTS_SECONDS`. All lists are comma-separated.

- [ ] **Step 1: Write failing tests.** Each loads settings in a subprocess with a controlled env (`env -i`-style dict plus `SECRET_KEY=x`, and `DOTENV` disabled by running from a temp cwd with `PYTHONPATH=backend`; `load_dotenv()` must not pick up the real `.env`, so add a `DJANGO_SKIP_DOTENV=1` guard around it), and prints JSON:

```python
def test_debug_defaults_to_false(): assert load({})["DEBUG"] is False
def test_debug_true_only_when_set(): assert load({"DEBUG": "True"})["DEBUG"] is True
def test_hosts_from_env():
    assert load({"ALLOWED_HOSTS": "api.thefintank.com,localhost"})["ALLOWED_HOSTS"] == ["api.thefintank.com", "localhost"]
def test_local_defaults_keep_localhost():
    s = load({})
    assert "localhost" in s["ALLOWED_HOSTS"] and "http://localhost:8020" in s["CORS_ALLOWED_ORIGINS"]
    assert not any("heroku" in h for h in s["ALLOWED_HOSTS"])
def test_redis_from_env_and_local_defaults():
    assert load({})["CACHES"]["default"]["LOCATION"] == "redis://127.0.0.1:6379/15"
    assert load({})["CELERY_BROKER_URL"] == "redis://localhost:6379/0"
    assert load({"CACHE_REDIS_URL": "redis://redis:6379/15"})["CACHES"]["default"]["LOCATION"] == "redis://redis:6379/15"
def test_plain_postgres_engine_and_no_gis():
    s = load({})
    assert s["DATABASES"]["default"]["ENGINE"] == "django.db.backends.postgresql"
    assert "django.contrib.gis" not in s["INSTALLED_APPS"]
def test_sslmode_only_when_set():
    assert "OPTIONS" not in load({})["DATABASES"]["default"]
    assert load({"DATABASE_SSLMODE": "require"})["DATABASES"]["default"]["OPTIONS"] == {"sslmode": "require"}
def test_media_goes_to_s3_when_not_debug():
    s = load({"AWS_BUCKET_NAME": "b"})
    assert s["STORAGES"]["default"]["BACKEND"] == "storages.backends.s3.S3Storage"
    assert s["STORAGES"]["default"]["OPTIONS"]["location"] == "media"
    assert s["MEDIA_URL"] == "https://b.s3.amazonaws.com/media/"
def test_media_local_when_debug():
    assert load({"DEBUG": "True"})["STORAGES"]["default"]["BACKEND"] == "django.core.files.storage.FileSystemStorage"
def test_static_storage_preserved():
    assert "staticfiles" in load({})["STORAGES"]
def test_secure_flags_only_when_not_debug():
    s = load({})
    assert s["SESSION_COOKIE_SECURE"] and s["CSRF_COOKIE_SECURE"]
    assert s["SECURE_PROXY_SSL_HEADER"] == ["HTTP_X_FORWARDED_PROTO", "https"]
    assert load({"DEBUG": "True"})["SESSION_COOKIE_SECURE"] is False
```

- [ ] **Step 2: Run to confirm failure.** `cd backend && ../../.venv/bin/python manage.py test fintank_backend.test_production_settings`. Expected: failures on each.

- [ ] **Step 3: Change settings.**
  - Add `env_list(name: str, default: list[str]) -> list[str]`.
  - `DEBUG` defaults to `'False'`.
  - `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` use `env_list`; defaults are the existing localhost entries only (drop Heroku, Vercel, DigitalOcean).
  - Replace the hard-coded cache/broker/result URLs with the env vars, keeping today's values as defaults. Remove the unused `REDIS_URL` handling and the duplicate result backend.
  - Set the engine to `django.db.backends.postgresql`, remove `django.contrib.gis`, `GEOS_LIBRARY_PATH`, `GDAL_LIBRARY_PATH`. Keep `django.contrib.postgres`.
  - Replace `DEFAULT_FILE_STORAGE` with `STORAGES`. Default backend `S3Storage` with `location` from `MEDIA_S3_LOCATION` (default `media`) when not `DEBUG`, `FileSystemStorage` when `DEBUG`. `staticfiles` backend is `whitenoise.storage.CompressedStaticFilesStorage`. `MEDIA_URL` includes the location.
  - When not `DEBUG`: `SECURE_PROXY_SSL_HEADER`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS = int(env, default 0)`. Do not set `SECURE_SSL_REDIRECT`; Caddy handles it and internal health checks use HTTP.
  - Wrap `load_dotenv()` in the `DJANGO_SKIP_DOTENV` guard.

- [ ] **Step 4: Add gunicorn.** `cd backend && uv add gunicorn`.

- [ ] **Step 5: Run everything.** `../../.venv/bin/python manage.py test` and `../../.venv/bin/python manage.py makemigrations --check --dry-run`. Expected: all pass, no migration changes. If any app needs a geo import, stop and report it.

- [ ] **Step 6: Update `CLAUDE.md`:** database is plain PostgreSQL, drop the GEOS/GDAL lines, list the new env vars, state that local `backend/.env` needs `DEBUG=True`.

- [ ] **Step 7: Commit.** `fix(settings): read production config from the environment`

### Task 2: Health endpoint

**Files:**
- Create: `backend/fintank_backend/health.py`
- Modify: `backend/fintank_backend/urls.py` (route before `pages.urls`)
- Test: `backend/fintank_backend/test_health.py`

**Interfaces:**
- Produces: `GET /healthz/` → 200 `{"status": "ok", "db": true, "redis": true}` or 503 with the failing part `false`. No auth. Never includes error text or connection details.

- [ ] **Step 1: Write failing tests:** `test_ok_when_db_and_cache_work`, `test_503_when_db_fails` (patch `connection.cursor` to raise; body has `"db": false`), `test_503_when_cache_fails` (patch `cache.set` to raise; body has `"redis": false`), `test_error_text_not_exposed` (exception message containing `secret-host` is absent from the body).
- [ ] **Step 2: Run to confirm failure.** `manage.py test fintank_backend.test_health`
- [ ] **Step 3: Implement `healthz(request) -> JsonResponse`** with `SELECT 1` and a cache `set`/`get` round trip with a 10s TTL. Catch `Exception` for each check.
- [ ] **Step 4: Run to confirm pass.**
- [ ] **Step 5: Commit.** `feat(api): add a health endpoint for deploys and uptime checks`

### Task 3: API image

**Files:**
- Create: `backend/Dockerfile`, `backend/.dockerignore`

**Interfaces:**
- Produces: image running `gunicorn fintank_backend.wsgi --bind 0.0.0.0:8000 --workers 2 --timeout 120` by default, user `app` (uid 10001). The same image runs Celery through a Compose `command`.

- [ ] **Step 1: Write `.dockerignore`:** exclude `class_files`, `media`, `.env*`, `**/.env*`, `.venv`, `**/__pycache__`, `*.whl`, `*.whl:Zone.Identifier`, `celerybeat-schedule*`, `notes.txt`, `pipelines/tests`.
- [ ] **Step 2: Write the Dockerfile:** `python:3.12-slim`; install `uv`; `uv sync --frozen --no-dev` before copying source so dependency layers cache; `collectstatic --noinput` at build with a throwaway `SECRET_KEY`; non-root user. No GDAL/GEOS packages.
- [ ] **Step 3: Build and check size and contents.**
```bash
docker build -t fintank-api:test backend
docker run --rm fintank-api:test sh -c 'test ! -e class_files && test ! -e .env && python -c "import pipelines.factor_windows, gunicorn" && echo CLEAN'
docker image ls fintank-api:test --format '{{.Size}}'
```
Expected: build context well under 500 MB, `CLEAN` printed, image under 1.5 GB. If a native library is missing, add only that package.
- [ ] **Step 4: Commit.** `feat(deploy): add the API image`

### Task 4: Web image

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `.npmrc`
- Modify: `next.config.ts`

**Interfaces:**
- Produces: image listening on port 3000. Build args: `NEXT_PUBLIC_FINTANK_API_URL`, `NEXT_PUBLIC_CONFIRMATION_EMAIL_REDIRECT`, `NEXT_PUBLIC_FIREBASE_API`, `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`, `NEXT_PUBLIC_FIREBASE_PROJECT_ID`, `NEXT_PUBLIC_FIREBASE_APP_ID`, `NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID`.

- [ ] **Step 1: Add `.npmrc`** with `legacy-peer-deps=true`. Plain `npm ci` fails with ERESOLVE today. Confirm with `npm ci --dry-run`.
- [ ] **Step 2: Add `output: 'standalone'`** to `next.config.ts`.
- [ ] **Step 3: Write `.dockerignore`:** exclude `backend`, `stables`, `infra`, `anchor`, `docs`, `.next`, `node_modules`, `.env*`, `*.png` at the root only, `class_files`.
- [ ] **Step 4: Write the multi-stage Dockerfile:** `node:22-slim`; `npm ci`; `next build` with `NODE_OPTIONS=--max-old-space-size=4096` and `NEXT_TELEMETRY_DISABLED=1`; the final stage copies `.next/standalone`, `.next/static` and `public`; non-root; `CMD ["node", "server.js"]`.
- [ ] **Step 5: Build and check.**
```bash
docker build -t fintank-web:test --build-arg NEXT_PUBLIC_FINTANK_API_URL=https://api.example.test/api .
docker run --rm fintank-web:test sh -c 'test ! -e .env && test -f server.js && test -d public/images/split_avatars && echo CLEAN'
```
Expected: `CLEAN`. Then confirm no local URL leaked: `docker run --rm fintank-web:test sh -c 'grep -rl "localhost:8000" .next/static | wc -l'` prints `0`, unless the match is a code fallback; report any matches.
- [ ] **Step 6: Commit.** `feat(deploy): add the web image`

### Task 5: Compose, Caddy, deploy script and smoke test

**Files:**
- Create: `deploy/docker-compose.yml`, `deploy/docker-compose.smoke.yml`, `deploy/Caddyfile`, `deploy/env.example`, `deploy/deploy.sh`, `deploy/smoke.sh`

**Interfaces:**
- Consumes: Task 2 `/healthz/`; images from Tasks 3–4.
- Produces: `deploy/deploy.sh <image-tag>`, run on the server from `/opt/fintank`. Services: `caddy`, `web`, `api`, `worker`, `redis`, `db`.

- [ ] **Step 1: Write `docker-compose.yml`.**
  - Images: `ghcr.io/francofin/fintank-web:${IMAGE_TAG}` and `ghcr.io/francofin/fintank-api:${IMAGE_TAG}`.
  - `worker` command: `celery -A fintank_backend worker -B -l info --concurrency 1 -s /tmp/celerybeat-schedule`.
  - `redis`: `redis:7-alpine`, `--maxmemory 300mb --maxmemory-policy volatile-lru --save "" --appendonly no`.
  - `db`: `postgres:16-alpine`, named volume, no published port.
  - Only `caddy` publishes ports (80, 443); named volumes for Caddy data.
  - Memory limits: web 700m, api 1500m, worker 800m, redis 350m, db 512m.
  - Health checks: `api` on `/healthz/`, `db` with `pg_isready`, `redis` with `redis-cli ping`.
  - `restart: unless-stopped`; json-file logging with `max-size: 10m`, `max-file: 3`.
- [ ] **Step 2: Write the `Caddyfile`:** `www.thefintank.com` → `web:3000`; `thefintank.com` redirects to `https://www.thefintank.com{uri}`; `api.thefintank.com` → `api:8000`. Hostnames come from env (`{$SITE_HOST}`, `{$APEX_HOST}`, `{$API_HOST}`) so the smoke test can use its own.
- [ ] **Step 3: Write `env.example`:** every variable name with a blank or safe value, including `BACKTEST_MAX_WORKERS=2`, `DEBUG=False`, `CACHE_REDIS_URL=redis://redis:6379/15`, `CELERY_BROKER_URL=redis://redis:6379/0`, `CELERY_RESULT_BACKEND=redis://redis:6379/0`, `DATABASE_HOST=db`, `FRONTEND_URL=https://www.thefintank.com`.
- [ ] **Step 4: Write `deploy.sh <tag>`.** With `set -euo pipefail`: refuse an empty tag; remember the current tag from `.image-tag`; `docker compose pull`; `docker compose run --rm api python manage.py migrate --noinput`; `docker compose up -d`; poll `api` health for up to 120s; on success write `.image-tag`; on failure redeploy the previous tag if there is one and exit 1. Migrations are not rolled back, so note that in a comment.
- [ ] **Step 5: Write `smoke.sh` and `docker-compose.smoke.yml`.** Project name `fintank-smoke`; Caddy uses `tls internal` and publishes only `127.0.0.1:18443`; locally built `:test` images; dummy secrets; `trap` always runs `docker compose down -v`. It fails unless each check passes:
```text
GET https://api.smoke.test:18443/healthz/ → 200 and "db": true, "redis": true
GET https://www.smoke.test:18443/         → 200
GET https://apex.smoke.test:18443/        → 301/308 to the www host
docker compose exec redis redis-cli config get maxmemory-policy → volatile-lru
docker compose exec worker celery -A fintank_backend inspect ping → pong
docker compose exec api python manage.py check --deploy → no errors
DEPLOY ROLLBACK: deploy.sh with a tag whose api fails health exits 1 and the previous tag stays up
COLD CACHE: flush Redis, GET a data page and an API market endpoint, api stays healthy (OOMKilled=false)
```
Use `curl --resolve` so no hosts-file change is needed.
- [ ] **Step 6: Ask the owner, then run `deploy/smoke.sh`.** Expected: all checks pass and `docker ps` shows no `fintank-smoke` containers afterward. S3-backed pages need read credentials; if the owner prefers not to pass any, record that the cold-cache check moves to Task 8.
- [ ] **Step 7: Commit.** `feat(deploy): add compose, Caddy, deploy script and smoke test`

### Task 6: Nightly database backup

**Files:**
- Create: `deploy/backup_db.sh`, `deploy/test_backup_db.sh`

**Interfaces:**
- Produces: `backup_db.sh`, run from cron at 07:30 UTC. Writes `s3://$BACKUP_BUCKET/postgres/fintank-YYYYMMDD.dump`. On failure, publishes to `$ALERT_TOPIC_ARN` and exits non-zero.

- [ ] **Step 1: Write `test_backup_db.sh` with stubbed `docker` and `aws` on `PATH`.** Cases: `success_uploads_dated_key`, `pg_dump_failure_alerts_and_uploads_nothing`, `empty_dump_alerts_and_uploads_nothing`, `upload_failure_alerts`.
- [ ] **Step 2: Run to confirm failure.** `bash deploy/test_backup_db.sh`
- [ ] **Step 3: Implement.** `pg_dump -Fc` to a temp file with `pipefail`; reject files under 1 KB; upload only after those pass; remove the temp file with `trap`.
- [ ] **Step 4: Run to confirm pass.**
- [ ] **Step 5: Add a real restore check to `smoke.sh`:** dump the smoke database, restore it into a scratch database, compare the `django_migrations` row count.
- [ ] **Step 6: Commit.** `feat(deploy): back up Postgres nightly with failure alerts`

### Task 7: CI and deploy workflow

**Files:**
- Create: `../.github/workflows/fintank-deploy.yml` (monorepo root)

**Interfaces:**
- Consumes: repo secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`; repo variables for each `NEXT_PUBLIC_*` value and `DEPLOY_ENABLED`.
- Produces: images `ghcr.io/francofin/fintank-{web,api}:<git-sha>`.

- [ ] **Step 1: Write the workflow.**
  - Triggers: push to `main` with paths `fintank/**` and the workflow file, plus `workflow_dispatch`. Pushes touching only `fintank/docs/**`, `fintank/backend/pipelines/**` or `fintank/infra/**` must not deploy.
  - `permissions: contents: read, packages: write`.
  - `test`: Postgres 16 and Redis services; `manage.py test`; `eslint` is covered by the web build.
  - `build`: needs `test`; `docker/build-push-action` for each image with GHA layer cache, contexts `fintank` and `fintank/backend`.
  - `deploy`: needs `build`; runs only if `vars.DEPLOY_ENABLED == 'true'`; pins the host with `DEPLOY_KNOWN_HOSTS`; copies `deploy/` to `/opt/fintank`; runs `./deploy.sh ${{ github.sha }}`.
- [ ] **Step 2: Lint.** `docker run --rm -v "$PWD/..:/repo" -w /repo rhysd/actionlint:latest .github/workflows/fintank-deploy.yml`. Expected: no findings.
- [ ] **Step 3: Check path filters** by reasoning through three cases in the commit message's test notes: a frontend change deploys; a docs change doesn't; a change outside `fintank/` doesn't.
- [ ] **Step 4: Commit.** `ci: test, build and deploy Fintank from GitHub Actions`

### Task 8: Server runbook and go-live

**Files:**
- Create: `deploy/README.md`, `deploy/bootstrap_server.sh`, `deploy/iam-django-policy.json`, `deploy/iam-backup-policy.json`
- Modify: `docs/RECENT_CHANGES.md`, `CLAUDE.md`

**Interfaces:**
- Produces: the owner's checklist below, written as exact commands and console paths in `deploy/README.md`. Do not perform these steps for the owner.

- [ ] **Step 1: Write `bootstrap_server.sh`:** installs Docker and Compose, 2 GB swap, `unattended-upgrades`, `fail2ban`, key-only SSH with root login off, a `deploy` user in the `docker` group, `/opt/fintank`, the backup cron line, and AWS CLI. Idempotent. Check with `shellcheck`.
- [ ] **Step 2: Write the IAM policies.** Django user: `s3:GetObject`, `s3:ListBucket` on `thetradingfloor`; `s3:PutObject`, `s3:DeleteObject` only on `thetradingfloor/media/*`. Backup user: `s3:PutObject` only on the backup bucket's `postgres/*`; `sns:Publish` only on `fintank-pipeline-alerts`. Confirm that the pipeline's publish and rollback never touch `media/`.
- [ ] **Step 3: Write `deploy/README.md`** covering the owner's steps, in this order:
  1. Create the Lightsail 4 GB instance (Ubuntu LTS, us-east-1), static IP, firewall: 22, 80, 443. Port 22 stays open because GitHub-hosted runners have no fixed IP, so `bootstrap_server.sh` must disable password and root SSH login and install `fail2ban`. Billing starts here.
  2. Create the IAM users and the private backup bucket with a 30-day lifecycle.
  3. Run `bootstrap_server.sh`. Write `/opt/fintank/.env` (mode 600) from `env.example`. Generate a new `SECRET_KEY` and Postgres password. Log in to GHCR with a `read:packages` token.
  4. Create the Route 53 zone. Recreate the records from DigitalOcean, except point `www`, the apex and `api` at the static IP. Lower TTLs to 300s. Change the nameservers at GoDaddy. Verify with `dns.google`.
  5. Add GitHub secrets and variables. Set `DEPLOY_ENABLED=true`. Owner pushes; the workflow deploys.
  6. Seed. Locally: `manage.py dumpdata stockuploader.Stock users.AvatarPreset | gzip > seed.json.gz` (expect about 12,881 stocks and 48 presets). Copy it to the server, then `manage.py loaddata` in the `api` container, and `createsuperuser`. Delete the copy afterward.
  7. Warm the cache by calling the three scheduled Celery tasks once.
  8. Firebase: add `www.thefintank.com` to authorized domains, delete old users. Stripe: add the webhook at `https://api.thefintank.com/api/billing/webhook/`, and update `STRIPE_WEBHOOK_SECRET`.
  9. Set `SECURE_HSTS_SECONDS=3600` once HTTPS is confirmed.
  10. Lightsail alarms to email; UptimeRobot on `/` and `https://api.thefintank.com/healthz/`.
  11. Run one backup by hand and confirm the S3 object exists.
  12. Later: delete the archived DigitalOcean app and its DNS zone, keeping the account.
  13. Before paying users: move to Option A following the steps in `deploy/README.md`.
- [ ] **Step 4: Write the go-live test list in the README:** sign up, login, avatar upload appears after an `api` restart, watchlist add/remove, stock search, index chart, heatmap, news, a backtest, a billing checkout in Stripe test mode, `free -m` and `docker stats` after clicking through.
- [ ] **Step 5: Update docs.** `docs/RECENT_CHANGES.md`: how the site is hosted and deployed, with the runbook link. `CLAUDE.md`: deploy commands pointer.
- [ ] **Step 6: Commit.** `docs(deploy): add the server runbook and go-live checklist`
