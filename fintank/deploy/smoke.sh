#!/usr/bin/env bash
# shellcheck disable=SC2329  # the check functions are invoked through `check`/`retry`
# Local smoke test for the production stack. Run: sg docker -c 'bash deploy/smoke.sh'
#
# Needs fintank-api:test and fintank-web:test in the local image store. Brings
# up the real compose file plus docker-compose.smoke.yml under the project name
# fintank-smoke, with dummy secrets, Caddy on 127.0.0.1:18443 only, and always
# tears everything down (containers, volumes, smoke tags) on exit.
set -uo pipefail

# Total timeout so the run cannot hang.
if [ -z "${SMOKE_INNER:-}" ]; then
  SMOKE_INNER=1 exec timeout "${SMOKE_TIMEOUT:-1200}" bash "${BASH_SOURCE[0]}" "$@"
fi

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d)"
FAILS=0
PORT=18443

export COMPOSE_PROJECT_NAME=fintank-smoke
export COMPOSE_FILE="$DEPLOY_DIR/docker-compose.yml:$DEPLOY_DIR/docker-compose.smoke.yml"
export COMPOSE_ENV_FILES="$TMP/env"
export ENV_FILE="$TMP/env"
export IMAGE_TAG=smoke-good
export DEPLOY_SKIP_PULL=1
# Pruning here would delete unused images on the machine running the test.
export DEPLOY_SKIP_PRUNE=1
export IMAGE_TAG_FILE="$TMP/image-tag"
export DEPLOY_HEALTH_TIMEOUT=45

cleanup() {
  docker compose down -v --remove-orphans >/dev/null 2>&1
  docker rmi fintank-api:smoke-good fintank-api:smoke-bad fintank-api:smoke-badweb fintank-api:smoke-badworker \
    fintank-web:smoke-good fintank-web:smoke-bad fintank-web:smoke-badweb fintank-web:smoke-badworker >/dev/null 2>&1
  rm -rf "$TMP"
}
trap cleanup EXIT
trap 'exit 143' TERM INT

pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1${2:+ -- $2}"; FAILS=$((FAILS + 1)); }

# check <name> <command...>: PASS if the command exits 0.
check() {
  local name="$1"; shift
  local out
  if out="$("$@" 2>&1)"; then pass "$name"; else fail "$name" "$(printf '%s' "$out" | tail -n 3 | tr '\n' ' ')"; fi
}

# retry <seconds> <command...>
retry() {
  local deadline=$((SECONDS + $1)); shift
  until "$@"; do
    [ "$SECONDS" -ge "$deadline" ] && return 1
    sleep 3
  done
}

hcurl() { # hcurl <host> <path> [curl args...]
  local host="$1" path="$2"; shift 2
  curl -ksS --max-time 20 --resolve "$host:$PORT:127.0.0.1" "$@" "https://$host:$PORT$path"
}

# --- prerequisites -----------------------------------------------------------
for img in fintank-api:test fintank-web:test; do
  docker image inspect "$img" >/dev/null 2>&1 || { echo "missing local image $img; build it first" >&2; exit 1; }
done

docker tag fintank-api:test fintank-api:smoke-good
docker tag fintank-web:test fintank-web:smoke-good
docker tag fintank-web:test fintank-web:smoke-bad
# A "bad release": same image, but the default command exits 1, so the api never gets healthy.
printf 'FROM fintank-api:smoke-good\nCMD ["sh", "-c", "exit 1"]\n' | docker build -q -t fintank-api:smoke-bad - >/dev/null \
  || { echo "could not build the bad api image" >&2; exit 1; }
# A release whose site is down: api and worker fine, web exits at once.
docker tag fintank-api:test fintank-api:smoke-badweb
printf 'FROM fintank-web:smoke-good\nCMD ["sh", "-c", "exit 1"]\n' | docker build -q -t fintank-web:smoke-badweb - >/dev/null \
  || { echo "could not build the bad web image" >&2; exit 1; }
# A release whose worker crash-loops: api and web fine, only `celery` is broken.
docker tag fintank-web:test fintank-web:smoke-badworker
printf "FROM fintank-api:smoke-good\nUSER root\nRUN printf '#!/bin/sh\\\\nexit 1\\\\n' > /app/.venv/bin/celery\nUSER app\n" \
  | docker build -q -t fintank-api:smoke-badworker - >/dev/null \
  || { echo "could not build the bad worker image" >&2; exit 1; }

