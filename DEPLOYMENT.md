# Deploying to AWS Lightsail

A from-scratch guide to running Pomodoro Spotify on a Lightsail instance,
reachable from anywhere, with real Spotify login working.

## ⚠️ Read this first: you need a domain name

Spotify's OAuth **requires HTTPS** for any redirect URI that isn't
`127.0.0.1`/`localhost`. A bare `http://<lightsail-ip>` will **not** work —
Spotify will reject the login. You need:

1. A hostname pointing at your Lightsail instance (a real domain, or the
   free workaround below), and
2. A free TLS certificate for it (via certbot, covered below).

**Don't have a domain?** Use your Lightsail instance's static IP with
[sslip.io](https://sslip.io) — no signup, no cost. If your static IP is
`3.90.12.34`, then `3.90.12.34.sslip.io` automatically resolves to that IP.
Use that as your hostname everywhere in this guide instead of a real domain.

---

## Fast path: one script

Once you've got the instance created and connected via SSH (steps 1–2
below), everything from "get the code" through "working HTTPS" is a single
command — [`deploy/deploy.sh`](deploy/deploy.sh):

```bash
curl -fsSL https://raw.githubusercontent.com/hamahero1/pomodoro-spotify/main/deploy/deploy.sh -o deploy.sh
chmod +x deploy.sh
./deploy.sh yourdomain.com        # or: ./deploy.sh --sslip
```

It clones the repo, sets up the venv, **runs the test suite and aborts if
anything fails**, writes `.env` (prompting for your Spotify Client
ID/Secret if `.env` doesn't exist yet — never touches it if it already
does), installs + starts the systemd service, configures Nginx, gets an
HTTPS cert via certbot, and does an end-to-end check against the live URL.
It's safe to re-run any time (e.g. after `git push`ing an update) — every
step checks its own state first rather than blindly redoing work.

The rest of this document explains what that script does step by step —
useful if something goes wrong, you want to understand the setup, or
you'd rather run it manually.

---

## 1. Create the Lightsail instance

