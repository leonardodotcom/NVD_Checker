import os
from dataclasses import dataclass


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    nvd_api_key: str | None
    db_path: str
    cache_ttl: int
    secret_key: str | None
    cookie_secure: bool
    session_max_age: int
    enable_docs: bool


def get_settings() -> Settings:
    return Settings(
        nvd_api_key=os.getenv("NVD_API_KEY") or None,
        db_path=os.getenv("DB_PATH", "nvd_checker.db"),
        cache_ttl=int(os.getenv("CACHE_TTL", "900")),
        secret_key=os.getenv("SECRET_KEY") or None,
        cookie_secure=_flag("COOKIE_SECURE", "1"),
        session_max_age=int(os.getenv("SESSION_MAX_AGE", str(8 * 3600))),
        enable_docs=_flag("ENABLE_DOCS", "0"),
    )
