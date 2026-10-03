import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_env_file(path: str | os.PathLike) -> list[str]:
    """Load KEY=VALUE lines from a .env file into os.environ.

    Variables that are already set in the real environment are never
    overridden, so Docker `env_file`, systemd `EnvironmentFile` and shell
    exports keep precedence. Supports comments, blank lines, an optional
    `export ` prefix, and single- or double-quoted values. Returns the names
    of the variables it set.
    """
    path = Path(path)
    if not path.is_file():
        return []
    loaded = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:  # inline comment after an unquoted value
            value = value.split(" #", 1)[0].rstrip()
        if key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


# Load the project's .env automatically (before any setting is read).
# ENV_FILE points to a different file; ENV_FILE="" disables loading.
_env_file = os.environ.get("ENV_FILE", str(PROJECT_ROOT / ".env"))
if _env_file:
    load_env_file(_env_file)


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
