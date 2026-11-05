#!/usr/bin/env bash
# One-time (and safe to rerun) server setup for a fresh Lightsail Ubuntu LTS box.
#
# Run it as the default `ubuntu` user:
#   sudo DEPLOY_PUBKEY="$(cat deploy_key.pub)" bash bootstrap_server.sh
#
# It installs Docker + Compose, AWS CLI, unattended-upgrades and fail2ban, adds
# 2 GB swap, creates the `deploy` user (docker group) and /opt/fintank, installs
# the nightly backup and disk check cron entries, and hardens SSH (key-only, no root login).
#
# Lock-out protection: SSH hardening is skipped (with a warning) unless `deploy`
# already has a non-empty authorized_keys, and the new config is checked with
# `sshd -t` before sshd is reloaded. Rerun after adding the key to finish.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root: sudo bash $0" >&2
  exit 1
fi

DEPLOY_USER=deploy
APP_DIR=/opt/fintank
BACKUP_LOG=/var/log/fintank-backup.log
CRON_LINE="30 7 * * * $APP_DIR/backup_db.sh >> $BACKUP_LOG 2>&1"
DISK_CRON_LINE="15 7 * * * $APP_DIR/check_disk.sh >> $BACKUP_LOG 2>&1"
export DEBIAN_FRONTEND=noninteractive

echo "== packages"
apt-get update -y
apt-get install -y ca-certificates curl gnupg unzip unattended-upgrades fail2ban cron

echo "== docker"
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  # shellcheck disable=SC1091
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

echo "== aws cli"
if ! command -v aws >/dev/null 2>&1; then
  case "$(uname -m)" in
    x86_64) AWS_ZIP=awscli-exe-linux-x86_64.zip ;;
    aarch64) AWS_ZIP=awscli-exe-linux-aarch64.zip ;;
    *) echo "unsupported CPU: $(uname -m)" >&2; exit 1 ;;
  esac
  TMP="$(mktemp -d)"
  curl -fsSL "https://awscli.amazonaws.com/$AWS_ZIP" -o "$TMP/awscliv2.zip"
  unzip -q "$TMP/awscliv2.zip" -d "$TMP"
  "$TMP/aws/install"
  rm -rf "$TMP"
fi

echo "== swap (2 GB)"
if ! swapon --show=NAME --noheadings | grep -q '^/swapfile$'; then
  if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
  fi
  swapon /swapfile
fi
grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab

echo "== unattended-upgrades"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
CONF
systemctl enable --now unattended-upgrades

echo "== deploy user and $APP_DIR"
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"
DEPLOY_HOME="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$DEPLOY_HOME/.ssh"
AUTH="$DEPLOY_HOME/.ssh/authorized_keys"
touch "$AUTH"
chown "$DEPLOY_USER:$DEPLOY_USER" "$AUTH"
chmod 600 "$AUTH"
if [ -n "${DEPLOY_PUBKEY:-}" ] && ! grep -qxF "$DEPLOY_PUBKEY" "$AUTH"; then
  printf '%s\n' "$DEPLOY_PUBKEY" >> "$AUTH"
fi
install -d -m 755 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR"

echo "== backup log and cron"
touch "$BACKUP_LOG"
chown "$DEPLOY_USER:$DEPLOY_USER" "$BACKUP_LOG"
chmod 640 "$BACKUP_LOG"
EXISTING="$(crontab -u "$DEPLOY_USER" -l 2>/dev/null || true)"
if ! printf '%s\n' "$EXISTING" | grep -qF "$APP_DIR/backup_db.sh"; then
  { printf '%s\n' "$EXISTING" | sed '/^$/d'; echo "$CRON_LINE"; } | crontab -u "$DEPLOY_USER" -
fi
EXISTING="$(crontab -u "$DEPLOY_USER" -l 2>/dev/null || true)"
if ! printf '%s\n' "$EXISTING" | grep -qF "$APP_DIR/check_disk.sh"; then
  { printf '%s\n' "$EXISTING" | sed '/^$/d'; echo "$DISK_CRON_LINE"; } | crontab -u "$DEPLOY_USER" -
fi

echo "== fail2ban"
systemctl enable --now fail2ban

echo "== ssh hardening"
if [ -s "$AUTH" ]; then
  # 00- sorts first, and sshd uses the first value it sees, so this wins over
  # cloud-init's 50-cloud-init.conf.
  CONF=/etc/ssh/sshd_config.d/00-fintank-hardening.conf
  cat > "$CONF" <<'CONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
CONF
  if sshd -t; then
    systemctl reload ssh 2>/dev/null || systemctl reload sshd
    echo "ssh: password and root login disabled"
  else
    rm -f "$CONF"
    echo "ssh: sshd -t rejected the config; hardening NOT applied" >&2
    exit 1
  fi
else
  echo "WARNING: $AUTH is empty, so SSH hardening was SKIPPED to avoid a lock-out." >&2
  echo "Add the deploy public key (DEPLOY_PUBKEY=...) and rerun this script." >&2
fi

echo "== done"
echo "Next: copy env.example to $APP_DIR/.env (mode 600), then docker login ghcr.io as $DEPLOY_USER."
