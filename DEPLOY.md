# Installing NVD Checker on a company server

This guide installs NVD Checker on a Linux server inside your company network, so colleagues can use it from
their browser at an address like `https://nvd-checker.yourcompany.local`. It assumes no prior experience with
hosting web apps. Each step says what it does and why.

There are two ways to install it. Pick one:

| | **Path A: Docker** (recommended) | **Path B: without Docker** |
| --- | --- | --- |
| Needs | Docker Engine + Compose plugin | Python 3.11+, nginx, systemd |
| HTTPS | Built in (Caddy) | You configure nginx |
| Updates | One command | A few commands |

If you're not sure, ask IT whether Docker is allowed on the server. If it is, use Path A.

---

## 1. How it fits together

```
 colleague's browser                company server                                 internet
 ───────────────────   HTTPS   ┌───────────────────────────────────────┐   HTTPS   ─────────
  nvd-checker.corp.local ────▶ │ reverse proxy (Caddy or nginx) :443   │
                               │     │  plain HTTP, local only          │
                               │     ▼                                 │
                               │ NVD Checker app :8000 ──▶ SQLite file │ ────────▶ services.nvd.nist.gov
                               └───────────────────────────────────────┘
```

- **Reverse proxy.** This is the only thing colleagues talk to. It handles HTTPS, so passwords and session cookies
  are encrypted on the network, and it forwards requests to the app. The app itself is never reachable directly.
- **App.** The Python program. It checks logins, stores projects and calls NVD.
- **SQLite file.** A single file holding users, projects and trigger words. Backing up the app means copying this
  file.
- **Outbound access.** The server must be able to reach `services.nvd.nist.gov` on port 443. Nothing on the
  internet ever connects *to* the server.

## 2. Is it safe?

For an internal tool, yes, as long as you follow this guide. The protections built in:

- **Login required.** Every page and API call needs an account. Accounts are created only by an administrator on
  the server; nobody can sign themselves up.
- **Passwords stored safely.** Only salted scrypt hashes are stored, never the passwords themselves. The minimum
  length is 10 characters. After 5 wrong attempts, the username is locked for 5 minutes.
- **Session cookies.** They're signed (they can't be forged without `SECRET_KEY`), `HttpOnly`, `Secure`
  (HTTPS-only) and `SameSite=Lax`, and they expire after 8 hours.
- **HTTPS everywhere.** Plain HTTP requests are redirected to HTTPS.
- **Browser protections.** Security headers are on: Content-Security-Policy, frame blocking, nosniff and HSTS. All
  data shown in the page is HTML-escaped.
- **Minimal privileges.** The app runs as an unprivileged user. In Docker, the app container isn't exposed to the
  network at all.
- **No API docs by default.** The interactive API docs are switched off.

What *you* need to do:

- **Keep it internal.** Make sure the firewall only allows port 443 (and 80, which just redirects) from the company
  network, and never from the internet. Ask IT if unsure.
- **Protect `SECRET_KEY`.** Anyone who has it can forge logins. Keep the `.env` file readable only by
  administrators (`chmod 600`).
- **Pick strong passwords.** Delete accounts when people leave.
- **Run exactly one app process.** The NVD rate limiter lives in memory, so don't scale it out. The provided
  configs already do this.
- **Tell your security team.** Many companies require a quick review before a new internal service goes live. This
  section is a good summary to send them.

## 3. What to ask IT for

1. **A Linux server or VM.** Ubuntu 22.04/24.04, Debian 12, or RHEL/Rocky 9. 1 vCPU, 1 GB RAM and 5 GB disk is
   plenty.
2. **A DNS name** pointing to that server, for example `nvd-checker.yourcompany.local`.
3. **A TLS certificate** for that name from the company's internal certificate authority: a certificate file and a
   private key file. Without one, the setup can create its own certificate, but browsers will show a warning until
   it's trusted (see [Certificates](#8-certificates)).
4. **Outbound HTTPS** to `services.nvd.nist.gov`. Ask whether the server must use a **proxy** for internet access,
   and whether that proxy **inspects TLS**. If it does, ask for the company **root CA certificate** file.
5. **Firewall:** inbound 443 and 80 from the internal network only.
6. *(Recommended)* **A free NVD API key**, which makes searches about 10× faster. Request one at
   https://nvd.nist.gov/developers/request-an-api-key. It arrives by email.

### Quick check: can the server reach NVD?

