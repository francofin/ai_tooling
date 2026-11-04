#!/usr/bin/env bash
# Usage: deploy.sh <image-tag>   (run on the server; files live in /opt/fintank)
#
# Pulls the app images, starts db and redis, migrates, starts everything, then
# requires api and web healthy and the worker running without restarts before
# recording the tag in .image-tag. If the new version fails that, the previous
# tag (if any) is redeployed and the script exits 1. The tag being attempted is
# written to .image-tag-attempt first, so a failed first deploy can be inspected.
#
# Only web, api and worker are pulled. db, redis and caddy use floating tags, and
# pulling a newer image would make `up -d` recreate them: a Postgres restart and
# an empty Redis on an ordinary deploy. README.md says how to move them on purpose.
#
# After a good deploy, images unused for a week are pruned. The previous tag's
# images are pinned first (see pin_previous_images) so a rollback never needs the
# registry. A failed prune does not fail the deploy.
#
# Migrations are NOT rolled back. A rollback redeploys old code against the
# already-migrated database, so migrations must stay backward compatible.
#
# Environment overrides (used by smoke.sh):
#   COMPOSE_FILE, COMPOSE_PROJECT_NAME  standard Compose variables
#   DEPLOY_SKIP_PULL=1                  skip `compose pull` (no registry)
#   DEPLOY_SKIP_PRUNE=1                 skip pruning (not on a developer's machine)
#   IMAGE_TAG_FILE                      where the deployed tag is recorded
#   DEPLOY_HEALTH_TIMEOUT               seconds to wait for api and web health (120)
#   DEPLOY_WORKER_SETTLE                seconds the worker must then stay up (15)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

TAG="${1:-}"
if [ -z "$TAG" ]; then
  echo "usage: $0 <image-tag>" >&2
  exit 2
fi

STATE_FILE="${IMAGE_TAG_FILE:-$DIR/.image-tag}"
ATTEMPT_FILE="$STATE_FILE-attempt"
TIMEOUT="${DEPLOY_HEALTH_TIMEOUT:-120}"
WORKER_SETTLE="${DEPLOY_WORKER_SETTLE:-15}"

PREV=""
if [ -f "$STATE_FILE" ]; then
  PREV="$(tr -d '[:space:]' < "$STATE_FILE")"
fi

compose() { docker compose "$@"; }

# wait_for_healthy <service...>: all of them healthy within TIMEOUT seconds.
wait_for_healthy() {
  local deadline=$((SECONDS + TIMEOUT)) service cid status waiting
  while :; do
    waiting=""
    for service in "$@"; do
      status=""
      cid="$(compose ps -q "$service" 2>/dev/null || true)"
      if [ -n "$cid" ]; then
        status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || true)"
      fi
      [ "$status" = "healthy" ] || waiting="$waiting $service"
    done
    [ -z "$waiting" ] && return 0
    if [ "$SECONDS" -ge "$deadline" ]; then
      echo "not healthy after ${TIMEOUT}s:$waiting" >&2
      return 1
    fi
    sleep 3
  done
}

# Prints "<running> <restarting> <restart count>". -a: a crashed worker still counts.
worker_state() {
  local cid
  cid="$(compose ps -aq worker 2>/dev/null || true)"
  [ -n "$cid" ] || return 1
  docker inspect -f '{{.State.Running}} {{.State.Restarting}} {{.RestartCount}}' "$cid" 2>/dev/null
}

# True if api and web get healthy and the worker stays up. The worker has no
# health check, so "up" means running with no restart since just after `up -d`:
# the restart policy would otherwise hide a crash loop. Comparing counts rather
# than expecting 0 covers an unchanged container kept by a redeploy of one tag.
release_is_up() {
  local before after
  before="$(worker_state)" || { echo "worker container not found" >&2; return 1; }
  wait_for_healthy api web || return 1
  sleep "$WORKER_SETTLE"
  after="$(worker_state)" || { echo "worker container not found" >&2; return 1; }
  if [ "$after" != "true false ${before##* }" ]; then
    echo "worker is not stable (was: $before, now: $after)" >&2
    return 1
  fi
}

rollback() {
  if [ -z "$PREV" ]; then
    echo "deploy of $TAG failed and there is no previous tag; leaving things as they are" >&2
    exit 1
  fi
  echo "deploy of $TAG failed; redeploying previous tag $PREV" >&2
  if IMAGE_TAG="$PREV" compose up -d && release_is_up; then
    echo "rolled back to $PREV" >&2
  else
    echo "rollback to $PREV did not become healthy either" >&2
  fi
  exit 1
}

# `image prune -a` removes every image no container uses, and once this deploy
# succeeds no running container uses the previous tag's. A stopped container
# counts as using its image, so keep one per image for rollback. Never started.
pin_previous_images() {
  local service image name
  for service in web api; do
    image="$(IMAGE_TAG="$PREV" compose config --images "$service")" || return 1
    name="fintank-rollback-$service"
    docker rm -f "$name" >/dev/null 2>&1 || true
    docker create --name "$name" "$image" >/dev/null 2>&1 || return 1
  done
}

prune_old_images() {
  if [ "${DEPLOY_SKIP_PRUNE:-}" = "1" ]; then return 0; fi
  if [ -n "$PREV" ] && ! pin_previous_images; then
    echo "could not pin the images for $PREV, so not pruning" >&2
    return 0
  fi
  if ! docker image prune -af --filter until=168h >/dev/null; then
    echo "image prune failed; check disk space by hand" >&2
  fi
}

printf '%s\n' "$TAG" > "$ATTEMPT_FILE"

export IMAGE_TAG="$TAG"

if [ "${DEPLOY_SKIP_PULL:-}" != "1" ]; then
  compose pull web api worker
fi

# Databases must be healthy before migrating. A failure here changes nothing
# that is serving traffic, so it does not trigger a rollback.
compose up -d --wait db redis
compose run --rm api python manage.py migrate --noinput

if ! compose up -d; then
  rollback
fi
if ! release_is_up; then
  rollback
fi

printf '%s\n' "$TAG" > "$STATE_FILE"
echo "deployed $TAG"

prune_old_images
