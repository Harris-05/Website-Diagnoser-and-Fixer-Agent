#!/usr/bin/env bash
#
# One-time provisioning for the Site Doctor EC2 instance.
#
# Run ONCE as ubuntu on a fresh Ubuntu box:
#     sudo bash deploy/setup-ec2.sh
#
# Safe to re-run -- every step checks whether it already did its work.
# Deploys after this are handled by deploy/remote-deploy.sh, which the
# GitHub Actions workflow calls over SSH.
#
# Sized for a t3.micro: 908 MB RAM, 2 vCPU, ~17 GB free disk.

set -euo pipefail

REPO_URL="https://github.com/Harris-05/Website-Diagnoser-and-Fixer-Agent.git"
BRANCH="${DEPLOY_BRANCH:-test}"
APP_DIR="/opt/sitedoctor"
WEB_DIR="/var/www/sitedoctor"
ENV_FILE="/etc/sitedoctor/env"
RUN_USER="ubuntu"

log() { echo ""; echo "==> $*"; }

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash deploy/setup-ec2.sh" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 1. Swap -- not optional on this box.
#
# 908 MB total with ~580 MB free, and the app runs TWO browsers: Playwright's
# Chromium to crawl, then Lighthouse launching its own Chrome to audit.
# Without swap the kernel OOM-killer terminates one of them mid-run, which
# looks like a random intermittent bug rather than memory exhaustion.
# ---------------------------------------------------------------------------
log "Swap"
if swapon --show | grep -q '/swapfile'; then
  echo "already active"
else
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  # Prefer RAM, but allow swap under pressure rather than killing processes.
  sysctl -w vm.swappiness=10 >/dev/null
  grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
  echo "2 GB swap enabled"
fi

# ---------------------------------------------------------------------------
# 2. System packages
#
# Node comes from Ubuntu's own repository, not NodeSource: this box runs a
# very new Ubuntu, NodeSource may not publish for it yet, and the distro
# package is already well past Lighthouse's Node >= 18.20 requirement.
# ---------------------------------------------------------------------------
log "System packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  git python3 python3-venv python3-pip nodejs npm ca-certificates curl debian-keyring debian-archive-keyring apt-transport-https

node_major="$(node -v | sed 's/^v\([0-9]*\).*/\1/')"
echo "node $(node -v), python $(python3 --version)"
if (( node_major < 18 )); then
  echo "ERROR: Lighthouse needs Node >= 18.20, found $(node -v)" >&2
  exit 1
fi

log "Lighthouse CLI"
if command -v lighthouse >/dev/null; then
  echo "already installed: $(lighthouse --version)"
else
  npm install -g lighthouse --no-fund --no-audit
  echo "installed $(lighthouse --version)"
fi

# ---------------------------------------------------------------------------
# 3. Caddy -- reverse proxy and automatic HTTPS
#
# From Caddy's official repository, which publishes an "any-version" list and
# therefore works on Ubuntu releases too new to have their own codename there.
# ---------------------------------------------------------------------------
log "Caddy"
if command -v caddy >/dev/null; then
  echo "already installed: $(caddy version)"
else
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq
  apt-get install -y -qq caddy
  echo "installed $(caddy version)"
fi

# ---------------------------------------------------------------------------
# 4. Application checkout
# ---------------------------------------------------------------------------
log "Application source ($BRANCH)"
if [[ -d "$APP_DIR/.git" ]]; then
  echo "already cloned"
else
  git clone --branch "$BRANCH" --depth 20 "$REPO_URL" "$APP_DIR"
fi
chown -R "$RUN_USER:$RUN_USER" "$APP_DIR"

# ---------------------------------------------------------------------------
# 5. Python environment and browser
#
# Ubuntu marks the system Python as externally managed (PEP 668), so a venv
# is required, not just tidier.
# ---------------------------------------------------------------------------
log "Python virtualenv"
if [[ ! -x "$APP_DIR/venv/bin/python" ]]; then
  sudo -u "$RUN_USER" python3 -m venv "$APP_DIR/venv"
fi
sudo -u "$RUN_USER" "$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
sudo -u "$RUN_USER" "$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/site-doctor/requirements.txt"
echo "installed $(sudo -u "$RUN_USER" "$APP_DIR/venv/bin/pip" list 2>/dev/null | wc -l) packages"

log "Playwright Chromium"
# --with-deps asks apt for Chromium's system libraries. On an Ubuntu release
# Playwright does not recognise yet it can fail; the browser itself still
# installs, so fall back rather than aborting the whole provision.
if sudo -u "$RUN_USER" "$APP_DIR/venv/bin/playwright" install --with-deps chromium; then
  echo "installed with system dependencies"
else
  echo "WARNING: --with-deps failed (likely an unrecognised Ubuntu release)."
  echo "Installing the browser alone, then the known library set by hand."
  sudo -u "$RUN_USER" "$APP_DIR/venv/bin/playwright" install chromium
  apt-get install -y -qq --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2t64 || \
  apt-get install -y -qq --no-install-recommends libasound2 || true
fi

# ---------------------------------------------------------------------------
# 6. Runtime secrets
#
# NOT in git, NOT in the image, NOT a GitHub Secret -- GitHub Secrets are for
# CI. This file is read by systemd (as root) before it drops to the ubuntu
# user, so 600 root-only is both safe and sufficient.
#
# AWS Parameter Store is the better long-term answer and is noted as a
# follow-up in deploy/README.md; it needs an IAM role and the AWS CLI
# resident, which this 908 MB box would rather avoid for now.
# ---------------------------------------------------------------------------
log "Secrets file"
mkdir -p "$(dirname "$ENV_FILE")"
if [[ -f "$ENV_FILE" ]]; then
  echo "$ENV_FILE already exists -- leaving it alone"
else
  cat > "$ENV_FILE" <<'EOF'
# Site Doctor runtime configuration. Root-readable only. Never commit this.
OPENAI_API_KEY=replace-me
SITEDOCTOR_TARGET_URL=https://example.com
EOF
  echo "created $ENV_FILE -- EDIT IT before the first audit run"
fi
chmod 600 "$ENV_FILE"
chown root:root "$ENV_FILE"

# ---------------------------------------------------------------------------
# 7. Web root and systemd units
# ---------------------------------------------------------------------------
log "Web root"
mkdir -p "$WEB_DIR/reports"
install -m 644 "$APP_DIR/deploy/index.html" "$WEB_DIR/index.html"
chown -R "$RUN_USER:$RUN_USER" "$WEB_DIR"

log "systemd units"
install -m 644 "$APP_DIR/deploy/sitedoctor-audit.service" /etc/systemd/system/
install -m 644 "$APP_DIR/deploy/sitedoctor-audit.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sitedoctor-audit.timer
echo "audit timer enabled"

log "Caddy configuration"
install -m 644 "$APP_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
systemctl reload caddy || systemctl restart caddy
echo "caddy serving $WEB_DIR"

# ---------------------------------------------------------------------------
log "Done"
cat <<EOF

Next steps:
  1. Put the real OpenAI key and target URL in $ENV_FILE
         sudo nano $ENV_FILE
  2. Trigger one audit by hand to confirm the pipeline works:
         sudo systemctl start sitedoctor-audit.service
         journalctl -u sitedoctor-audit.service -f
  3. Visit http://<this-ip>/ -- you should see the status page.
  4. When DNS points here, put the hostname at the top of
     /etc/caddy/Caddyfile and run: sudo systemctl reload caddy
     Caddy then fetches a Let's Encrypt certificate automatically.

Memory check (two browsers on 908 MB is the main risk here):
     free -h
EOF
