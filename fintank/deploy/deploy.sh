#!/usr/bin/env bash
# Usage: deploy.sh <image-tag>   (run on the server; files live in /opt/fintank)
#
# Pulls the images, starts db and redis, migrates, starts everything, waits for
# the api health check, and records the tag in .image-tag. If the new version
# does not become healthy, the previous tag (if any) is redeployed and the
# script exits 1.
#
# Migrations are NOT rolled back. A rollback redeploys old code against the
# already-migrated database, so migrations must stay backward compatible.
#
# Environment overrides (used by smoke.sh):
#   COMPOSE_FILE, COMPOSE_PROJECT_NAME  standard Compose variables
#   DEPLOY_SKIP_PULL=1                  skip `compose pull` (no registry)
#   IMAGE_TAG_FILE                      where the deployed tag is recorded
#   DEPLOY_HEALTH_TIMEOUT               seconds to wait for api health (120)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

TAG="${1:-}"
if [ -z "$TAG" ]; then
  echo "usage: $0 <image-tag>" >&2
  exit 2
fi

STATE_FILE="${IMAGE_TAG_FILE:-$DIR/.image-tag}"
TIMEOUT="${DEPLOY_HEALTH_TIMEOUT:-120}"

PREV=""
if [ -f "$STATE_FILE" ]; then
  PREV="$(tr -d '[:space:]' < "$STATE_FILE")"
fi

compose() { docker compose "$@"; }

wait_for_api() {
  local deadline=$((SECONDS + TIMEOUT)) cid status
  while [ "$SECONDS" -lt "$deadline" ]; do
    cid="$(compose ps -q api 2>/dev/null || true)"
    if [ -n "$cid" ]; then
      status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || true)"
      [ "$status" = "healthy" ] && return 0
    fi
    sleep 3
  done
  return 1
}

rollback() {
  if [ -z "$PREV" ]; then
    echo "deploy of $TAG failed and there is no previous tag; leaving things as they are" >&2
    exit 1
  fi
  echo "deploy of $TAG failed; redeploying previous tag $PREV" >&2
  if IMAGE_TAG="$PREV" compose up -d && wait_for_api; then
    echo "rolled back to $PREV" >&2
  else
    echo "rollback to $PREV did not become healthy either" >&2
  fi
  exit 1
}

export IMAGE_TAG="$TAG"

if [ "${DEPLOY_SKIP_PULL:-}" != "1" ]; then
  compose pull
fi

# Databases must be healthy before migrating. A failure here changes nothing
# that is serving traffic, so it does not trigger a rollback.
compose up -d --wait db redis
compose run --rm api python manage.py migrate --noinput

if ! compose up -d; then
  rollback
fi
if ! wait_for_api; then
  rollback
fi

printf '%s\n' "$TAG" > "$STATE_FILE"
echo "deployed $TAG"