Log in to the server (`ssh you@server`) and run:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" "https://services.nvd.nist.gov/rest/json/cves/2.0?resultsPerPage=1"
```

- `200`: good, continue.
- Timeout or `Could not resolve host`: outbound access is blocked. Ask IT to allow it, or for proxy details.
- `SSL certificate problem`: a TLS-inspecting proxy. You'll need the company root CA (see
  [Corporate proxy](#9-corporate-proxy)).

---

## 4. Path A — Install with Docker

### A1. Install Docker (skip if `docker compose version` already works)

Ubuntu / Debian:
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER      # lets you run docker without sudo; log out and back in afterwards
docker compose version             # should print a version
```
RHEL / Rocky: follow https://docs.docker.com/engine/install/rhel/. Your IT team may have its own standard
package.

### A2. Get the code

```bash
sudo mkdir -p /opt/nvd-checker && sudo chown $USER /opt/nvd-checker
git clone https://github.com/leonardodotcom/NVD_Checker.git /opt/nvd-checker
cd /opt/nvd-checker
```
(If the server can't reach GitHub, download the repository as a ZIP on your PC, copy it with
`scp NVD_Checker.zip you@server:/opt/`, and unzip it there.)

### A3. Configure

```bash
cp .env.example .env
chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(32))"    # copy the output
nano .env
```
Set at least:

