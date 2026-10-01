import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("NVD_API_KEY", raising=False)
    from app.sources.registry import get_sources

    get_sources.cache_clear()
    from app.main import app

    with TestClient(app) as c:
        yield c
    get_sources.cache_clear()
