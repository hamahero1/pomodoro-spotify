#!/usr/bin/env bash
#
# Robust, re-runnable deployment script for Pomodoro Spotify on a fresh
# Ubuntu Lightsail instance. Safe to run more than once — every step
# checks its own state first instead of blindly redoing work.
#
# Usage (run ON THE SERVER, from anywhere):
#   ./deploy.sh yourdomain.com
#   ./deploy.sh --sslip                 # no domain yet? auto-detects the
#                                        # server's public IP and uses
#                                        # <ip>.sslip.io — no signup needed
#
# Optional env vars (skip the interactive prompts, e.g. for automation):
#   SPOTIFY_CLIENT_ID=... SPOTIFY_CLIENT_SECRET=... ./deploy.sh yourdomain.com
#
# What it does, in order, each step checked/validated before moving on:
#   1. Installs system packages (python3, nginx, certbot, git)
#   2. Clones the repo (or pulls latest if already cloned)
#   3. Creates/reuses a venv, installs Python deps
#   4. Runs the test suite — aborts the deploy if anything fails
#   5. Writes .env (generates a real SECRET_KEY, prompts for Spotify
#      credentials only if not already set), without ever overwriting an
#      existing .env's real values
#   6. Installs + starts the systemd service (Gunicorn), verifies it's
#      actually running
#   7. Installs the Nginx site config, validates it with `nginx -t`
#      BEFORE reloading (never reloads a broken config)
#   8. Requests a free HTTPS certificate via certbot (skipped if one
#      already exists for this domain)
#   9. Does a final end-to-end curl check against the live HTTPS URL

set -euo pipefail

# ---------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------
DOMAIN="${1:-}"
if [[ "$DOMAIN" == "--sslip" ]]; then
  echo "==> Detecting public IP for sslip.io fallback domain..."
  PUBLIC_IP="$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')"
  if [[ -z "$PUBLIC_IP" ]]; then
    echo "ERROR: Could not auto-detect this server's public IP. Pass a domain explicitly instead: ./deploy.sh yourdomain.com" >&2
    exit 1
  fi
  DOMAIN="${PUBLIC_IP}.sslip.io"
  echo "    Using $DOMAIN"
fi
if [[ -z "$DOMAIN" ]]; then
  echo "Usage: $0 <your-domain> | --sslip" >&2
  exit 1
fi

