# Deploy handoff: getting the site live on AWS

Written 2026-11-08, updated 2026-11-10. Read this first in a deploy session, then `deploy/README.md` (the runbook) for every command. Hosting decisions are in `docs/AWS_HOSTING_PLAN.md`. Pipeline state is in `docs/RECENT_CHANGES.md`.

## Where things stand

- **The site is not live.** The old Heroku backend is deleted and the DigitalOcean app is archived.
- **All hosting code is on `main`:**
  - PR #1 (`7091960`, merged 2026-11-05) added the Docker images, Compose stack, Caddy, deploy/backup/disk scripts, the GitHub Actions workflow, login rate limits and the runbook.
  - PR #2 (`e6066b9`, merged 2026-11-08) added the owner's frontend work: index peer chart and valuations table, and 54 unused npm packages removed.
  - The index attribution work (16 commits, through `ed5daf4`) went straight to `main` before PR #2.
  - After PR #2: the capital-markets bullet commentary (`feat/spread-bullets`, with its CI test) and the attribution handoff doc (`feat/index-attribution`, `8bbc1e1`) were merged, ending at `75af3ca`.
- **Local `main` matches GitHub** at `75af3ca` (2026-11-09), and `npm install` has been run.
- **Runbook progress:** step 1 done 2026-11-10, so **the hosting bill has started** (Lightsail 4 GB, $24 USD/month before tax). Step 2 is half done: the backup bucket exists, the IAM users do not yet. Steps 3 onwards are not started. If you stop part-way, see "Stopping and deleting" at the end of the runbook.
- **Server:** Lightsail instance `fintank` (Ubuntu 24.04.4 LTS, `us-east-1a`, dual-stack). Static IP `fintank-ip` = **`52.21.34.225`**: this is `SERVER_IP` in the runbook. SSH as `ubuntu` with `~/.ssh/LightsailDefaultKey-us-east-1.pem`.

## The GitHub workflow is red on purpose

`.github/workflows/fintank-deploy.yml` runs on every push to `main` that touches `fintank/` (docs, `backend/pipelines/` and `infra/` excluded, apart from `pipelines/factor_windows.py`).

- **test** runs the Django tests, the backup and disk script tests, and the `safeFetch` URL-guard test. It is green on runs #2 to #5 (#5 is the latest, for `75af3ca`).
- **build** fails in about 5 seconds with `Repository variable NEXT_PUBLIC_FINTANK_API_URL is empty`. This guard is deliberate: it stops a site being built that points at no API. It clears in runbook step 5.
- **deploy** is skipped. It only runs when the repo variable `DEPLOY_ENABLED` is `true` and the branch is `main`.
- The workflow does not run on PRs, so a PR shows no checks.
- **The frontend is not built on GitHub until step 5.** Until then, check frontend changes locally before pushing (see "Checking a frontend change" below).
- **Two notices, nothing to do now:**
  - Pinned actions target Node 20 and GitHub runs them on Node 24. They work; bump the pins at some point.
  - `ubuntu-latest` moves to Ubuntu 26. That affects the CI runners only, not the server. If a run fails strangely, pin `ubuntu-24.04`.

## Go-live order (runbook `deploy/README.md`)

