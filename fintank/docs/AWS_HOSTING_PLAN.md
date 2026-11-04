# Plan: move the whole Fintank web app to AWS

Status: **decided 2026-11-04, build not started.** Written 2026-10-26. Implementation plan: `docs/superpowers/plans/2026-11-04-aws-web-hosting.md`.
Goal: run the frontend, backend, database, cache and background jobs on AWS, alongside the data pipeline that is already there. Spend clearly less than the old **~112 CAD/month** (Heroku ~64 + DigitalOcean ~48).

**Decisions (these override anything below that conflicts):**
- **Start on Option B** (Postgres on the server, about 43 CAD/month with 13% tax), and **move to Option A** (about 63 CAD/month with tax) before taking paying users.
- **Fresh database.** Nothing was migrated from Heroku, so the dump/restore, temporary hostnames and cutover steps in section 6 no longer apply.
- **Registry:** GHCR. **Frontend:** on the server. **Domain:** `thefintank.com`, with DNS moving from DigitalOcean to Route 53; GoDaddy stays the registrar.
- **Old hosting is already off** (2026-11-04): the Heroku app is deleted and `thefintank-app` is archived on DigitalOcean, so the site is offline until go-live. `orca-app` and the Droplet on DigitalOcean are separate and stay.
- **Tables needing seed data:** only `Stock` and `AvatarPreset`.

