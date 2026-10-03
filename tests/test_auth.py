import pytest

from app import auth, manage

from .conftest import TEST_PASSWORD, TEST_USER


def test_hash_round_trip():
    h = auth.hash_password("s3cret-password")
    assert h.startswith("scrypt$") and "s3cret" not in h
    assert auth.verify_password("s3cret-password", h)
    assert not auth.verify_password("wrong", h)
    assert not auth.verify_password("x", "garbage")
    assert auth.hash_password("same") != auth.hash_password("same")  # salted


def test_api_requires_login(anon_client):
    assert anon_client.get("/api/projects").status_code == 401
    assert anon_client.post("/api/search", json={"keywords": [{"term": "x"}]}).status_code == 401
    assert anon_client.get("/api/sources").status_code == 401
    assert anon_client.get("/api/me").status_code == 401
    assert anon_client.get("/healthz").status_code == 200


def test_pages_redirect_when_logged_out(anon_client):
    r = anon_client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert anon_client.get("/login").status_code == 200


def test_login_logout_round_trip(anon_client):
    r = anon_client.post("/api/login", json={"username": "ALICE", "password": TEST_PASSWORD})
    assert r.status_code == 200 and r.json() == {"user": TEST_USER}
    assert anon_client.get("/api/me").json() == {"user": TEST_USER}
    assert anon_client.get("/login", follow_redirects=False).status_code == 303
    assert anon_client.get("/").status_code == 200
    assert anon_client.post("/api/logout").status_code == 204
    assert anon_client.get("/api/projects").status_code == 401


def test_wrong_password_and_lockout(anon_client):
    for _ in range(auth.MAX_FAILURES):
        r = anon_client.post("/api/login", json={"username": TEST_USER, "password": "nope"})
        assert r.status_code == 401
    r = anon_client.post("/api/login", json={"username": TEST_USER, "password": TEST_PASSWORD})
    assert r.status_code == 429
    assert anon_client.post("/api/login", json={"username": "ghost", "password": "x"}).status_code == 401


def test_deleted_user_loses_session(client):
    auth.delete_user(TEST_USER)
    assert client.get("/api/projects").status_code == 401


def test_security_headers(anon_client):
    headers = anon_client.get("/healthz").headers
    assert headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in headers["content-security-policy"]


def test_docs_disabled_by_default(anon_client):
    assert anon_client.get("/docs").status_code == 404


def test_manage_cli(anon_client, monkeypatch, capsys):
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "another long password")
    assert manage.main(["create-user", "bob"]) == 0
    assert auth.authenticate("bob", "another long password") == "bob"
    manage.main(["list-users"])
    assert "bob" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        manage.main(["create-user", "bob"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "short")
    with pytest.raises(SystemExit):
        manage.main(["create-user", "carol"])
    assert manage.main(["delete-user", "bob"]) == 0
    assert auth.authenticate("bob", "another long password") is None