1. In the [Lightsail console](https://lightsail.aws.amazon.com/), **Create
   instance**.
2. Platform: **Linux/Unix**. Blueprint: **OS Only → Ubuntu 22.04 LTS**
   (avoid the Bitnami blueprints — plain Ubuntu is simplest to reason about
   here).
3. Pick any plan (the cheapest $5/mo tier is plenty for personal use).
4. Create the instance, then open its page → **Networking** tab → attach a
   **static IP** (so it doesn't change on reboot).
5. Still on **Networking**, add firewall rules for **HTTP (80)** and
   **HTTPS (443)** in addition to the default SSH (22).
6. If using a real domain: add an **A record** at your DNS provider pointing
   your domain (or subdomain, e.g. `pomodoro.yourdomain.com`) at the static
   IP. If using sslip.io, skip this — no DNS setup needed.

Connect via the browser-based SSH button on the instance page, or your own
SSH client with the downloaded key.

## 2. Install system packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git nginx certbot python3-certbot-nginx
```

## 3. Get the code

```bash
cd ~
git clone https://github.com/<your-username>/pomodoro-spotify.git
cd pomodoro-spotify
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 4. Configure `.env` for production

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # copy this
nano .env
```

Fill in:

```
SECRET_KEY=<the random hex you just generated — required in production>
FLASK_ENV=production
FLASK_DEBUG=0

SPOTIFY_CLIENT_ID=<your real client id>
SPOTIFY_CLIENT_SECRET=<your real client secret>
SPOTIFY_REDIRECT_URI=https://YOUR_DOMAIN/spotify/callback

DATABASE_URL=sqlite:///pomodoro.db
```

`FLASK_ENV=production` matters: it enforces `SECRET_KEY` being set (the app
refuses to start without it) and makes session cookies `Secure` (HTTPS-only,
correct once you have TLS below).

## 5. Update the Spotify Developer Dashboard

Go to your app at [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
→ **Settings** → **Redirect URIs** → add:

```
https://YOUR_DOMAIN/spotify/callback
```

(Keep the old `http://127.0.0.1:5000/spotify/callback` entry too if you
still want to run it locally sometimes — Spotify allows multiple redirect
URIs on one app.)

## 6. Run it as a real service (systemd + Gunicorn)

Never run `python app.py` in production — that's Flask's development
server, single-threaded and not hardened for real traffic. Use the
included Gunicorn + systemd setup instead:

```bash
sudo cp deploy/pomodoro-spotify.service /etc/systemd/system/
sudo nano /etc/systemd/system/pomodoro-spotify.service   # fix User/paths if you didn't use `ubuntu` / ~/pomodoro-spotify
sudo systemctl daemon-reload
sudo systemctl enable --now pomodoro-spotify
sudo systemctl status pomodoro-spotify   # should say "active (running)"
```

Logs: `sudo journalctl -u pomodoro-spotify -f`

This also makes the app **auto-restart** if it ever crashes, and **come
back up automatically after a server reboot**.

## 7. Put Nginx in front of it, then get HTTPS

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/pomodoro-spotify
sudo nano /etc/nginx/sites-available/pomodoro-spotify   # replace YOUR_DOMAIN
sudo ln -s /etc/nginx/sites-available/pomodoro-spotify /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx -d YOUR_DOMAIN
```

Certbot will ask for an email (for renewal notices) and agree-to-terms,
then automatically edit the Nginx config to redirect HTTP → HTTPS and
install the certificate. It also sets up auto-renewal (certs are valid 90
days, renewal is silent — nothing for you to do later).

## 8. Verify

Open `https://YOUR_DOMAIN` in a browser. You should see the app, padlock
in the address bar, and **Connect Spotify** should complete a real login
and land you back on the app.

---

## Updating the app later

Easiest: re-run the deploy script with the same domain — it pulls the
latest code, reinstalls deps, re-runs the tests, and restarts the service,
all safely (it won't touch your existing `.env` or working HTTPS setup):

```bash
cd ~/pomodoro-spotify && ./deploy/deploy.sh yourdomain.com
```

Or do it by hand:

```bash
cd ~/pomodoro-spotify
git pull
source venv/bin/activate
pip install -r requirements.txt   # in case dependencies changed
pytest -q                          # confirm nothing's broken before restarting
sudo systemctl restart pomodoro-spotify
```

## Backing up your data

Your tasks, notes, and Spotify session all live in two places on the
server — neither is in git (by design: it's your personal data, not
source code):

```bash
# From your own machine, copy both down:
scp -r ubuntu@YOUR_DOMAIN:~/pomodoro-spotify/instance/pomodoro.db ./backup/
scp -r ubuntu@YOUR_DOMAIN:~/pomodoro-spotify/notes/files ./backup/
```

Do this periodically, or set up a cron job on the server that copies them
to Lightsail's own object storage / S3 on a schedule if you want it
automated.

## Troubleshooting

- **"Connect Spotify" fails / redirects to an error** — almost always a
  redirect URI mismatch. It must match **exactly** (including `https://`
  and no trailing slash) between `.env`'s `SPOTIFY_REDIRECT_URI` and what's
  registered in the Spotify dashboard.
- **502 Bad Gateway from Nginx** — Gunicorn isn't running or isn't
  listening on 127.0.0.1:8000. Check `sudo systemctl status
  pomodoro-spotify` and the journalctl logs above.
- **"database is locked" errors** — shouldn't happen with the included
  setup (single Gunicorn worker + a SQLite busy-timeout are both already
  configured for exactly this reason). If you changed `--workers` to more
  than 1 in the systemd unit, put it back to 1.
- **Certbot fails** — make sure your domain's DNS A record has actually
  propagated to the static IP first (`dig YOUR_DOMAIN` should show it) and
  that port 80 is open in the Lightsail firewall — certbot needs it for
  the HTTP validation challenge.
- **App works over HTTP but not HTTPS, or vice versa** — check
  `SPOTIFY_REDIRECT_URI` in `.env` uses `https://` after step 7, and that
  you restarted the service (`sudo systemctl restart pomodoro-spotify`)
  after editing `.env` — it's only read at startup.
