import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    nvd_api_key: str | None
    db_path: str
    cache_ttl: int


def get_settings() -> Settings:
    return Settings(
        nvd_api_key=os.getenv("NVD_API_KEY") or None,
        db_path=os.getenv("DB_PATH", "nvd_checker.db"),
        cache_ttl=int(os.getenv("CACHE_TTL", "900")),
    )