| Step | What | Who | Status |
|---|---|---|---|
| 1 | Lightsail 4 GB in `us-east-1`, static IP `fintank-ip`, ports 22/80/443, SSH test. **Billing starts here.** | owner (console) | **done 2026-11-10** (`52.21.34.225`) |
| 2 | Backup bucket `fintank-backups-137315715959`, IAM users `fintank-django` and `fintank-backup`. Run from `fintank/`. | owner | **half done**: bucket created 2026-11-10 (public access blocked, `expire-30-days` rule, AES256 default encryption, empty). IAM users `fintank-django`, `fintank-backup` next. |
| 3a–e | Deploy key, `bootstrap_server.sh`, backup credentials, `/opt/fintank/.env`, GHCR pull access | owner | not started |
| 4 | DNS to Route 53: apex, `www`, `api` A records to the static IP; wait until all three resolve | owner | not started |
| 5 | GitHub secrets (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`) and variables (API URL, email redirect, 5 Firebase values, `DEPLOY_ENABLED=true` last). First deploy. | owner | not started |
| 6 | Seed `Stock` (12,881) and `AvatarPreset` (48) | owner | not started |
| 7 | Warm the cache | owner | not started |
| 8 | Firebase authorised domains and Stripe | owner | not started |
| 9 | HSTS | owner | not started |
| 10 | Monitoring (disk alarm, backup heartbeat) | owner | not started |
| 11 | One backup by hand, then a restore check | owner | not started |
| 12 | Clean up DigitalOcean | owner | later |
| 13 | Move to a managed database (Option A) | owner | before paying users |

Then work through the runbook's **Go-live test list**, the avatar upload test and the heatmap timing.

**Step 1 notes for WSL:**
- Copy the key into the WSL home folder; `chmod` does not work on the Windows drive. For example: `cp /mnt/c/Users/<you>/Downloads/LightsailDefaultKey-us-east-1.pem ~/.ssh/ && chmod 600 ~/.ssh/LightsailDefaultKey-us-east-1.pem`.
- The runbook writes the key's short name; use `~/.ssh/LightsailDefaultKey-us-east-1.pem` instead.

## Before the first deploy (step 5): dependency vulnerabilities

`npm install` reports 59 vulnerabilities. They existed before PR #2. `npm audit --omit=dev` (packages the live site uses) on 2026-11-08: 43 in total, **4 critical, 22 high**.

**Fix before go-live, with the safe `npm audit fix` (no major versions):**
- `dompurify` (critical, XSS; direct, cleans article HTML)
- `axios` (high, SSRF bypass; direct)
- `form-data`, `immutable`, `nanoid`, `picomatch`, `ws`, `websocket-driver` (critical), `source-map-js`, `svgo`, `browserslist`, `@babel/plugin-transform-modules-systemjs` (indirect, plain fixes)

**Later: major upgrades, each needing its own test** (put on the before-paying-users list):

| Upgrade | Fixes | Notes |
|---|---|---|
| `firebase` 13 | `protobufjs` (critical), `@grpc/grpc-js`, firestore packages | Sign-in and sign-up need retesting |
| `swiper` 14 | prototype pollution (critical) | Carousels need retesting |
| ~~`sharp` 0.35~~ | install-time command injection | Resolved by dropping the unused direct `sharp` 0.29 (branch `fix/npm-audit-safe-drop-sharp`); `next` keeps its own `sharp` 0.35.5 |
| `next` 16 | `postcss` | Large upgrade; not for go-live |
| `@solana/spl-token`, `@coral-xyz/anchor` | `bigint-buffer` | No good fix; Solana is off on the live site (`NEXT_PUBLIC_ENABLE_SOLANA` is not passed to the build) |
| `toml` | uncontrolled recursion | No fix offered |

**Never run `npm audit fix --force`.** It applies all the major upgrades at once, untested.

**Safe pass done 2026-11-09** on branch `fix/npm-audit-safe-drop-sharp` (PR pending). `npm audit --omit=dev` went from 43 (4 critical, 22 high) to 22 (1 critical, 12 high): every target listed above is fixed, and only the major upgrades below remain. `package.json` changed by one line, removing the unused direct `sharp` (see the build note under "Checking a frontend change"). The image build passes; lint shows 0 errors and 282 warnings. After merging, the owner runs `npm install` locally.

**How the safe pass was done:** in a throwaway worktree, run `npm audit fix` (without `--force`). Check `git diff package.json` shows no major version change. Run the image build below. Run lint. Open a PR like PR #2. After merging, the owner runs `npm install` locally.

## Checking a frontend change before pushing

**Never run `next build` in the main folder.** It rewrites `.next/` and breaks a running dev server; recovery is `rm -rf .next` and a dev-server restart.

The most faithful check is the same Docker build GitHub will run, from a throwaway worktree:

```bash
git worktree add --detach <scratch>/wt <branch>
mkdir -p <scratch>/dockercfg && echo '{}' > <scratch>/dockercfg/config.json
cd <scratch>/wt/fintank
sg docker -c "DOCKER_CONFIG=<scratch>/dockercfg docker build -q -t fintank-web:check \
  --build-arg NEXT_PUBLIC_FINTANK_API_URL=https://api.thefintank.com/api \
  --build-arg NEXT_PUBLIC_CONFIRMATION_EMAIL_REDIRECT=https://www.thefintank.com/completesignup \
  --build-arg NEXT_PUBLIC_FIREBASE_API=AIzaSyDummyDummyDummyDummyDummyDummy00 \
  --build-arg NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=dummy.firebaseapp.com \
  --build-arg NEXT_PUBLIC_FIREBASE_PROJECT_ID=dummy \
  --build-arg NEXT_PUBLIC_FIREBASE_APP_ID=1:000000000000:web:0000000000000000 \
  --build-arg NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID=G-DUMMY00000 ."
```

- It does a clean `npm ci` from the lockfile, so it catches a removed package that is still imported. It takes a few minutes.
- **Firebase must not be empty:** with empty values, prerender fails (`auth/invalid-api-key`). The dummy values are for test builds only.
- **`DOCKER_CONFIG` is needed** because Docker Desktop's credential helper (`desktop.exe`) can time out under WSL with `error getting credentials`. Public images need no sign-in.
- **`sg docker -c`** is needed because the shell user is not in the `docker` group by default.
- **`npm ci` failing on `sharp` with `Installation error: Request timed out`** (seen 2026-11-09; `main` at `75af3ca` failed the same way): the old direct `sharp` 0.29 downloads libvips from GitHub in its install script and gave up every time under `npm ci` in `node:22-slim`. Nothing imported it, so it was removed. If it comes back, check `package.json` for a direct `sharp` entry; `next` brings its own.
- Clean up afterwards: `git worktree remove --force <scratch>/wt && sg docker -c 'docker rmi -f fintank-web:check && docker builder prune -f'`.
- **Lint:** `npx eslint <files>` from `fintank/` with `node_modules` available. On 2026-11-08 there were 0 errors and 282 old warnings.
- **The full stack** can be tested locally with `deploy/docker-compose.smoke.yml` and `deploy/smoke.sh` (16 checks; all passed on 2026-11-05). The old test images `fintank-api:test` and `fintank-web:test` (about 3 GB) can be deleted.

**A new `NEXT_PUBLIC_*` setting needs three things,** or it is empty on the live site: an `ARG`/`ENV` in `fintank/Dockerfile`, a `build-args` line in the workflow, and a GitHub variable. None were added in PR #2.

## Things to raise with the owner

- **Login limits** (open item in `RECENT_CHANGES.md`): `/admin/login/` and `/login/` allow 20 attempts an hour per address and 100 per account. Ask during the go-live login check and again before paying users.
- **Untracked files** in `fintank/`: `docs/project_overview.{md,html}` and `stables/`. They are the owner's; leave them alone.
- **Known gaps, decide after go-live:**
  - stale-backtest cleanup
  - gunicorn `--threads`
  - a Celery beat entry for the heatmap (decide from the heatmap timing)
  - a client at 1 request per second could block `www` logins
  - small hardening in the URL guard and log redaction
- **Untested until go-live:** reading the S3 data from the server, Let's Encrypt, GHCR pulls, Stripe, FMP and Firebase.

## Working rules for a deploy session

- The owner runs every AWS change, deploy, approval, push and pull. From the session's shell, AWS calls are **read-only** (`AWS_PROFILE=fintank`).
- The shell cannot push or fetch: the SSH key has a passphrase and `gh` is not installed. Ask the owner to push, and to send screenshots of Actions runs.
- Never start Django, Celery, `npm run dev` or any long-running process for the owner. Name what is needed and wait.
- Never print, ask for or paste secrets: IAM keys, the deploy key, Firebase or Stripe keys. The server IP is fine.
- All work stays in `fintank/`. Commit only when asked.
