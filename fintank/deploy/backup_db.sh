#!/usr/bin/env bash
# Nightly Postgres backup. Cron (host, 07:30 UTC):
#   30 7 * * * /opt/fintank/backup_db.sh >> /var/log/fintank-backup.log 2>&1
#
# Dumps the `db` Compose service with pg_dump -Fc, checks the dump is not
# empty, and uploads it (server-side encrypted) to
# s3://$BACKUP_BUCKET/postgres/fintank-YYYYMMDD.dump. A rerun on the same UTC
# date overwrites that date's key, but only after the checks pass; on any
# failure nothing is uploaded and an SNS alert (date + failing step only, never
# error output) goes to $ALERT_TOPIC_ARN. Exits non-zero on any failure.
#
# BACKUP_BUCKET and ALERT_TOPIC_ARN come from the environment, or else from
# the .env next to the compose file (only those keys are read; the file is
# never sourced). BACKUP_ENV_FILE overrides the .env path.
#
# BACKUP_HEARTBEAT_URL (optional, same sources) is pinged after a successful
# upload, for a dead-man's switch that alerts when this script stops running at
# all. A failed ping is noted in the log and does not fail the backup.
set -euo pipefail

# Cron has a minimal PATH; append the standard dirs (existing entries win).
export PATH="${PATH:+$PATH:}/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
umask 077

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

ENV_FILE="${BACKUP_ENV_FILE:-$DIR/.env}"
read_env_key() { # read_env_key <KEY>: print the value from the env file, if any
  [ -f "$ENV_FILE" ] || return 0
  sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1 | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/"
}
if [ -z "${BACKUP_BUCKET:-}" ]; then BACKUP_BUCKET="$(read_env_key BACKUP_BUCKET)"; fi
if [ -z "${ALERT_TOPIC_ARN:-}" ]; then ALERT_TOPIC_ARN="$(read_env_key ALERT_TOPIC_ARN)"; fi
if [ -z "${BACKUP_HEARTBEAT_URL:-}" ]; then BACKUP_HEARTBEAT_URL="$(read_env_key BACKUP_HEARTBEAT_URL)"; fi
: "${BACKUP_BUCKET:?BACKUP_BUCKET is required}"
: "${ALERT_TOPIC_ARN:?ALERT_TOPIC_ARN is required}"

# Compose requires IMAGE_TAG to interpolate the file; use the deployed tag.
if [ -z "${IMAGE_TAG:-}" ]; then
  TAG_FILE="${IMAGE_TAG_FILE:-$DIR/.image-tag}"
  IMAGE_TAG=unknown
  if [ -r "$TAG_FILE" ]; then IMAGE_TAG="$(tr -d '[:space:]' < "$TAG_FILE")"; fi
  export IMAGE_TAG
fi

DATE="$(date -u +%Y%m%d)"
KEY="postgres/fintank-$DATE.dump"
TMPFILE="$(mktemp "${TMPDIR:-/tmp}/fintank-backup.XXXXXX")"
trap 'rm -f "$TMPFILE"' EXIT

# fail <step>: alert with the date and step only, then exit non-zero.
fail() {
  echo "backup $DATE FAILED at step: $1" >&2
  if ! aws sns publish --topic-arn "$ALERT_TOPIC_ARN" \
      --subject "Fintank DB backup FAILED" \
      --message "Fintank database backup for $DATE failed at step: $1" >/dev/null 2>&1; then
    echo "publishing the failure alert also failed" >&2
  fi
  exit 1
}

# -T keeps the binary stream clean. User and DB are resolved inside the
# container; no password is passed or printed.
if ! docker compose exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$TMPFILE"; then
  fail "pg_dump"
fi

SIZE="$(wc -c < "$TMPFILE")"
if [ "$SIZE" -lt 1024 ]; then
  fail "dump size check (under 1 KB)"
fi

if ! aws s3 cp --sse AES256 --only-show-errors "$TMPFILE" "s3://$BACKUP_BUCKET/$KEY"; then
  fail "upload"
fi

echo "backup $DATE ok: s3://$BACKUP_BUCKET/$KEY ($SIZE bytes)"

# Output discarded: the URL is enough to fake a good backup, so keep it out of logs.
if [ -n "$BACKUP_HEARTBEAT_URL" ]; then
  if ! curl -fsS --max-time 15 --retry 2 -o /dev/null "$BACKUP_HEARTBEAT_URL" >/dev/null 2>&1; then
    echo "backup $DATE: heartbeat ping failed (the backup itself succeeded)" >&2
  fi
fi