Prices below are AWS us-east-1 list prices in USD, converted at **1.39 CAD/USD**. They exclude tax. Confirm them in the [AWS Pricing Calculator](https://calculator.aws/) before committing; AWS pricing pages are the authority.

---

## 1. What has to be hosted

What the code needs, checked against the repo on 2026-10-26:

| Part | What it is today | What it needs |
|---|---|---|
| Frontend | Next.js 15.4, Pages + App Router. It has **12 `getServerSideProps` pages** and **API routes** (`src/pages/api/auth`, `billing`, `backtester`, `watchlist`, `articlefetcher`, `imagefetcher`). | A **Node server** (SSR). A static export to S3 is **not** possible. |
| Backend API | Django + DRF, served with WhiteNoise for static files. It reads market data from S3 (`thetradingfloor`) and caches it in Redis. | Python app server (gunicorn), about 1–2 GB RAM (pandas/parquet). |
| Database | PostgreSQL, using the **PostGIS** engine (`django.contrib.gis.db.backends.postgis`). | PostgreSQL. **No model uses a geo field**, so plain PostgreSQL works; see 5.3. |
| Cache + queue | Redis: Django cache (db 15) and Celery broker/results (db 0). | One small Redis. |
| Background jobs | Celery worker + beat, with **only 3 scheduled tasks**: news cache 10:00 UTC, profiles and econ 20:00 UTC. | A small always-on process, or cron. |
| Media | User avatars/uploads go to S3 (`storages`) and Cloudinary. | Unchanged. |
| Payments | Stripe, via the Next billing API route and Django. | A stable HTTPS URL for webhooks. |
| Data pipeline | Already on AWS (ECS Fargate + Step Functions). | Unchanged. |

Traffic is low (a personal/early-stage product), so **always-on managed services with per-hour minimums dominate the bill**, not usage. The cheapest sound design keeps the number of always-on things small.

---

## 2. Options compared

### Option A: one Lightsail server + Lightsail managed database (recommended)

- **App server:** one **Lightsail instance (4 GB RAM, 2 vCPU, 80 GB SSD, 4 TB transfer)** runs everything except the database, under Docker Compose:
  - **Caddy**: HTTPS (automatic Let's Encrypt), routing `fintank.<domain>` → Next.js and `api.fintank.<domain>` → Django.
  - **Next.js** (standalone production server).
  - **Django** (gunicorn, 2–3 workers).
  - **Celery** worker + beat in one process (`-B`), which is fine with 3 daily tasks.
  - **Redis** (cache + broker, append-only persistence off; it's a cache).
- **Database:** a **Lightsail managed PostgreSQL database** (standard plan). It includes automatic daily backups and point-in-time restore, and connects over Lightsail's private network.
- **Builds:**
  - Docker images are built by **GitHub Actions**, not on the server (`next build` needs ~2–3 GB RAM), and pushed to a registry.
  - The server pulls them and restarts (`docker compose pull && up -d`).

Why Lightsail over plain EC2:
- Fixed monthly bundles that include the IPv4 address, SSD and a large transfer allowance, so there are no surprise line items.
- Simplest console.
- Same AWS account and billing as the pipeline.

### Option B: lean, everything on one server

Same as A, but PostgreSQL runs as a container on the same instance. Backups are a nightly `pg_dump` to S3 plus Lightsail snapshots.
- **Cheapest.**
- If the server dies, the database restore is manual, and both are on one disk.
- Acceptable only while there are no paying users to lose data for.

### Option C: fully managed containers (for reference)

- Next.js and Django on **ECS Fargate** behind an **Application Load Balancer**.
- **RDS** PostgreSQL and **ElastiCache** Redis.
- This is the textbook setup, but the load balancer alone costs ~$16+/month and every piece has its own hourly minimum. It **costs more than today**, so it isn't worth it at this traffic. Revisit only if traffic needs autoscaling.

### Option A′: frontend on AWS Amplify instead of the server

- Amplify Hosting builds and serves Next.js SSR (managed builds, CDN, preview branches).
- The Lightsail server then only runs Django/Celery/Redis and could be the 2 GB bundle.
- Amplify bills per build minute, GB served and SSR compute. That's likely a few dollars at this traffic, but its SSR rates are hard to pin down from public sources, so treat its line as an estimate.
- A reasonable alternative if the Next build or SSR memory becomes a problem on the server.

---

## 3. Monthly cost

| Item | A (recommended) | B (lean) | A′ (Amplify front) | C (managed) |
|---|---|---|---|---|
| App server | Lightsail 4 GB: **$24** | Lightsail 4 GB: **$24** | Lightsail 2 GB: **$12** | Fargate 2 services (~0.5 vCPU/1 GB each): ~$36 |
| Load balancer | none (Caddy) | none | none | ALB: ~$17 |
| PostgreSQL | Lightsail DB standard: **$15** | on server: $0 | Lightsail DB: **$15** | RDS db.t4g.micro + 20 GB: ~$14 |
| Redis | on server: $0 | on server: $0 | on server: $0 | ElastiCache t4g.micro: ~$12 |
| Frontend hosting | on server: $0 | on server: $0 | Amplify: ~$2–5 (est.) | in Fargate above |
| Backups | included | S3 + snapshots: ~$2 | included | included |
| DNS (Route 53 zone) | $0.50 | $0.50 | $0.50 | $0.50 |
| Container registry | GHCR free / ECR ~$0.50 | same | ~$0.50 | ~$0.50 |
| **Total USD** | **~$40** | **~$27** | **~$31–34** | **~$80+** |
| **Total CAD** | **~56** | **~38** | **~43–47** | **~111+** |
| **vs today (112 CAD)** | **−50%** | −66% | −60% | about the same |

Not in the table, because you already pay them:
- **Data pipeline:** about $6–10/month. The weekly run is a 4 vCPU/16 GB Fargate task for about 5h ≈ $1.10, plus daily news runs, S3 storage and versioning.
- **Domain:** your registrar.
- **Cloudinary, Stripe, FMP, SerpAPI.**

Ways to cut further later:
- If the server sits mostly idle, test the 2 GB bundle ($12).
- Lightsail can't resize down in place: take a snapshot and create a smaller instance from it.
- An EC2 t4g instance with a 1-year Savings Plan is ~30–40% cheaper than on-demand EC2, but needs more setup than Lightsail.

---

## 4. Recommendation

Go with **Option A**:

| | |
|---|---|
| Cost | About **56 CAD/month**, half of today's bill |
| Database | Real backups and point-in-time restore for user accounts and Stripe-linked data |
| Ops | One server to understand |
| Fit | Everything stays in the same AWS account as the pipeline, with the same SNS alerts |

Option B is the fallback if cost matters more than database safety. Revisit C only if traffic grows enough to need autoscaling.

---

## 5. Work needed before any deploy

These are code and config changes in this repo. Each is small, but all are required:

1. **Fix the frontend build.** Done 2026-11-03.
   - `next build` failed on `anchor/src/counter-exports.ts` importing `../target/idl/counter.json`. That file could never be generated: the repo has no `counter` program, only an empty `fintank` one.
   - Removed the unused counter scaffold (`/counter`, `src/components/counter`, `anchor/src`), then fixed the 3 type errors and 2 lint errors behind it.
2. **Production settings for Django** (`backend/fintank_backend/settings.py`):
   - `DEBUG` defaults to **True** when unset. Make it default to False.
   - `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` are hard-coded to Heroku/localhost; read them from env.
   - Celery broker/results and the cache location are hard-coded to `localhost`/db 15. Read `REDIS_URL` from env and keep db numbers configurable.
   - Add `SECURE_PROXY_SSL_HEADER`, `CSRF_TRUSTED_ORIGINS`, secure cookies, and HSTS once HTTPS works.
3. **Database engine.**
   - Switch to `django.db.backends.postgresql`; no model uses geo fields.
   - This removes GDAL/GEOS from the image, making it smaller and faster to build. Lightsail managed Postgres may not offer PostGIS anyway.
   - Verify with a full `manage.py test` and a migration check against a restored copy.
4. **Dockerfiles + Compose.**
   - `backend/Dockerfile`: gunicorn.
   - `Dockerfile` for Next with `output: 'standalone'`.
   - `deploy/docker-compose.yml`: caddy, web, api, worker, redis.
   - `deploy/Caddyfile`.
   - Build context = `fintank/` only, never the monorepo root. This keeps the shared root `.env` and the other projects out of the images.
5. **CI (GitHub Actions).**
   - Path filter `fintank/**`.
   - Run tests, build both images, push to GHCR (free) or ECR.
   - Deploy over SSH: `docker compose pull && docker compose up -d`, then `manage.py migrate`.
6. **Secrets.**
   - A root-only `.env` on the server (or SSM Parameter Store, read at startup).
   - Lightsail instances can't use IAM instance roles, so Django's S3 access needs a dedicated IAM user with **read-only access to `thetradingfloor`**, plus write access to the media prefix.
   - Never reuse the pipeline or admin credentials.

---

## 6. Migration steps

| Phase | What | You do in AWS | Est. time |
|---|---|---|---|
| 0 | Repo changes from section 5, tested locally with Docker Compose | none | 1–2 sessions |
| 1 | Create Lightsail instance (4 GB, Ubuntu LTS, us-east-1) + static IP + firewall (22 from your IP only, 80, 443) | console | 30 min |
| 2 | Create Lightsail PostgreSQL (standard), private access only | console | 15 min |
| 3 | Install Docker, add the deploy user and SSH key for CI, write the `.env` | SSH | 30 min |
| 4 | Restore data: `pg_dump` from Heroku Postgres → `pg_restore` into Lightsail DB | CLI | 30 min |
| 5 | First deploy via CI to **temporary hostnames** (e.g. `new.` / `api-new.`) and test everything: login, billing, backtester, watchlist, charts, news | DNS + browser | 1–2 h |
| 6 | Stripe: add the new webhook endpoint (keep the old one until cutover) | Stripe dashboard | 10 min |
| 7 | **Cutover:** put Heroku in maintenance mode, take a final DB dump and restore, switch DNS to Lightsail, update `NEXT_PUBLIC_FINTANK_API_URL`/CORS | DNS | 1 h |
| 8 | Watch for a week: SNS/CloudWatch alarm on instance status, uptime check | console | — |
| 9 | Cancel Heroku dynos/add-ons and the DigitalOcean app **after a week of clean running**. Keep the final Heroku DB dump in S3 | Heroku / DO | 15 min |

Set the DNS TTL low (300s) a day before cutover so the switch and any rollback are fast. The rollback plan is to point DNS back to Heroku/DO, which stay untouched until phase 9.

---

## 7. Monitoring (cheap)

- **Lightsail metric alarms**, free with the instance: CPU, status checks and burst capacity, notifying the existing SNS topic or email.
- **Uptime check:** CloudWatch Synthetics costs money; a free external pinger (e.g. UptimeRobot) on `/` and an API health endpoint is enough.
- **Logs:** Docker's json-file driver with rotation on the server. CloudWatch Logs only if needed (billed per GB).
- **A small `/healthz` endpoint** in Django that checks the DB and Redis connections.

---

## 8. Open decisions

1. Option **A** (managed DB, ~56 CAD) or **B** (DB on the server, ~38 CAD)?
2. **Domain:** what is it, and where is DNS hosted today? Move it to Route 53, or just point records at the static IP?
3. **Current Heroku add-ons:** which Postgres plan, which Redis, and the database size? This sizes the Lightsail DB and the dump/restore window.
4. **Registry:** GHCR (free, with GitHub) or ECR (same account as the pipeline)?
5. **Frontend:** on the server (A) or Amplify (A′)?

Next step once these are answered: turn sections 5 and 6 into a task-by-task implementation plan under `docs/superpowers/plans/`.

---

### Price sources (checked 2026-10-26; confirm in the calculator)

- Lightsail bundles and managed database starting prices: [Lightsail bundles (AWS docs)](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-bundles.md), [CloudZero: Lightsail pricing](https://www.cloudzero.com/blog/amazon-lightsail-pricing/), [cloudburn: Lightsail total cost](https://cloudburn.io/blog/amazon-lightsail-pricing)
- RDS db.t4g.micro ≈ $0.016/h in us-east-1: [Holori](https://calculator.holori.com/aws/rds/db.t4g.micro), [Bytebase](https://www.bytebase.com/dbcost/rds/instance/db.t4g.micro/), [AWS RDS PostgreSQL pricing](https://aws.amazon.com/rds/postgresql/pricing)
- Amplify Hosting (build $0.01/min, $0.15/GB served, $0.023/GB-month stored; SSR rates vary by source): [wring.co Amplify pricing guide](https://wring.co/blog/aws-amplify-pricing-guide), [zenn: Next.js on AWS 2026](https://zenn.dev/aws_japan/articles/nextjs-on-aws-2026)
- ALB, ElastiCache, Fargate, EC2 and public IPv4 figures are from AWS list prices as known at writing. Verify them in the calculator.