# --- dummy env (no real secrets, no AWS credentials) -------------------------
rnd() { head -c 24 /dev/urandom | base64 | tr -d '/+=\n'; }
cp "$DEPLOY_DIR/env.example" "$TMP/env"
cat >> "$TMP/env" <<ENVEOF
SITE_HOST=www.smoke.test
APEX_HOST=apex.smoke.test
API_HOST=api.smoke.test
CADDY_GLOBAL_OPTS=local_certs
ALLOWED_HOSTS=api.smoke.test,localhost
CORS_ALLOWED_ORIGINS=https://www.smoke.test
CSRF_TRUSTED_ORIGINS=https://www.smoke.test
FRONTEND_URL=https://www.smoke.test
SECRET_KEY=smoke-$(rnd)$(rnd)$(rnd)
DATABASE_PASSWORD=$(rnd)
AWS_BUCKET_NAME=smoke-unused-bucket
STRIPE_SECRET_KEY=sk_test_dummy
STRIPE_WEBHOOK_SECRET=whsec_dummy
STRIPE_PRICE_PRO_MONTHLY=price_dummy_m
STRIPE_PRICE_PRO_YEARLY=price_dummy_y
FMP_API=dummy
FMP_URL=https://fmp.invalid
FMP_CLOUD_DATA_BASE_URL=https://fmp.invalid
AZURE_BING_KEY=dummy
CLOUDINARY_CLOUD_NAME=dummy
CLOUDINARY_API_KEY=dummy
CLOUDINARY_SECRET_API=dummy
CLOUDINARY_URL=cloudinary://dummy:dummy@dummy
ENVEOF

# --- bring the stack up through the real deploy script -----------------------
echo "== deploying smoke-good"
if ! bash "$DEPLOY_DIR/deploy.sh" smoke-good; then
  echo "FAIL  initial deploy -- see output above"
  docker compose logs --tail 40 api 2>&1 | tail -n 40
  exit 1
fi
pass "initial deploy.sh smoke-good"

# --- checks ------------------------------------------------------------------
healthz_ok() {
  local body
  body="$(hcurl api.smoke.test /healthz/ -w '\n%{http_code}')" || return 1
  [[ "$body" == *'"db": true'* && "$body" == *'"redis": true'* && "$body" == *$'\n200' ]]
}
check "GET api /healthz/ -> 200, db and redis true" retry 60 healthz_ok

www_ok() { [ "$(hcurl www.smoke.test / -o /dev/null -w '%{http_code}')" = 200 ]; }
check "GET www / -> 200" retry 60 www_ok

