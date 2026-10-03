"""User accounts, password hashing and session-based login."""

import hashlib
import hmac
import secrets
import sqlite3
import time
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from .db import connect

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
MIN_PASSWORD_LENGTH = 10
MAX_FAILURES = 5
LOCKOUT_SECONDS = 300


# ---------- password hashing ----------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        candidate = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate.hex(), digest)


# A real hash of a random password, so unknown usernames take as long as wrong passwords.
_DUMMY_HASH = hash_password(secrets.token_hex(16))


# ---------- user storage ----------
def create_user(username: str, password: str) -> None:
    username = username.strip()
    if not username:
        raise ValueError("Username cannot be blank")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, hash_password(password), now),
            )
    except sqlite3.IntegrityError:
        raise ValueError(f"User '{username}' already exists")


def set_password(username: str, password: str) -> bool:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    with connect() as conn:
        return conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?", (hash_password(password), username)
        ).rowcount > 0


def delete_user(username: str) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM users WHERE username = ?", (username,)).rowcount > 0


def list_users() -> list[tuple[str, str]]:
    with connect() as conn:
        rows = conn.execute("SELECT username, created_at FROM users ORDER BY username").fetchall()
        return [(r["username"], r["created_at"]) for r in rows]


def user_count() -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


# ---------- brute-force protection ----------
_failures: dict[str, list[float]] = {}


def _recent_failures(key: str) -> list[float]:
    cutoff = time.monotonic() - LOCKOUT_SECONDS
    recent = [t for t in _failures.get(key, []) if t > cutoff]
    _failures[key] = recent
    return recent


def is_locked(username: str) -> bool:
    return len(_recent_failures(username.lower())) >= MAX_FAILURES


def record_failure(username: str) -> None:
    _recent_failures(username.lower()).append(time.monotonic())


def clear_failures(username: str) -> None:
    _failures.pop(username.lower(), None)


def authenticate(username: str, password: str) -> str | None:
    """Return the canonical username if the credentials are valid."""
    with connect() as conn:
        row = conn.execute(
            "SELECT username, password_hash FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
    if row is None:
        verify_password(password, _DUMMY_HASH)
        return None
    return row["username"] if verify_password(password, row["password_hash"]) else None


def user_exists(username: str) -> bool:
    with connect() as conn:
        return conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone() is not None


# ---------- request dependency ----------
def current_user(request: Request) -> str | None:
    username = request.session.get("user")
    if username and user_exists(username):
        return username
    if username:  # user was deleted while logged in
        request.session.clear()
    return None


def require_user(request: Request) -> str:
    username = current_user(request)
    if not username:
        raise HTTPException(401, "Not authenticated")
    return username
