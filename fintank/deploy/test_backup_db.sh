#!/usr/bin/env bash
# Tests for backup_db.sh using stub docker/aws/date on PATH. No real docker,
# aws or network. Run: bash deploy/test_backup_db.sh
set -uo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAILS=0
WORK="$(mktemp -d)"
trap '[ -n "${KEEP:-}" ] || rm -rf "$WORK"' EXIT

# new_case: fresh stub dir + log files; sets BIN and LOG.
new_case() {
  BIN="$WORK/bin-$1"; LOG="$WORK/log-$1"
  mkdir -p "$BIN"; : > "$LOG"
  cat > "$BIN/docker" <<STUB
#!/usr/bin/env bash
echo "docker \$*" >> "$LOG"
case "\${STUB_DUMP:-ok}" in
  ok) head -c 4096 /dev/zero ;;
  empty) printf 'tiny' ;;
  fail) head -c 4096 /dev/zero ; echo "pg_dump: secret-conn-detail" >&2; exit 1 ;;
esac
STUB
  cat > "$BIN/aws" <<STUB
#!/usr/bin/env bash
echo "aws \$*" >> "$LOG"
if [ "\$1 \$2" = "s3 cp" ] && [ "\${STUB_CP_FAIL:-}" = 1 ]; then exit 1; fi
if [ "\$1 \$2" = "sns publish" ] && [ "\${STUB_SNS_FAIL:-}" = 1 ]; then exit 1; fi
exit 0
STUB
  cat > "$BIN/date" <<'STUB'
#!/usr/bin/env bash
echo 20261104
STUB
  chmod +x "$BIN"/*
}

run_backup() { # run_backup <case-name>; extra env via caller
  PATH="$BIN:$PATH" BACKUP_BUCKET=test-bucket ALERT_TOPIC_ARN=arn:aws:sns:us-east-1:1:topic \
    BACKUP_ENV_FILE=/nonexistent bash "$DEPLOY_DIR/backup_db.sh" >"$WORK/out-$1" 2>&1
}

report() { # report <name> <ok:0|1> [detail]
  if [ "$2" -eq 0 ]; then echo "PASS  $1"; else echo "FAIL  $1${3:+ -- $3}"; FAILS=$((FAILS + 1)); fi
}

t_success_uploads_dated_key() {
  new_case s; STUB_DUMP=ok run_backup s; local rc=$?
  [ "$rc" -eq 0 ] || return 1
  grep -q 'aws s3 cp --sse AES256 --only-show-errors .* s3://test-bucket/postgres/fintank-20261104.dump' "$LOG" || return 1
  ! grep -q 'sns publish' "$LOG" || return 1
  grep -q 'docker compose exec -T db sh -c' "$LOG" || return 1
}

t_pg_dump_failure_alerts_and_uploads_nothing() {
  new_case f; STUB_DUMP=fail run_backup f; local rc=$?
  [ "$rc" -ne 0 ] || return 1
  ! grep -q 'aws s3 cp' "$LOG" || return 1
  grep -q 'aws sns publish' "$LOG" || return 1
  grep -q 'aws sns publish.*20261104.*step: pg_dump' "$LOG" || return 1
  ! grep -q 'secret-conn-detail' "$LOG" || return 1
}

t_empty_dump_alerts_and_uploads_nothing() {
  new_case e; STUB_DUMP=empty run_backup e; local rc=$?
  [ "$rc" -ne 0 ] || return 1
  ! grep -q 'aws s3 cp' "$LOG" || return 1
  grep -q 'aws sns publish' "$LOG" || return 1
}

t_upload_failure_alerts() {
  new_case u; STUB_DUMP=ok STUB_CP_FAIL=1 run_backup u; local rc=$?
  [ "$rc" -ne 0 ] || return 1
  grep -q 'aws s3 cp' "$LOG" || return 1
  grep -q 'aws sns publish' "$LOG" || return 1
}

t_alert_failure_still_exits_nonzero() {
  new_case a; STUB_DUMP=fail STUB_SNS_FAIL=1 run_backup a; local rc=$?
  [ "$rc" -ne 0 ] || return 1
  grep -qi 'publish.*failed\|failed.*publish' "$WORK/out-a" || return 1
}

t_missing_config_fails() {
  new_case m
  if PATH="$BIN:$PATH" BACKUP_ENV_FILE=/nonexistent env -u BACKUP_BUCKET -u ALERT_TOPIC_ARN \
    bash "$DEPLOY_DIR/backup_db.sh" >"$WORK/out-m" 2>&1; then return 1; fi
  ! grep -q 'aws s3 cp' "$LOG"
}

for t in success_uploads_dated_key pg_dump_failure_alerts_and_uploads_nothing \
         empty_dump_alerts_and_uploads_nothing upload_failure_alerts \
         alert_failure_still_exits_nonzero missing_config_fails; do
  "t_$t"; report "$t" $?
done

[ "$FAILS" -eq 0 ] || { echo "$FAILS case(s) failed"; exit 1; }
echo "all cases passed"