APP_DIR="$HOME/pomodoro-spotify"
REPO_URL="https://github.com/hamahero1/pomodoro-spotify.git"
SERVICE_NAME="pomodoro-spotify"
RUN_USER="$(whoami)"

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
step() { echo; echo "==> $*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

trap 'echo; echo "❌ Deploy failed at line $LINENO. Nothing after this point ran. Safe to fix the issue and re-run ./deploy.sh $DOMAIN — earlier steps will just be skipped/reused." >&2' ERR

if [[ "$RUN_USER" == "root" ]]; then
  fail "Don't run this as root — run it as your normal user (e.g. ubuntu); it uses sudo internally only where needed."
fi
command -v sudo >/dev/null || fail "sudo is required but not found."

# ---------------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------------
step "Installing system packages"
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-venv python3-pip git nginx certbot python3-certbot-nginx curl >/dev/null
python3 --version
nginx -v

# ---------------------------------------------------------------------
# 2. Get the code
# ---------------------------------------------------------------------
step "Fetching the app"
if [[ -d "$APP_DIR/.git" ]]; then
  echo "    Already cloned — pulling latest instead."
  git -C "$APP_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# ---------------------------------------------------------------------
# 3. Python environment
# ---------------------------------------------------------------------
step "Setting up the Python virtual environment"
if [[ ! -d venv ]]; then
  python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "    $(python --version), $(pip --version | cut -d' ' -f1-2)"

# ---------------------------------------------------------------------
# 4. Test suite — refuse to deploy broken code
# ---------------------------------------------------------------------
step "Running the test suite (deploy aborts here if anything fails)"
pytest -q

# ---------------------------------------------------------------------
# 5. .env — create if missing, never clobber an existing one
# ---------------------------------------------------------------------
step "Checking .env"
REDIRECT_URI="https://${DOMAIN}/spotify/callback"

if [[ ! -f .env ]]; then
  echo "    No .env yet — creating one."
  cp .env.example .env
  SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"

  if [[ -z "${SPOTIFY_CLIENT_ID:-}" ]]; then
    read -rp "    Spotify Client ID: " SPOTIFY_CLIENT_ID
  fi
  if [[ -z "${SPOTIFY_CLIENT_SECRET:-}" ]]; then
    read -rsp "    Spotify Client Secret: " SPOTIFY_CLIENT_SECRET
    echo
  fi
  [[ -n "$SPOTIFY_CLIENT_ID" ]] || fail "Spotify Client ID is required."
  [[ -n "$SPOTIFY_CLIENT_SECRET" ]] || fail "Spotify Client Secret is required."

  # sed -i differs between GNU/BSD; this is the GNU form (Ubuntu default).
  sed -i \
    -e "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|" \
    -e "s|^FLASK_ENV=.*|FLASK_ENV=production|" \
    -e "s|^FLASK_DEBUG=.*|FLASK_DEBUG=0|" \
    -e "s|^SPOTIFY_CLIENT_ID=.*|SPOTIFY_CLIENT_ID=${SPOTIFY_CLIENT_ID}|" \
    -e "s|^SPOTIFY_CLIENT_SECRET=.*|SPOTIFY_CLIENT_SECRET=${SPOTIFY_CLIENT_SECRET}|" \
    -e "s|^SPOTIFY_REDIRECT_URI=.*|SPOTIFY_REDIRECT_URI=${REDIRECT_URI}|" \
    .env
  echo "    .env written."
else
  echo "    .env already exists — leaving your values as-is."
  if grep -q "your-spotify-client-id\|your-spotify-client-secret\|change-me-to-a-random-secret" .env; then
    fail ".env still has placeholder values (e.g. 'your-spotify-client-id'). Edit it manually: nano .env"
  fi
  CURRENT_REDIRECT="$(grep '^SPOTIFY_REDIRECT_URI=' .env | cut -d= -f2-)"
  if [[ "$CURRENT_REDIRECT" != "$REDIRECT_URI" ]]; then
    echo "    WARNING: .env's SPOTIFY_REDIRECT_URI ($CURRENT_REDIRECT) doesn't match this domain's ($REDIRECT_URI)."
    echo "    Update it manually if that's not intentional, and match it in the Spotify dashboard too."
  fi
fi

# ---------------------------------------------------------------------
# 6. systemd service
# ---------------------------------------------------------------------
step "Installing the systemd service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
sed \
  -e "s|^User=.*|User=${RUN_USER}|" \
  -e "s|^Group=.*|Group=${RUN_USER}|" \
  -e "s|WorkingDirectory=.*|WorkingDirectory=${APP_DIR}|" \
  -e "s|Environment=PATH=.*|Environment=PATH=${APP_DIR}/venv/bin|" \
  -e "s|ExecStart=/home/ubuntu/pomodoro-spotify/venv/bin/gunicorn|ExecStart=${APP_DIR}/venv/bin/gunicorn|" \
  deploy/pomodoro-spotify.service | sudo tee "$SERVICE_FILE" >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

sleep 2
if ! sudo systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "    Service failed to start. Last 30 log lines:"
  sudo journalctl -u "$SERVICE_NAME" -n 30 --no-pager
  fail "$SERVICE_NAME did not start — see log above."
fi
echo "    $SERVICE_NAME is active."

# ---------------------------------------------------------------------
# 7. Nginx
# ---------------------------------------------------------------------
step "Configuring Nginx for $DOMAIN"
NGINX_SITE="/etc/nginx/sites-available/${SERVICE_NAME}"
if [[ -f "$NGINX_SITE" ]] && sudo grep -q "listen 443" "$NGINX_SITE" 2>/dev/null; then
  # certbot's --nginx plugin edits this file in place to add the HTTPS
  # server block + redirect. Re-writing it from the plain-HTTP template
  # on every rerun would silently destroy that and break HTTPS on the
  # next redeploy — so once certbot has configured it, leave it alone.
  echo "    Nginx site already has HTTPS configured (by a previous certbot run) — leaving its content as-is."
else
  sed "s|YOUR_DOMAIN|${DOMAIN}|g" deploy/nginx.conf | sudo tee "$NGINX_SITE" >/dev/null
fi
sudo ln -sf "$NGINX_SITE" "/etc/nginx/sites-enabled/${SERVICE_NAME}"
sudo rm -f /etc/nginx/sites-enabled/default

if ! sudo nginx -t; then
  fail "Nginx config test failed — not reloading a broken config. Check $NGINX_SITE."
fi
sudo systemctl reload nginx
echo "    Nginx reloaded."

# ---------------------------------------------------------------------
# 8. HTTPS via certbot (skip if a cert already exists)
# ---------------------------------------------------------------------
step "Checking for an existing TLS certificate"
if sudo certbot certificates 2>/dev/null | grep -q "Domains: .*\b${DOMAIN}\b"; then
  echo "    Certificate for $DOMAIN already exists — skipping certbot."
else
  echo "    Requesting one from Let's Encrypt..."
  sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@${DOMAIN}" --redirect \
    || fail "certbot failed — is port 80 open in the Lightsail firewall, and does $DOMAIN's DNS actually point at this server yet? (dig $DOMAIN)"
fi

# ---------------------------------------------------------------------
# 9. End-to-end check
# ---------------------------------------------------------------------
step "Verifying the live site"
HTTP_CODE="$(curl -sk -o /dev/null -w '%{http_code}' "https://${DOMAIN}/" || echo "000")"
if [[ "$HTTP_CODE" != "200" ]]; then
  fail "https://${DOMAIN}/ returned HTTP $HTTP_CODE, expected 200. Check: sudo journalctl -u $SERVICE_NAME -f"
fi

echo
echo "✅ Deployed successfully: https://${DOMAIN}"
echo
echo "One thing left to do manually: make sure this exact redirect URI is"
echo "registered in your Spotify app at developer.spotify.com/dashboard:"
echo "    ${REDIRECT_URI}"
