import base64
import json

from app.sources import cn_recording as rec
from app.sources.cn_capture import chrome_launch_command


def test_redact_blanks_secrets_but_keeps_search_terms():
    text = '{"username":"leo","password":"hunter2","token": "abc"} pwd=xyz&q=apache&csrfToken=zzz'
    out = rec.redact(text)
    assert "hunter2" not in out and "abc" not in out and "xyz" not in out and "zzz" not in out
    assert "q=apache" in out and '"username":"leo"' in out


def test_sensitive_urls():
    assert rec.is_sensitive_url("https://x/web/user/login")
    assert rec.is_sensitive_url("https://x/captcha/image?id=1")
    assert rec.is_sensitive_url("https://x/api/sms/send")
    assert not rec.is_sensitive_url("https://x/web/homePage/vulList")


def _har():
    def entry(url, method="GET", status=200, mime="application/json", text="{}", rtype="xhr", post=None, enc=None):
        e = {
            "_resourceType": rtype,
            "request": {"method": method, "url": url,
                        "headers": [{"name": "Cookie", "value": "SECRETCOOKIE"}, {"name": "Authorization", "value": "Bearer SECRETTOKEN"}],
                        "cookies": [{"name": "sid", "value": "SECRETCOOKIE"}]},
            "response": {"status": status, "headers": [{"name": "Set-Cookie", "value": "sid=SECRETCOOKIE"}],
                         "content": {"mimeType": mime, "text": text}},
        }
        if enc:
            e["response"]["content"]["encoding"] = enc
        if post:
            e["request"]["postData"] = {"mimeType": "application/json", "text": post}
        return e

    return {"log": {"entries": [
        entry("https://www.cnvd.org.cn/user/login", "POST", post='{"username":"leo","password":"hunter2"}', text='{"ticket":"SECRETTICKET"}'),
        entry("https://www.cnvd.org.cn/flaw/list?flag=true", "POST", post='{"keyword":"apache","pageNo":1,"token":"SECRETTOKEN2"}',
              text=json.dumps({"rows": [{"id": "CNVD-2026-1", "title": "漏洞"}]})),
        entry("https://www.cnvd.org.cn/flaw/show/CNVD-2026-1", rtype="document", mime="text/html",
              text=base64.b64encode("<html>详情 password=hunter2</html>".encode()).decode(), enc="base64"),
        entry("https://www.cnvd.org.cn/static/app.png", rtype="image", mime="image/png", text="PNGDATA"),
    ]}}


def test_sanitize_har_removes_secrets_and_keeps_structure(tmp_path):
    out = tmp_path / "out"
    summary = rec.sanitize_har(_har(), out, "cnvd")

    everything = "\n".join(p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file())
    for secret in ("SECRETCOOKIE", "SECRETTOKEN", "SECRETTICKET", "hunter2"):
        assert secret not in everything

    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    login, listing, detail, image = index
    assert login["sensitive_url_body_skipped"] and "request_body" not in login and "body_file" not in login
    assert listing["method"] == "POST" and '"keyword":"apache"' in listing["request_body"]
    assert "<redacted>" in listing["request_body"]
    assert "CNVD-2026-1" in (out / "bodies" / listing["body_file"]).read_text(encoding="utf-8")
    assert "详情" in (out / "bodies" / detail["body_file"]).read_text(encoding="utf-8")  # base64 decoded
    assert "body_file" not in image
    text = summary.read_text(encoding="utf-8")
    assert "flaw/list" in text and "4 requests recorded, 2 bodies saved" in text


def test_body_cap_and_file_names():
    assert rec.body_filename(7, "POST", "https://x/a/b/c?q=1") == "007_POST_a_b_c.txt"
    assert rec.body_filename(0, "GET", "https://x/") == "000_GET_root.txt"
    assert rec.wants_body("https://x/list", "xhr", "application/json", 0)
    assert not rec.wants_body("https://x/list", "xhr", "application/json", rec.MAX_FILES)
    assert not rec.wants_body("https://x/list", "image", "image/png", 0)


def test_chrome_launch_commands_per_platform():
    mac, win, linux = (chrome_launch_command(9222, p) for p in ("darwin", "win32", "linux"))
    assert "Google\\ Chrome.app" in mac and "--remote-debugging-port=9222" in mac
    assert "chrome.exe" in win and "cn-chrome-profile" in win
    assert linux.startswith("google-chrome ") and "--user-data-dir" in linux
