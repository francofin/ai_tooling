#!/usr/bin/env bash
# Daily disk check. Cron (host, 07:15 UTC, installed by bootstrap_server.sh):
#   15 7 * * * /opt/fintank/check_disk.sh >> /var/log/fintank-backup.log 2>&1
#
# Publishes to $ALERT_TOPIC_ARN when the root disk, which holds Docker's images
# and the database, is over DISK_ALERT_PERCENT (default 85). ALERT_TOPIC_ARN comes
# from the environment or the .env next to this file; only that key is read.
set -euo pipefail

# Cron has a minimal PATH; append the standard dirs (existing entries win).
export PATH="${PATH:+$PATH:}/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${BACKUP_ENV_FILE:-$DIR/.env}"
LIMIT="${DISK_ALERT_PERCENT:-85}"

if [ -z "${ALERT_TOPIC_ARN:-}" ] && [ -f "$ENV_FILE" ]; then
  ALERT_TOPIC_ARN="$(sed -n 's/^ALERT_TOPIC_ARN=//p' "$ENV_FILE" | tail -n 1)"
fi
: "${ALERT_TOPIC_ARN:?ALERT_TOPIC_ARN is required}"

USED="$(df --output=pcent / | tail -n 1 | tr -dc '0-9')"
if [ "$USED" -gt "$LIMIT" ]; then
  echo "disk at ${USED}% (limit ${LIMIT}%): alerting"
  aws sns publish --topic-arn "$ALERT_TOPIC_ARN" \
    --subject "Fintank disk ${USED}% full" \
    --message "The Fintank server's root disk is ${USED}% full (limit ${LIMIT}%). See Troubleshooting in deploy/README.md." \
    >/dev/null
fi
