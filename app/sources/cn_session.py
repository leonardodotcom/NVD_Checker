"""Saved browser login sessions for the Chinese databases.

A human logs in once in a real browser (`python -m app.manage cn-login <site>`);
Playwright's `storage_state` (cookies + local storage) is saved here and reused
for scraping until the site rejects it. A session file is a credential: it is
written with mode 0600, never logged, and must not be committed or baked into an
image.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..config import get_settings

SITES = ("cnnvd", "cnvd")


def _dir() -> Path:
    return Path(get_settings().cn_session_dir)


def session_path(site: str) -> Path:
    if site not in SITES:
        raise ValueError(f"Unknown site '{site}'. Choose one of: {', '.join(SITES)}")
    return _dir() / f"{site}.json"


def _expired_marker(site: str) -> Path:
    return _dir() / f"{site}.expired"


def validate_state(state: object) -> dict:
    """Raise ValueError unless `state` looks like a Playwright storage_state."""
    if not isinstance(state, dict) or not isinstance(state.get("cookies"), list):
        raise ValueError("Not a Playwright storage_state file (expected an object with a 'cookies' list)")
    for c in state["cookies"]:
        if not isinstance(c, dict) or "name" not in c or "value" not in c:
            raise ValueError("Malformed cookie entry in session file")
    return state


def save_state(site: str, state: dict) -> Path:
    """Write the session atomically with owner-only permissions; clears any 'expired' flag."""
    validate_state(state)
    path = session_path(site)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    os.replace(tmp, path)
    os.chmod(path, 0o600)
    _expired_marker(site).unlink(missing_ok=True)
    return path


def load_state(site: str) -> dict | None:
    path = session_path(site)
    try:
        return validate_state(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def mark_expired(site: str) -> None:
    """Remember that the site rejected this session, so the UI asks for a re-login."""
    try:
        _dir().mkdir(parents=True, exist_ok=True)
        _expired_marker(site).write_text(datetime.now(timezone.utc).isoformat(timespec="seconds"))
    except OSError:
        pass


def cookie_jar(state: dict) -> httpx.Cookies:
    jar = httpx.Cookies()
    for c in state["cookies"]:
        jar.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))
    return jar


def _persistent_expiries(state: dict) -> list[float]:
    # Playwright uses expires == -1 for session cookies
    return [c["expires"] for c in state["cookies"] if isinstance(c.get("expires"), (int, float)) and c["expires"] > 0]


def describe(site: str) -> tuple[str, str]:
    """(status, detail) for the UI. Status: ready | login_required | session_expired."""
    path = session_path(site)
    state = load_state(site)
    if state is None:
        return "login_required", "No login session. An administrator must run: python -m app.manage cn-login " + site
    if _expired_marker(site).exists():
        return "session_expired", "Login session expired. An administrator must run: python -m app.manage cn-login " + site
    expiries = _persistent_expiries(state)
    if expiries and max(expiries) < time.time():
        return "session_expired", "Login session expired. An administrator must run: python -m app.manage cn-login " + site
    age_days = int((time.time() - path.stat().st_mtime) // 86400)
    detail = "Session captured today" if age_days == 0 else f"Session captured {age_days} day{'s' if age_days != 1 else ''} ago"
    return "ready", detail
