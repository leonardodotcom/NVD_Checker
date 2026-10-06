import json
import os
import stat
import time

import pytest

from app.sources import cn_session

GOOD = {"cookies": [{"name": "sid", "value": "x", "domain": ".cnvd.org.cn", "path": "/", "expires": -1}], "origins": []}


@pytest.fixture(autouse=True)
def session_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CN_SESSION_DIR", str(tmp_path / "sessions"))


def test_missing_session_is_login_required():
    status, detail = cn_session.describe("cnvd")
    assert status == "login_required" and "cn-login cnvd" in detail


def test_save_is_private_and_ready():
    path = cn_session.save_state("cnvd", GOOD)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert cn_session.describe("cnvd") == ("ready", "Session captured today")
    assert cn_session.cookie_jar(cn_session.load_state("cnvd")).get("sid") == "x"


def test_expired_marker_and_cleared_by_new_login():
    cn_session.save_state("cnvd", GOOD)
    cn_session.mark_expired("cnvd")
    assert cn_session.describe("cnvd")[0] == "session_expired"
    cn_session.save_state("cnvd", GOOD)
    assert cn_session.describe("cnvd")[0] == "ready"


def test_persistent_cookies_all_in_the_past_means_expired():
    old = {"cookies": [{"name": "sid", "value": "x", "domain": "d", "path": "/", "expires": time.time() - 10}]}
    cn_session.save_state("cnnvd", old)
    assert cn_session.describe("cnnvd")[0] == "session_expired"


@pytest.mark.parametrize("bad", [[], {"cookies": "nope"}, {"cookies": [{"name": "a"}]}, "text"])
def test_rejects_malformed_state(bad):
    with pytest.raises(ValueError):
        cn_session.save_state("cnvd", bad)


def test_unknown_site_rejected():
    with pytest.raises(ValueError):
        cn_session.session_path("../etc/passwd")


def test_import_cli(tmp_path, capsys):
    from app import manage

    f = tmp_path / "s.json"
    f.write_text(json.dumps(GOOD))
    assert manage.main(["cn-import-session", "cnnvd", str(f)]) == 0
    manage.main(["cn-session-status"])
    out = capsys.readouterr().out
    assert "cnnvd\tready" in out and "cnvd\tlogin_required" in out
    f.write_text("not json")
    with pytest.raises(SystemExit):
        manage.main(["cn-import-session", "cnnvd", str(f)])
