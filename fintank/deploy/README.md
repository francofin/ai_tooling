# Fintank server runbook and go-live

Status: **the site is not live until you finish this runbook.** The old Heroku backend is deleted and the DigitalOcean app `thefintank-app` is archived, so `thefintank.com` is offline today.

You do these steps yourself, in order. Each one says how to confirm it worked. Do not move on until it did.

**Cost.** Billing starts at step 1, when the Lightsail instance is created. Expect roughly 43 CAD/month with tax (4 GB instance, static IP, Route 53 zone, small S3 usage). If you stop part-way, delete the instance (see "Stopping and deleting" at the end), or you keep paying.

## What is where

| Thing | Value |
|---|---|
| AWS account / region | `137315715959` / `us-east-1` |
| AWS CLI profile (SSO, for you) | `fintank` (`aws sso login --profile fintank`) |
| Live data + media bucket | `thetradingfloor` |
| Backup bucket (you create) | `fintank-backups-137315715959` |
| Alert topic | `arn:aws:sns:us-east-1:137315715959:fintank-pipeline-alerts` |
| Server folder | `/opt/fintank` (files copied by CI, plus your `.env`) |
| Images | `ghcr.io/francofin/fintank-web`, `ghcr.io/francofin/fintank-api` (private) |
| Sites | `https://www.thefintank.com`, `https://api.thefintank.com`, apex redirects to `www` |

Throughout, `SERVER_IP` is the static IP from step 1. Commands marked "your machine" run on your laptop, "server" means over SSH.

The runbook assumes you run commands from the repo folder `fintank/` on your machine.

---

## 1. Create the Lightsail instance (billing starts here)

1. AWS console, search **Lightsail**. Region `us-east-1` (top right, "Virginia").
2. **Create instance**: Platform **Linux/Unix**, blueprint **OS Only, Ubuntu** (the newest LTS offered), plan **4 GB** (check the monthly price shown), name `fintank`. Create.
3. Instance, **Networking** tab, **Create static IP**, attach it to `fintank`, name it `fintank-ip`. Write down the address: this is `SERVER_IP`.
4. Same tab, **IPv4 Firewall**: keep **SSH 22**, add **HTTP 80** and **HTTPS 443** (Add rule, Application: HTTP / HTTPS). Do the same under **IPv6 Firewall** if it is shown.
   - Port 22 stays open to everyone because GitHub's runners have no fixed IP. `bootstrap_server.sh` makes that safe: key-only SSH, root login off, `fail2ban` installed.