| Setting | Value |
| --- | --- |
| `SECRET_KEY` | the random string you just generated |
| `SITE_ADDRESS` | the DNS name, e.g. `nvd-checker.yourcompany.local` |
| `NVD_API_KEY` | your NVD key, if you have one |
| `CADDY_TLS` | leave `internal`, or see [Certificates](#8-certificates) to use IT's certificate |

### A4. Start it

```bash
docker compose up -d --build
docker compose ps
```
After a few seconds, `app` should show `Up … (healthy)` and `caddy` should show `Up`.

- `--build` builds the app image from the `Dockerfile`.
- `-d` runs it in the background.
- `restart: unless-stopped` in `docker-compose.yml` means it starts again automatically after a reboot.

### A5. Create the first user

```bash
docker compose exec app python -m app.manage create-user alice
```
You'll be asked for the password twice. It must be at least 10 characters.

### A6. Open it

Browse to `https://nvd-checker.yourcompany.local`, sign in, create a project and add trigger words. 🎉

---

## 5. Path B — Install without Docker (systemd + nginx)

The examples use Ubuntu/Debian commands. On RHEL/Rocky, replace `apt` with `dnf`; the nginx config goes in
`/etc/nginx/conf.d/`.

### B1. Install prerequisites

```bash
sudo apt update
sudo apt install -y python3 python3-venv git nginx sqlite3
python3 --version     # needs 3.11 or newer
```

### B2. Create a service user and get the code

```bash
sudo useradd --system --home /opt/nvd-checker --shell /usr/sbin/nologin nvdchecker
sudo git clone https://github.com/leonardodotcom/NVD_Checker.git /opt/nvd-checker
sudo python3 -m venv /opt/nvd-checker/.venv
sudo /opt/nvd-checker/.venv/bin/pip install -r /opt/nvd-checker/requirements.txt
sudo mkdir -p /var/lib/nvd-checker && sudo chown nvdchecker: /var/lib/nvd-checker
```
`nvdchecker` is a user that can't log in. The app runs as this user, so even a bug in the app can't touch the
rest of the server.

### B3. Configure

```bash
sudo mkdir -p /etc/nvd-checker
sudo cp /opt/nvd-checker/.env.example /etc/nvd-checker/nvd-checker.env
sudo chmod 600 /etc/nvd-checker/nvd-checker.env
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
sudo nano /etc/nvd-checker/nvd-checker.env
```
Set `SECRET_KEY`, set `DB_PATH=/var/lib/nvd-checker/nvd_checker.db`, and set `NVD_API_KEY` (optional). The
`SITE_ADDRESS`/`CADDY_TLS` lines are only for Docker and are ignored here.

### B4. Run it as a service

```bash
sudo cp /opt/nvd-checker/deploy/nvd-checker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nvd-checker
systemctl status nvd-checker          # should say "active (running)"
curl -s http://127.0.0.1:8000/healthz # {"status":"ok"}
```
systemd keeps the app running, restarts it if it crashes, and starts it at boot. The app listens only on
`127.0.0.1`, so it isn't reachable from other machines except through nginx.

### B5. Put nginx (HTTPS) in front

```bash
sudo mkdir -p /etc/nginx/certs
sudo cp nvd-checker.crt nvd-checker.key /etc/nginx/certs/     # the files from IT
sudo chmod 600 /etc/nginx/certs/nvd-checker.key
sudo cp /opt/nvd-checker/deploy/nginx.conf.example /etc/nginx/sites-available/nvd-checker
sudo nano /etc/nginx/sites-available/nvd-checker   # set server_name (twice) and the certificate paths
sudo ln -s /etc/nginx/sites-available/nvd-checker /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### B6. Create the first user

```bash
cd /opt/nvd-checker
sudo -u nvdchecker env $(sudo cat /etc/nvd-checker/nvd-checker.env | grep -v '^#' | xargs) \
  .venv/bin/python -m app.manage create-user alice
```
(The app loads a `.env` file from its own folder automatically, but on Path B the settings live in
`/etc/nvd-checker/`, which only root can read. That's why this command passes them in explicitly. The running
service gets them from systemd's `EnvironmentFile`.)

Then open `https://nvd-checker.yourcompany.local`.

---

## 6. Day-to-day administration

The commands below assume Docker. For Path B, run the same `python -m app.manage …` commands as in step B6.

| Task | Command |
| --- | --- |
| Add a user | `docker compose exec app python -m app.manage create-user bob` |
| Reset a password | `docker compose exec app python -m app.manage set-password bob` |
| Remove a user (their sessions stop working immediately) | `docker compose exec app python -m app.manage delete-user bob` |
| List users | `docker compose exec app python -m app.manage list-users` |
| See logs | `docker compose logs -f app` (Path B: `journalctl -u nvd-checker -f`) |
| Restart | `docker compose restart app` (Path B: `sudo systemctl restart nvd-checker`) |
| Stop | `docker compose down` (data is kept) |

### Updating to a new version

```bash
cd /opt/nvd-checker
git pull
docker compose up -d --build
```
Path B: `sudo git pull && sudo .venv/bin/pip install -r requirements.txt && sudo systemctl restart nvd-checker`.

### Backups

All data lives in one SQLite file. Back it up daily, for example with a cron job:

```bash
# Docker
docker compose exec app python -c "import sqlite3; s=sqlite3.connect('/data/nvd_checker.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d)"
docker compose cp app:/data/backup.db ./backup-$(date +%F).db
# Path B
sudo -u nvdchecker sqlite3 /var/lib/nvd-checker/nvd_checker.db ".backup '/var/lib/nvd-checker/backup-$(date +%F).db'"
```
To restore, stop the app, put the backup file in place under the original name, and start the app again.

---

## 7. Configuration reference (`.env`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `SECRET_KEY` | — (**required**) | Signs session cookies. The app refuses to start without it. Changing it logs everybody out. |
| `NVD_API_KEY` | empty | NVD key. Raises the rate limit from 5 to 50 requests per 30 s. |
| `CACHE_TTL` | `900` | Seconds to reuse identical NVD results. |
| `DB_PATH` | `nvd_checker.db` | SQLite file location. Docker forces `/data/nvd_checker.db`. |
| `COOKIE_SECURE` | `1` | Only send the session cookie over HTTPS. Set `0` **only** for local testing over plain http. |
| `SESSION_MAX_AGE` | `28800` | Login lifetime in seconds (8 h). |
| `ENABLE_DOCS` | `0` | `1` exposes interactive API docs at `/docs`. |
| `SITE_ADDRESS` | — | Docker only: the hostname Caddy serves. |
| `CADDY_TLS` | `internal` | Docker only: `internal`, or `/certs/cert.pem /certs/key.pem`. |
| `HTTPS_PROXY`, `NO_PROXY` | empty | Corporate outbound proxy. |
| `SSL_CERT_FILE` | empty | CA bundle for a TLS-inspecting proxy. |

## 8. Certificates

**Option 1: certificate from IT (best).** Browsers trust it with no warnings.
```bash
mkdir -p certs
cp /path/from/it/nvd-checker.crt certs/cert.pem    # include intermediate certificates in this file if IT gave you any
cp /path/from/it/nvd-checker.key certs/key.pem
chmod 600 certs/key.pem
# in .env:
CADDY_TLS=/certs/cert.pem /certs/key.pem
docker compose up -d
```

**Option 2: `CADDY_TLS=internal`.** Caddy creates its own small certificate authority. The traffic is encrypted,
but browsers show "not secure" until that authority is trusted. To fix the warning, export Caddy's root
certificate and ask IT to distribute it to company machines (or import it into your own browser for a trial):
```bash
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
```

## 9. Corporate proxy

If the server reaches the internet through a proxy, add it to `.env`:
```
HTTPS_PROXY=http://proxy.yourcompany.local:8080
NO_PROXY=localhost,127.0.0.1
```

If that proxy **inspects TLS** (you saw `SSL certificate problem` in the quick check):

1. Save the company root CA as `certs/company-ca.pem`.
2. In `.env`, set `SSL_CERT_FILE=/certs/company-ca.pem` (Path B: the real path on disk). This lets the app verify
   NVD.
3. **Docker only:** the image build also downloads Python packages, so pass the CA to the build. Either uncomment
   the two `secrets` blocks in `docker-compose.yml`, or build once with
   `docker build --secret id=corp_ca,src=certs/company-ca.pem -t nvd-checker:latest .`
   and then run `docker compose up -d`.

Docker itself may also need the proxy to download base images. See
https://docs.docker.com/engine/daemon/proxy/.

## 10. Troubleshooting

| Symptom | Likely cause → fix |
| --- | --- |
| App container keeps restarting; logs say `SECRET_KEY is not set` | Set `SECRET_KEY` in `.env`, then `docker compose up -d`. |
| Login succeeds but you're immediately sent back to the login page | You're using plain `http://`. Use `https://`. (For an http-only test, set `COOKIE_SECURE=0`.) |
| "Too many failed attempts" | Wait 5 minutes, or reset the password with `set-password`. |
| Search shows `nvd / "keyword": network error …` | The server can't reach NVD. Run the quick check in §3; you probably need a proxy or a firewall rule. |
| Search error mentions `CERTIFICATE_VERIFY_FAILED` | TLS-inspecting proxy → set `SSL_CERT_FILE` (§9). |
| Search shows `HTTP 403` or `HTTP 503` from NVD | NVD rate limit or an outage. Add an `NVD_API_KEY`, or retry later. |
| Searches are slow | Without an API key, NVD allows 5 requests per 30 s and each trigger word needs at least one. Add a key, or use fewer words or a shorter time range. |
| Browser says "connection not private" | Expected with `CADDY_TLS=internal`. Use IT's certificate (§8). |
| `docker compose up` fails with `port is already allocated` | Another web server already uses 80/443. Stop it, or change the `ports:` mapping, e.g. `"8443:443"`. |
| Can't reach the site from another PC | Check the DNS name resolves to the server and the firewall allows 443 from your network. |

Run the health check on the server itself:
`curl -k https://localhost/healthz` should return `{"status":"ok"}`.

## 11. Chinese databases (CNNVD / CNVD)

CNNVD (run by CNITSEC) and CNVD (run by CNCERT/CC) are Chinese-language websites with **no API**, and they need a
login. The app therefore uses a login session that **a person captures once in a real browser**; the server reuses
it until the site rejects it. No password is ever read or stored.

> **Status:** the session tooling, source status in the UI and the result merging are done. The page parsers for
> each site are written after the one-time recording step in "Step 0" below, because the exact pages and
> parameters of both sites must be confirmed on a real login. Until then both sources show as
> "coming soon" and cannot be selected.

**Before you start**
- Check each site's terms of use and your company's policy for automated access. Use a **dedicated account**, not a
  personal one, and keep request volume low (the app waits `CN_REQUEST_DELAY` seconds between pages and caches
  results for `CN_CACHE_TTL`).
- Allow outbound HTTPS from the server to `www.cnnvd.org.cn` and `www.cnvd.org.cn` (firewall / proxy allow-list).
- Type your trigger words in **Chinese** for these sources; the entries are written in Chinese. A CVE id (for
  example `CVE-2026-1234`) also matches, since entries cite them.

**Step 0: record the sites (once, on your own computer)**
```bash
python -m pip install -r requirements-cn.txt && python -m playwright install chromium
python scripts/cn_probe.py cnvd        # then: python scripts/cn_probe.py cnnvd
```
A browser opens: log in, open the vulnerability list, search one keyword, open one entry, press Enter in the
terminal. The script saves a folder (`cn_probe_out/…`) with the requests the site made. Cookies, passwords and the
bodies of login requests are never recorded. Skim the folder, then hand it over so the parsers can be written.

**Capture a session (repeat whenever it expires)**
A server has no screen, so do this on your laptop:
```bash
python -m app.manage cn-login cnvd --out cnvd-session.json     # log in in the window, press Enter
```
Then install it on the server (the file is a credential: transfer it securely, delete the copy afterwards):
```bash
# Docker
docker compose cp cnvd-session.json app:/tmp/cnvd-session.json
docker compose exec app python -m app.manage cn-import-session cnvd /tmp/cnvd-session.json
docker compose exec app rm /tmp/cnvd-session.json
# Without Docker (run as the service user, with the same environment file as in step B6)
sudo -u nvdchecker ... .venv/bin/python -m app.manage cn-import-session cnvd /path/to/cnvd-session.json
```
Check it with `python -m app.manage cn-session-status` (Docker: `docker compose exec app …`). Sessions are stored in
`CN_SESSION_DIR` (`/data/sessions` in Docker, on the same volume as the database, mode 0600). They are not part of the
image and not in git.

**When a session expires** the source turns red in the UI ("session expired"), and searches that include it show an
error naming the command to run. Capture a new session as above; no restart is needed.
