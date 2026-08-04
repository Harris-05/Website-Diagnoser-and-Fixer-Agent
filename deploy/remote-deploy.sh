#!/usr/bin/env bash
#
# Runs ON the EC2 instance, invoked over SSH by .github/workflows/deploy.yml.
#
# Kept as a script on the server rather than a pile of inline SSH commands so
# that the workflow stays readable, and so a deploy can be run by hand the
# same way CI runs it:
#
#     ssh ubuntu@<ip> 'sudo bash /opt/sitedoctor/deploy/remote-deploy.sh'

set -euo pipefail

APP_DIR="/opt/sitedoctor"
BRANCH="${DEPLOY_BRANCH:-test}"
RUN_USER="ubuntu"

log() { echo "==> $*"; }

if [[ $EUID -ne 0 ]]; then
  echo "needs sudo (it installs systemd units and reloads services)" >&2
  exit 1
fi

cd "$APP_DIR"

# Record where we were, so a bad deploy can be rolled back to a known commit.
PREVIOUS="$(git rev-parse HEAD)"
log "current commit $PREVIOUS"

log "fetching $BRANCH"
sudo -u "$RUN_USER" git fetch --depth 20 origin "$BRANCH"
sudo -u "$RUN_USER" git checkout -q "$BRANCH"
sudo -u "$RUN_USER" git reset --hard "origin/$BRANCH"
NEW="$(git rev-parse HEAD)"
log "now at $NEW"

if [[ "$PREVIOUS" == "$NEW" ]]; then
  log "no new commits, but continuing so dependency changes still apply"
fi

# Only reinstall when the dependency list actually changed. pip is slow on a
# 2 vCPU box and this runs on every push.
if ! git diff --quiet "$PREVIOUS" "$NEW" -- site-doctor/requirements.txt; then
  log "requirements.txt changed -- reinstalling"
  sudo -u "$RUN_USER" "$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/site-doctor/requirements.txt"
  sudo -u "$RUN_USER" "$APP_DIR/venv/bin/playwright" install chromium
else
  log "requirements.txt unchanged -- skipping pip"
fi

log "refreshing the status page"
install -m 644 -o "$RUN_USER" -g "$RUN_USER" "$APP_DIR/deploy/index.html" /var/www/sitedoctor/index.html

log "refreshing systemd units"
install -m 644 "$APP_DIR/deploy/sitedoctor-audit.service" /etc/systemd/system/
install -m 644 "$APP_DIR/deploy/sitedoctor-audit.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sitedoctor-audit.timer

# Preserve the live Caddyfile's first line, which holds the hostname once DNS
# is configured. Copying the repo version verbatim would silently revert an
# HTTPS site back to plain HTTP on :80.
log "Caddy configuration"
if [[ -f /etc/caddy/Caddyfile ]] && ! head -n 20 /etc/caddy/Caddyfile | grep -q '^:80 {'; then
  log "live Caddyfile has a hostname configured -- NOT overwriting it"
  log "    apply repo changes by hand if the repo Caddyfile changed"
else
  install -m 644 "$APP_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
  systemctl reload caddy || systemctl restart caddy
fi

# Restart the API only if it exists. Haris's FastAPI service is not built yet;
# once a sitedoctor-api.service is installed this picks it up with no change
# to this script.
if systemctl list-unit-files | grep -q '^sitedoctor-api.service'; then
  log "restarting sitedoctor-api"
  systemctl restart sitedoctor-api
else
  log "no sitedoctor-api.service yet -- skipping (expected until the API lands)"
fi

log "deployed $NEW"
log "rollback with: sudo -u $RUN_USER git -C $APP_DIR reset --hard $PREVIOUS && sudo bash $APP_DIR/deploy/remote-deploy.sh"