web_healthy() { [ "$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q web)")" = healthy ]; }
check "web container reports healthy" web_healthy

www_headers() {
  local headers
  headers="$(hcurl www.smoke.test / -o /dev/null -D -)" || return 1
  grep -qi '^strict-transport-security: max-age=' <<<"$headers" || { echo "no HSTS"; return 1; }
  grep -qi '^x-frame-options: SAMEORIGIN' <<<"$headers" || { echo "no frame protection"; return 1; }
}
check "www sends HSTS and SAMEORIGIN frame protection" www_headers

apex_redirect() {
  local r
  r="$(hcurl apex.smoke.test /some/path?x=1 -o /dev/null -w '%{http_code} %{redirect_url}')" || return 1
  [[ "$r" =~ ^(301|308)\ https://www\.smoke\.test(:[0-9]+)?/some/path\?x=1$ ]] || { echo "$r"; return 1; }
}
check "GET apex -> 301/308 to www" apex_redirect

redis_policy() { docker compose exec -T redis redis-cli config get maxmemory-policy | grep -qx volatile-lru; }
check "redis maxmemory-policy = volatile-lru" redis_policy

redis_save_empty() { [ -z "$(docker compose exec -T redis redis-cli config get save | sed -n 2p | tr -d '\r')" ]; }
check "redis persistence disabled (save empty)" redis_save_empty

celery_ping() { docker compose exec -T worker celery -A fintank_backend inspect ping 2>&1 | grep -q pong; }
check "worker answers celery inspect ping" retry 60 celery_ping

check "manage.py check --deploy has no errors" \
  docker compose exec -T api python manage.py check --deploy

# COLD CACHE. No AWS credentials are passed to this stack, so S3-backed routes
# cannot return real data here and may answer 5xx; that is accepted. What this
# proves is only that an empty cache does not take the api down: it stays
# healthy and is not OOM-killed. The real cold-cache check against S3 data
# happens at go-live (Task 8).
cold_cache() {
  docker compose exec -T redis redis-cli flushall >/dev/null || return 1
  hcurl api.smoke.test /api/index-performance/ -o /dev/null -w '%{http_code}\n' || true
  hcurl www.smoke.test / -o /dev/null -w '%{http_code}\n' || true
  local cid
  cid="$(docker compose ps -q api)"
  [ "$(docker inspect -f '{{.State.OOMKilled}}' "$cid")" = false ] || { echo "api OOMKilled"; return 1; }
  [ "$(docker inspect -f '{{.State.Health.Status}}' "$cid")" = healthy ] || { echo "api not healthy"; return 1; }
  healthz_ok
}
check "cold cache: api healthy and not OOMKilled after Redis flush" cold_cache

# BACKUP RESTORE. Dumps the smoke database the same way backup_db.sh does,
# restores it into a scratch database in this smoke project's db, and compares
# the django_migrations row count. The scratch database is always dropped.
restore_check() {
  local want got rc=0
  want="$(docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select count(*) from django_migrations"' | tr -d '[:space:]')" || return 1
  [[ "$want" =~ ^[0-9]+$ && "$want" -gt 0 ]] || { echo "bad source count '$want'"; return 1; }
  docker compose exec -T db sh -c '
    set -e
    pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB" > /tmp/smoke-restore.dump
    dropdb -U "$POSTGRES_USER" --if-exists smoke_restore
    createdb -U "$POSTGRES_USER" smoke_restore
    pg_restore -U "$POSTGRES_USER" -d smoke_restore --no-owner /tmp/smoke-restore.dump
  ' || rc=1
  if [ "$rc" -eq 0 ]; then
    got="$(docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d smoke_restore -tAc "select count(*) from django_migrations"' | tr -d '[:space:]')" || rc=1
  fi
  docker compose exec -T db sh -c 'dropdb -U "$POSTGRES_USER" --if-exists smoke_restore; rm -f /tmp/smoke-restore.dump' >/dev/null 2>&1
  [ "$rc" -eq 0 ] || { echo "dump/restore failed"; return 1; }
  [ "$got" = "$want" ] || { echo "django_migrations: source $want, restored '$got'"; return 1; }
}
check "pg_dump restores into a scratch db with the same django_migrations count" restore_check

# DEPLOY ROLLBACK. Runs last because it replaces the containers.
rollback_case() { # rollback_case <bad-tag>
  local rc cid
  bash "$DEPLOY_DIR/deploy.sh" "$1" >"$TMP/rollback.log" 2>&1
  rc=$?
  [ "$rc" -eq 1 ] || { echo "deploy.sh exit code $rc, expected 1"; tail -n 5 "$TMP/rollback.log"; return 1; }
  [ "$(cat "$IMAGE_TAG_FILE")" = smoke-good ] || { echo ".image-tag changed"; return 1; }
  [ "$(cat "$IMAGE_TAG_FILE-attempt")" = "$1" ] || { echo ".image-tag-attempt not recorded"; return 1; }
  grep -q 'rolled back to smoke-good' "$TMP/rollback.log" || { echo "rollback did not finish"; tail -n 5 "$TMP/rollback.log"; return 1; }
  cid="$(docker compose ps -q api)"
  [ "$(docker inspect -f '{{.Config.Image}}' "$cid")" = fintank-api:smoke-good ] || { echo "api is not on smoke-good"; return 1; }
  [ "$(docker inspect -f '{{.State.Health.Status}}' "$cid")" = healthy ] || { echo "api not healthy after rollback"; return 1; }
  healthz_ok
}
check "deploy.sh with a failing api exits 1 and the previous tag stays up" rollback_case smoke-bad
check "deploy.sh with a failing web exits 1 and the previous tag stays up" rollback_case smoke-badweb
check "deploy.sh with a crash-looping worker exits 1 and the previous tag stays up" rollback_case smoke-badworker

echo
if [ "$FAILS" -eq 0 ]; then echo "SMOKE: all checks passed"; exit 0; fi
echo "SMOKE: $FAILS check(s) failed"
exit 1
