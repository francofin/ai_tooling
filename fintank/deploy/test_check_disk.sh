#!/usr/bin/env bash
# Tests for check_disk.sh using stub df/aws on PATH. No real aws or network.
# Run: bash deploy/test_check_disk.sh
set -uo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAILS=0
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
LOG="$WORK/log"

cat > "$WORK/df" <<'STUB'
#!/usr/bin/env bash
printf 'Use%%\n %s%%\n' "$STUB_USED"
STUB
cat > "$WORK/aws" <<STUB
#!/usr/bin/env bash
echo "aws \$*" >> "$LOG"
[ "\${STUB_SNS_FAIL:-}" != 1 ]
STUB
chmod +x "$WORK/df" "$WORK/aws"

run() { : > "$LOG"; PATH="$WORK:$PATH" BACKUP_ENV_FILE="${ENV_FILE_UNDER_TEST:-/nonexistent}" bash "$DEPLOY_DIR/check_disk.sh" >/dev/null 2>&1; }
report() { if [ "$2" -eq 0 ]; then echo "PASS  $1"; else echo "FAIL  $1"; FAILS=$((FAILS + 1)); fi; }

t_below_limit_is_quiet() { STUB_USED=85 ALERT_TOPIC_ARN=arn:topic run || return 1; [ ! -s "$LOG" ]; }
t_over_limit_alerts() { STUB_USED=86 ALERT_TOPIC_ARN=arn:topic run || return 1; grep -q 'sns publish --topic-arn arn:topic .*86%' "$LOG"; }
t_limit_can_be_set() { STUB_USED=50 DISK_ALERT_PERCENT=40 ALERT_TOPIC_ARN=arn:topic run || return 1; grep -q 'sns publish' "$LOG"; }
t_topic_read_from_env_file() {
  printf 'SECRET_KEY=not-read\nALERT_TOPIC_ARN=arn:from-file\n' > "$WORK/env"
  STUB_USED=90 ENV_FILE_UNDER_TEST="$WORK/env" run || return 1
  grep -q 'arn:from-file' "$LOG" && ! grep -q 'not-read' "$LOG"
}
t_failed_alert_fails_the_script() { ! STUB_USED=90 STUB_SNS_FAIL=1 ALERT_TOPIC_ARN=arn:topic run; }
t_missing_topic_fails() { ! STUB_USED=10 run; }

for t in below_limit_is_quiet over_limit_alerts limit_can_be_set topic_read_from_env_file \
         failed_alert_fails_the_script missing_topic_fails; do
  "t_$t"; report "$t" $?
done

[ "$FAILS" -eq 0 ] || { echo "$FAILS case(s) failed"; exit 1; }
echo "all cases passed"
