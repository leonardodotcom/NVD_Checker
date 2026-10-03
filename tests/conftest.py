import os

# Must be set before app.main is imported (it reads settings at import time).
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ["COOKIE_SECURE"] = "0"
os.environ.pop("NVD_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_USER, TEST_PASSWORD = "alice", "correct horse battery"


@pytest.fixture
def anon_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    from app import auth
    from app.main import app
    from app.sources.registry import get_sources

    get_sources.cache_clear()
    auth._failures.clear()
    with TestClient(app) as c:
        auth.create_user(TEST_USER, TEST_PASSWORD)
        yield c
    get_sources.cache_clear()


@pytest.fixture
def client(anon_client):
    resp = anon_client.post("/api/login", json={"username": TEST_USER, "password": TEST_PASSWORD})
    assert resp.status_code == 200
    return anon_client