5. Account page, **SSH keys** (or the instance's **Connect** tab), download the default key for `us-east-1` (`LightsailDefaultKey-us-east-1.pem`). On your machine: `chmod 600 LightsailDefaultKey-us-east-1.pem`.

Confirm: `ssh -i LightsailDefaultKey-us-east-1.pem ubuntu@SERVER_IP` gives you a prompt (type `yes` to the fingerprint question). Type `exit`.

## 2. IAM users and the backup bucket

Run on your machine with the SSO profile. If a command says you lack IAM permissions, do the same thing in the console (IAM, Users, Create user, attach an inline policy with the JSON from the file).

```bash
aws sso login --profile fintank
export AWS_PROFILE=fintank AWS_DEFAULT_REGION=us-east-1
BUCKET=fintank-backups-137315715959
```

**Backup bucket (private, objects deleted after 30 days):**

```bash
aws s3api create-bucket --bucket "$BUCKET"
aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" --lifecycle-configuration '{
  "Rules": [{"ID": "expire-30-days", "Status": "Enabled", "Filter": {"Prefix": ""},
             "Expiration": {"Days": 30}, "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7}}]}'
```

(No `LocationConstraint` is needed in `us-east-1`.)

**Two IAM users, one per job.** The policy files are `deploy/iam-django-policy.json` (read `thetradingfloor`, write only `media/*`) and `deploy/iam-backup-policy.json` (upload only to the backup bucket's `postgres/*`, publish only to the alert topic). Never reuse the pipeline or your admin keys.

```bash
aws iam create-user --user-name fintank-django
aws iam put-user-policy --user-name fintank-django --policy-name fintank-django \
  --policy-document file://deploy/iam-django-policy.json
aws iam create-access-key --user-name fintank-django \
  --query 'AccessKey.[AccessKeyId,SecretAccessKey]' --output text

aws iam create-user --user-name fintank-backup
aws iam put-user-policy --user-name fintank-backup --policy-name fintank-backup \
  --policy-document file://deploy/iam-backup-policy.json
aws iam create-access-key --user-name fintank-backup \
  --query 'AccessKey.[AccessKeyId,SecretAccessKey]' --output text
```

Each `create-access-key` prints two values on one line, the access key ID then the secret, **once**. Save each pair straight into your password manager now, labelled "django" and "backup", without copying them into any file, chat or commit. If you lose one, delete that key (`aws iam delete-access-key`) and create a new one.

Confirm: `aws s3api get-bucket-lifecycle-configuration --bucket "$BUCKET"` shows the 30-day rule, and `aws iam list-user-policies --user-name fintank-django` shows `fintank-django` (same for `fintank-backup`).

Note: the pipeline's publish/rollback code (`backend/pipelines/publish.py`) only writes and deletes keys under `index_data/`, `stock_data/` and `econ_data/`, so it never touches `media/`.

## 3. Prepare the server

### 3a. Make the deploy key (your machine)

This is the key GitHub uses to log in as `deploy`.

```bash
ssh-keygen -t ed25519 -f ~/.ssh/fintank_deploy -C fintank-github-deploy -N ""
```

You now have `~/.ssh/fintank_deploy` (private, goes into GitHub in step 5) and `~/.ssh/fintank_deploy.pub` (public, goes onto the server).

### 3b. Run the bootstrap script

```bash
scp -i LightsailDefaultKey-us-east-1.pem deploy/bootstrap_server.sh ~/.ssh/fintank_deploy.pub ubuntu@SERVER_IP:~
ssh -i LightsailDefaultKey-us-east-1.pem ubuntu@SERVER_IP
```

On the server:

```bash
sudo DEPLOY_PUBKEY="$(cat fintank_deploy.pub)" bash bootstrap_server.sh
```

It takes a few minutes. It is safe to run again. It installs Docker, AWS CLI, `fail2ban` and automatic security updates, adds 2 GB of swap, creates the `deploy` user and `/opt/fintank`, installs the nightly backup cron entry for `deploy`, and turns off SSH passwords and root login. It only turns those off if `deploy` already has a key, so it cannot lock you out.

**Before you close the `ubuntu` session**, open a second terminal on your machine and confirm the deploy key works:

```bash
ssh -i ~/.ssh/fintank_deploy deploy@SERVER_IP 'docker ps && echo ok'
```

You should see an empty container list and `ok`. Then `exit` the `ubuntu` session.

### 3c. AWS credentials for the backup (user `deploy`)

The backup runs as `deploy` and needs the **backup** IAM key. On the server as `deploy` (`ssh -i ~/.ssh/fintank_deploy deploy@SERVER_IP`):

```bash
mkdir -p ~/.aws && chmod 700 ~/.aws
nano ~/.aws/credentials
```

Paste exactly this, with the backup user's two values, then save (Ctrl+O, Enter) and exit (Ctrl+X):

```
[default]
aws_access_key_id = BACKUP_ACCESS_KEY_ID
aws_secret_access_key = BACKUP_SECRET_ACCESS_KEY
```

```bash
chmod 600 ~/.aws/credentials
printf '[default]\nregion = us-east-1\n' > ~/.aws/config
aws sts get-caller-identity   # Arn should end in user/fintank-backup
```

### 3d. Write `/opt/fintank/.env`

The CI deploy never touches `.env`. You write it once.

From your machine:

```bash
scp -i ~/.ssh/fintank_deploy deploy/env.example deploy@SERVER_IP:/opt/fintank/.env
```

On the server:

```bash
chmod 600 /opt/fintank/.env
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # use as SECRET_KEY
openssl rand -hex 32                                             # use as DATABASE_PASSWORD
nano /opt/fintank/.env
```

Make a **new** `SECRET_KEY` and Postgres password here. Do not reuse old ones. The password is hex on purpose: a `$` in a Compose env value gets treated as a variable and mangled. Fill in:

| Key | Value |
|---|---|
| `DEBUG` | `False` (must stay `False`) |
| `SECRET_KEY` | the generated string |
| `DATABASE_PASSWORD` | the `openssl rand -hex 32` output |
| `DATABASE_SSLMODE` | leave empty (the `db` container is local) |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | the **django** IAM key from step 2 |
| `AWS_BUCKET_NAME` | `thetradingfloor` |
| `FMP_API`, `FMP_URL`, `FMP_CLOUD_DATA_BASE_URL`, `AZURE_BING_KEY`, `CLOUDINARY_*` | copy from your local `backend/.env` |
| `STRIPE_SECRET_KEY`, `STRIPE_PRICE_PRO_MONTHLY`, `STRIPE_PRICE_PRO_YEARLY` | Stripe dashboard, Developers, API keys / Products. Use **test** keys until the go-live tests pass |
| `STRIPE_WEBHOOK_SECRET` | filled in step 8 |
| `BACKUP_BUCKET` | `fintank-backups-137315715959` |
| `ALERT_TOPIC_ARN` | `arn:aws:sns:us-east-1:137315715959:fintank-pipeline-alerts` |
| `SECURE_HSTS_SECONDS` | keep `0` until step 9 |

The hostname and Redis lines are already right. Check the file has no blanks you meant to fill: `grep -n '=$' /opt/fintank/.env` (the empty `CADDY_GLOBAL_OPTS=`, `DATABASE_SSLMODE=` and `STRIPE_WEBHOOK_SECRET=` are expected for now).

### 3e. Let the server pull private images

1. GitHub, **Settings** (your profile), **Developer settings**, **Personal access tokens**, **Tokens (classic)**, **Generate new token (classic)**. Name `fintank-server-pull`, scope **`read:packages`** only, 90 days or longer. Copy the token.
2. On the server as `deploy`:

```bash
echo 'PASTE_TOKEN' | docker login ghcr.io -u francofin --password-stdin
```

You should see `Login Succeeded`. (Put a calendar reminder to renew the token before it expires, or deploys fail at `compose pull`.)

## 4. DNS (Route 53)

The domain's DNS is at DigitalOcean today and the registrar is GoDaddy. You will host DNS in Route 53 and point GoDaddy's nameservers at it.

1. **Write down every existing record first.** DigitalOcean, **Networking**, **Domains**, `thefintank.com`. Copy each record (type, name, value) into a note: MX (email), TXT (SPF, DKIM, verification), CNAME and so on. If you forget MX records, email stops working.
2. Route 53 console, **Hosted zones**, **Create hosted zone**: name `thefintank.com`, type Public. Create.
3. In the new zone, **Create record** for each record from your list, **except** the apex, `www` and `api`. Set **TTL 300** on everything.
4. Create these three as **A** records with value `SERVER_IP`, TTL 300: apex (leave the name empty), `www`, `api`.
5. Note the four nameservers in the zone's `NS` record.
6. GoDaddy, **My Products**, domain `thefintank.com`, **DNS**, **Nameservers**, **Change**, **Enter my own nameservers**, paste the four Route 53 nameservers (no trailing dot). Save.
7. Keep the DigitalOcean DNS zone for now. It is your fallback for lookup of old records. Delete it in step 12.

Confirm (can take minutes to a few hours):

```bash
curl -s 'https://dns.google/resolve?name=api.thefintank.com&type=A'
curl -s 'https://dns.google/resolve?name=www.thefintank.com&type=A'
curl -s 'https://dns.google/resolve?name=thefintank.com&type=A'
```

Each answer should contain `SERVER_IP`. Do not push a deploy until all three do: Caddy asks Let's Encrypt for certificates on first start and fails if DNS is wrong (see Troubleshooting).

## 5. GitHub secrets and variables, then the first deploy

In GitHub, repo **Settings**, **Secrets and variables**, **Actions**.

**Secrets** (tab Secrets, New repository secret):

| Name | Value |
|---|---|
| `DEPLOY_HOST` | `SERVER_IP` |
| `DEPLOY_USER` | `deploy` |
| `DEPLOY_SSH_KEY` | the whole contents of `~/.ssh/fintank_deploy` (private key), including the `BEGIN`/`END` lines: `cat ~/.ssh/fintank_deploy` |
| `DEPLOY_KNOWN_HOSTS` | output of `ssh-keyscan -t ed25519 SERVER_IP` (your machine) |

For `DEPLOY_KNOWN_HOSTS`, check the key is really your server's before saving. On the server: `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`. On your machine: `ssh-keyscan -t ed25519 SERVER_IP 2>/dev/null | ssh-keygen -lf -`. The two fingerprints must match.

**Variables** (tab Variables, New repository variable). These are public values compiled into the website, so they are variables, not secrets:

| Name | Value |
|---|---|
| `NEXT_PUBLIC_FINTANK_API_URL` | `https://api.thefintank.com/api` |
| `NEXT_PUBLIC_CONFIRMATION_EMAIL_REDIRECT` | `https://www.thefintank.com/completesignup` |
| `NEXT_PUBLIC_FIREBASE_API` | Firebase web API key |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Firebase auth domain |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Firebase project ID |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | Firebase app ID |
| `NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID` | Firebase measurement ID |
| `DEPLOY_ENABLED` | `true` (add last) |

Firebase values: Firebase console, project settings (gear icon), **General**, **Your apps**, the web app, **SDK setup and configuration**, **Config**. Map `apiKey`, `authDomain`, `projectId`, `appId`, `measurementId` to the five names above. **The web build fails without them**, and a deploy will not get past the build job.

**Merge `aws-web-hosting` into `main` first.** The workflow only runs from `main`, so nothing deploys from the branch. Merge the pull request on GitHub (or merge locally and push `main`). Merging changes `fintank/` and starts the deploy by itself; if you add the secrets and variables after the merge, rerun it from **Actions**, **Fintank deploy**, **Run workflow** (branch `main`). The jobs are test, build, deploy.

After the merge, update your local checkout:
- `git checkout main && git pull`, then run `npm install` in `fintank/` (Next moved to 15.5.29).
- `backend/.env` needs `DEBUG=True` for local work (`DEBUG` now defaults to False).

Confirm on the server (as `deploy`):

```bash
cd /opt/fintank && export IMAGE_TAG=$(cat .image-tag)
echo "$IMAGE_TAG"                   # a commit SHA
docker compose ps                   # all services Up; api and db "healthy"
curl -s https://api.thefintank.com/healthz/
```

and `https://www.thefintank.com` loads in a browser (the first certificate can take a minute).

Every `docker compose` command needs to run in `/opt/fintank` with `IMAGE_TAG` set, so each step below starts with `cd /opt/fintank && export IMAGE_TAG=$(cat .image-tag)`. A new SSH session forgets it.

## 6. Seed the data

The new database is empty. Stocks must exist before the first watchlist add (`Stock.objects` is what the watchlist links to), and avatar presets are needed for signup.

On your machine, from the **main folder** (the real checkout at `~/projects/ai_agents/ai_tooling/fintank`, not a branch worktree), where the local database with the stocks is. Prerequisites: `backend/.env` points at that local database and has `DEBUG=True`, and the repo's shared virtualenv exists at `ai_tooling/.venv`.

```bash
cd ~/projects/ai_agents/ai_tooling/fintank/backend
../../.venv/bin/python manage.py shell -c "from stockuploader.models import Stock; from users.models import AvatarPreset; print('stocks', Stock.objects.count(), 'presets', AvatarPreset.objects.count())"
```

This must print `stocks 12881 presets 48` before you go on. If not, you are pointed at the wrong database. Then dump to `/tmp`, outside the repo, so it cannot be committed:

```bash
../../.venv/bin/python manage.py dumpdata stockuploader.Stock users.AvatarPreset | gzip > /tmp/seed.json.gz
ls -lh /tmp/seed.json.gz
```

Copy it up and load it:

```bash
scp -i ~/.ssh/fintank_deploy /tmp/seed.json.gz deploy@SERVER_IP:/opt/fintank/
ssh -i ~/.ssh/fintank_deploy deploy@SERVER_IP
```

On the server:

```bash
cd /opt/fintank && export IMAGE_TAG=$(cat .image-tag)
gunzip -c seed.json.gz | docker compose run --rm -T api python manage.py loaddata --format=json -
docker compose exec -T api python manage.py shell -c "from stockuploader.models import Stock; from users.models import AvatarPreset; print('stocks', Stock.objects.count(), 'presets', AvatarPreset.objects.count())"
```

Expect `stocks 12881 presets 48`. Then create your admin user and delete the copies:

```bash
cd /opt/fintank && export IMAGE_TAG=$(cat .image-tag)
docker compose exec api python manage.py createsuperuser
rm /opt/fintank/seed.json.gz
```

On your machine: `rm /tmp/seed.json.gz`.

## 7. Warm the cache

The worker fills the cache on a schedule. Run the three scheduled tasks once so the site has data now. On the server:

```bash
cd /opt/fintank && export IMAGE_TAG=$(cat .image-tag)
docker compose exec worker celery -A fintank_backend call news.tasks.update_news_articles
docker compose exec worker celery -A fintank_backend call analyzer.tasks.update_universe_profiles
docker compose exec worker celery -A fintank_backend call analyzer.tasks.update_economic_data
docker compose logs -f --tail 50 worker
```

Each `call` prints a task id. In the logs, wait for each to say `succeeded` (press Ctrl+C to stop following; the universe-profiles task can take several minutes). Confirm by loading a few pages on the site.

## 8. Firebase and Stripe

**Firebase** (console, your project, **Authentication**):
- **Settings**, **Authorized domains**, **Add domain**: `www.thefintank.com`. (Also add `thefintank.com` if sign-in popups are used from the apex.)
- **Users**: delete the old users, since the user database was lost with Heroku and the new one is empty.

**Stripe** (dashboard, Developers, **Webhooks**, **Add endpoint**):
- Endpoint URL: `https://api.thefintank.com/api/billing/webhook/`
- Select exactly these events (the ones `backend/billing/sync.py` handles): `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`.
- Open the endpoint and **Reveal** the signing secret (`whsec_...`). On the server: `nano /opt/fintank/.env`, set `STRIPE_WEBHOOK_SECRET=` to it, then
  `cd /opt/fintank && IMAGE_TAG=$(cat .image-tag) docker compose up -d --force-recreate api worker`.

Confirm: in Stripe, **Send test webhook** returns `200`.

## 9. Turn on HSTS

Only after `https://www.thefintank.com` and `https://api.thefintank.com` both load without warnings. On the server set `SECURE_HSTS_SECONDS=3600` in `/opt/fintank/.env` and restart the api (same `up -d --force-recreate api worker` command). Browsers then insist on HTTPS for an hour. Raise it later only when you are sure.

## 10. Monitoring

- **Lightsail alarms**: instance `fintank`, **Metrics** tab. Add alarms for **CPU utilization** (above 80% for 15 minutes) and **Status check failed**, with **Email** notification to your address. Confirm the email subscription when it arrives.
- **UptimeRobot** (free): add two HTTP(s) monitors, `https://www.thefintank.com/` and `https://api.thefintank.com/healthz/`, 5 minute interval, email alerts.

## 11. Run one backup by hand

On the server as `deploy`:

```bash
/opt/fintank/backup_db.sh
tail -n 3 /var/log/fintank-backup.log
crontab -l          # should contain: 30 7 * * * /opt/fintank/backup_db.sh >> /var/log/fintank-backup.log 2>&1
```

The first command should print `backup YYYYMMDD ok: s3://fintank-backups-137315715959/postgres/fintank-YYYYMMDD.dump (N bytes)`. Confirm the object exists, on your machine:

```bash
aws s3 ls s3://fintank-backups-137315715959/postgres/ --profile fintank
```

(This uses your own SSO profile; the backup user itself cannot list, which is intended.) To test restore, practice once on a spare machine: `pg_restore --clean --if-exists -d DBNAME fintank-YYYYMMDD.dump`.

## 12. Later: clean up DigitalOcean

After a week of clean running: delete the archived app `thefintank-app` and the `thefintank.com` DNS zone in DigitalOcean (**Networking**, **Domains**). Keep the account.

## 13. Move to Option A (managed database), before paying users

Today Postgres runs in the `db` container on the same server (Option B). Backups exist but there is no point-in-time restore. Before real paying users, move to a Lightsail managed database (Option A, about 56 CAD/month total).

1. Lightsail, **Databases**, **Create database**: PostgreSQL 16, region `us-east-1`, the smallest **Standard** plan, **private** access only (not public), same VPC as the instance. Write down the endpoint, user, password and database name (`fintank_api`).
2. Put the site in maintenance so no writes happen: simplest is to stop the web and api containers on the server: `cd /opt/fintank && export IMAGE_TAG=$(cat .image-tag) && docker compose stop web api worker`. (The site is down from here.)
3. Dump from the container: `cd /opt/fintank && export IMAGE_TAG=$(cat .image-tag) && docker compose exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > /tmp/move.dump`.
4. Restore into the managed database. From the server with the endpoint in `PGHOST`: `docker run --rm -i -e PGPASSWORD='MANAGED_PASSWORD' postgres:16-alpine pg_restore --no-owner --clean --if-exists -h MANAGED_ENDPOINT -U MANAGED_USER -d fintank_api < /tmp/move.dump`.
5. Edit `/opt/fintank/.env`: `DATABASE_HOST=MANAGED_ENDPOINT`, `DATABASE_USER=`, `DATABASE_PASSWORD=`, `DATABASE_NAME=` to the managed values, and `DATABASE_SSLMODE=require`.
6. Start again: `cd /opt/fintank && export IMAGE_TAG=$(cat .image-tag) && docker compose up -d`. (The `db` container may also start; it is unused now.)
7. Verify: log in, load a watchlist, check `cd /opt/fintank && export IMAGE_TAG=$(cat .image-tag) && docker compose logs api` shows no database errors. Then `rm /tmp/move.dump`.
8. After a few days of clean running, remove the `db` service and the `pgdata` volume from `deploy/docker-compose.yml` (a normal commit and deploy), and update `backup_db.sh` to dump from the managed database (or rely on its automatic backups). Do not remove `db` earlier: it is your way back.

---

## Go-live test list

Do these on `https://www.thefintank.com` with Stripe in **test mode**. Tick each.

- [ ] Sign up a new account, confirm the email link lands on `/completesignup`.
- [ ] Log in and out.
- [ ] Upload an avatar. It shows right away. Then restart the api (`cd /opt/fintank && IMAGE_TAG=$(cat .image-tag) docker compose restart api`) and reload: the avatar is still there (stored in S3, not the container).
- [ ] **The avatar must be publicly readable.** Avatars load from `https://thetradingfloor.s3.amazonaws.com/media/...`. Right-click the avatar, open the image in a new tab. If you see `AccessDenied`, follow "If media is not public" below. Do not assume it works.
- [ ] Add and remove a stock on the watchlist.
- [ ] Stock search returns results.
- [ ] An index chart loads.
- [ ] The heatmap loads.
- [ ] News shows articles.
- [ ] Run a backtest to completion.
- [ ] Billing: start a checkout with Stripe test card `4242 4242 4242 4242`, finish it, confirm the account shows Pro and Stripe shows a `200` for the webhook delivery.
- [ ] On the server, after clicking through: `free -m` (swap use should be small) and `docker stats --no-stream` (nothing near its memory limit: api 1500m, worker 800m, web 700m).

When all pass, switch Stripe to live keys (`STRIPE_SECRET_KEY`, prices, a live-mode webhook with its own `STRIPE_WEBHOOK_SECRET`), recreate api and worker, and run one real small payment.

### If media is not public

Only needed if the avatar test shows `AccessDenied`. Make only `media/*` public, never the whole bucket.

1. S3 console, bucket `thetradingfloor`, **Permissions**, **Block public access**, **Edit**. Untick only **Block public access to buckets and accounts through new public bucket or access point policies** and **Block public and cross-account access to buckets and accounts through any public bucket or access point policies** (leave the two ACL options ticked). Save and confirm.
2. Same tab, **Bucket policy**, **Edit**. Add this statement to the existing list (keep what is there):

```json
{
  "Sid": "PublicReadMedia",
  "Effect": "Allow",
  "Principal": "*",
  "Action": "s3:GetObject",
  "Resource": "arn:aws:s3:::thetradingfloor/media/*"
}
```

3. Reload the avatar URL. It should display. Check `https://thetradingfloor.s3.amazonaws.com/stock_data/` still gives `AccessDenied` (data stays private).

---

## Troubleshooting

**Caddy cannot get a certificate (browser says connection failed or insecure; `docker compose logs caddy` shows ACME or "no valid A records" errors).** DNS has not propagated or points at the wrong IP. Run the three `dns.google` checks from step 4; fix the records until they all return `SERVER_IP`. Check ports 80 and 443 are open in the Lightsail firewall. Then `cd /opt/fintank && export IMAGE_TAG=$(cat .image-tag) && docker compose restart caddy` and watch `docker compose logs -f caddy`. Let's Encrypt rate-limits repeated failures, so fix DNS before retrying many times.

**The deploy rolled back.** The GitHub Action fails and the log says `redeploying previous tag ...` (or "no previous tag" on the first deploy). The site keeps running on the previous version. Look at what failed: open the failed run in GitHub Actions, then on the server `cd /opt/fintank && export IMAGE_TAG=$(cat .image-tag) && docker compose ps && docker compose logs --tail 100 api`. Common causes: a missing or wrong value in `.env`, a failing migration, or `ghcr.io` login expired (`docker login` again). Fix it and push again, or use **Run workflow**. Database migrations are not rolled back, so keep them backward compatible. To pin a specific old version by hand: `IMAGE_TAG=<sha> docker compose up -d`.

**A "Fintank DB backup FAILED" email.** It names the date and step: `pg_dump` (the `db` container is down or unhealthy: `cd /opt/fintank && export IMAGE_TAG=$(cat .image-tag) && docker compose ps`), `dump size check` (empty dump), or `upload` (AWS credentials or bucket: `aws sts get-caller-identity` as `deploy`, check `~/.aws/credentials` and the backup bucket name in `.env`). Details are in `tail -n 50 /var/log/fintank-backup.log`. Fix, then rerun `/opt/fintank/backup_db.sh` to confirm. If you get no email at all for a day, check the log and `crontab -l` as `deploy`, and that you confirmed the SNS email subscription.

**Locked out of SSH.** The `ubuntu` user still works with the Lightsail default key. As a last resort, use the Lightsail console's browser SSH (instance, **Connect**).

## Stopping and deleting

If you stop here, billing continues until you delete things. Lightsail console: instance `fintank`, three-dot menu, **Delete**; **Networking**, static IP `fintank-ip`, **Delete** (an unattached static IP is also billed); delete the Route 53 hosted zone (about 0.50 USD/month); delete the S3 backup bucket if you want it gone (empty it first). Snapshots, if you made any, are separate: delete them too.
