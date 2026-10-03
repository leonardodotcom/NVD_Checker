# NVD Checker

A small web app that monitors vulnerability databases for **your own trigger words**. It groups keywords into
**projects** (one per product or stack you care about), searches the selected sources over a time window, and
aggregates the results into a single de-duplicated, sortable list that you can export to CSV.

- **Sources:** NVD (NIST, CVE API 2.0). CNNVD and CNVD (China) appear in the UI as *coming soon*. Both need an
  authenticated session, so each source is a predefined adapter in the backend rather than a free-form URL.
- **Time ranges:** last 24 h, 7 d, 30 d, 90 d, 6 months, 1 year, or a custom range of up to 3 years. You can filter
  on published or last-modified date.
- **Aggregation:** every keyword is run against every selected source. Results are de-duplicated by CVE, and the
  keywords each CVE matched are merged. The list is sorted newest first, then by severity, with per-keyword and
  per-severity counts.

> **Installing on a server for your team?** Follow **[DEPLOY.md](DEPLOY.md)**. It's a step-by-step guide covering
> Docker or systemd + nginx, HTTPS, user accounts, backups and troubleshooting.

## Run it locally (development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# in .env: set SECRET_KEY (any random string) and COOKIE_SECURE=0 (plain http on localhost)
export $(grep -v '^#' .env | xargs)
python -m app.manage create-user admin      # prompts for a password (min. 10 characters)
uvicorn app.main:app --reload
```

Open http://localhost:8000 and sign in. Create a project, add trigger words (tick *exact phrase* for multi-word terms that
must appear verbatim), choose sources and a time range, and click **Search**.

### NVD API key (recommended)

Without a key, NVD allows 5 requests per 30 s. With one, it allows 50. Each keyword needs at least one request,
and ranges longer than 120 days are split into 120-day chunks (an NVD limit). Large projects without a key are
therefore slow. A key is free from https://nvd.nist.gov/developers/request-an-api-key; put it in `NVD_API_KEY`.
Identical queries are cached in memory for `CACHE_TTL` seconds (15 min by default).

## API

All endpoints except `/api/login` and `/healthz` require a signed-in session.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/login`, `/api/logout` | sign in / out (`{"username", "password"}`) |
| GET | `/api/me` | current user |
| GET / POST | `/api/projects` | list / create projects |
| GET / PUT / DELETE | `/api/projects/{id}` | read / rename / delete a project |
| POST / DELETE | `/api/projects/{id}/keywords[/{kid}]` | add / remove a trigger word |
| GET | `/api/sources` | available sources (`enabled`, `requires_auth`) |
| POST | `/api/search` | run a search and return aggregated results |
| POST | `/api/search/export.csv` | same body as `/api/search`, returns CSV |

Example search body:
`{"project_id": 1, "keywords": [{"term": "extra"}], "sources": ["nvd"], "window": "30d", "date_field": "published"}`.

Interactive docs are at `/docs` when `ENABLE_DOCS=1`.

## Adding a source (e.g. CNNVD / CNVD)

1. Implement `search()` in `app/sources/cnnvd.py`, a subclass of `app.sources.base.Source`. It should log in
   (credentials from environment variables), query by keyword and date range, and return normalized
   `Vulnerability` objects.
2. Make `enabled` return `True` when the credentials are configured.
3. It's already registered in `app/sources/registry.py`, so the UI picks it up automatically.

## Project layout

```
app/
  main.py                 FastAPI app, session middleware, security headers, static UI
  auth.py                 user accounts, scrypt password hashing, login lockout
  manage.py               admin CLI: create-user / set-password / delete-user / list-users
  db.py                   SQLite storage for users, projects and keywords
  models.py               Pydantic models
  sources/                source adapters (nvd.py, cnnvd.py, cnvd.py) + registry
  services/aggregator.py  fan-out, de-duplication, sorting, counts
  routers/                REST endpoints
static/                   single-page UI (vanilla JS)
tests/                    pytest suite (NVD mocked with respx)
deploy/                   Caddyfile, systemd unit, nginx example
Dockerfile, docker-compose.yml
```

## Tests

```bash
pytest
```
