"""Shared helpers for recording how CNNVD / CNVD behave (the Phase 0 probe).

Used by `scripts/cn_probe.py` (live recording from the user's own Chrome) and
`scripts/har_sanitize.py` (a HAR exported from Chrome DevTools), so both routes
produce the same folder layout and apply the same privacy rules:

* cookies, Set-Cookie and Authorization headers are never recorded (no headers at all);
* bodies of login / captcha / SMS / token-looking requests are skipped entirely;
* password- or token-looking values inside any other text are blanked.
"""

import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

SENSITIVE_URL = re.compile(r"login|logout|passw|pwd|auth|captcha|verify|sms|token|session|signin", re.I)
SECRET_VALUE = re.compile(
    r'(?i)("?(?:password|passwd|pwd|token|authorization|cookie|ticket|csrf\w*)"?\s*[:=]\s*)("[^"]*"|[^&\s,}]+)'
)
RECORDED_TYPES = ("json", "html", "xml", "text/plain", "javascript")
BODY_RESOURCE_TYPES = ("document", "xhr", "fetch")
MAX_BODY = 300_000
MAX_FILES = 80
MAX_REQUEST_BODY = 5000


def redact(text: str) -> str:
    return SECRET_VALUE.sub(lambda m: m.group(1) + '"<redacted>"', text)


def is_sensitive_url(url: str) -> bool:
    return bool(SENSITIVE_URL.search(url))


def wants_body(url: str, resource_type: str, content_type: str, saved: int) -> bool:
    return (
        not is_sensitive_url(url)
        and saved < MAX_FILES
        and resource_type in BODY_RESOURCE_TYPES
        and any(t in content_type for t in RECORDED_TYPES)
    )


def body_filename(n: int, method: str, url: str) -> str:
    slug = urlsplit(url).path.strip("/").replace("/", "_")[:60] or "root"
    slug = re.sub(r"[^A-Za-z0-9_.-]", "_", slug)
    return f"{n:03d}_{method}_{slug}.txt"


def make_record(n: int, method: str, url: str, status: int, resource_type: str, content_type: str,
                request_content_type: str, request_body: str | None) -> dict:
    sensitive = is_sensitive_url(url)
    rec = {
        "n": n,
        "method": method,
        "url": url,
        "status": status,
        "resource_type": resource_type,
        "content_type": content_type,
        "request_content_type": request_content_type,
        "sensitive_url_body_skipped": sensitive,
    }
    if not sensitive and request_body:
        rec["request_body"] = redact(request_body[:MAX_REQUEST_BODY])
    return rec


def write_body(out: Path, rec: dict, text: str) -> None:
    name = body_filename(rec["n"], rec["method"], rec["url"])
    (out / "bodies").mkdir(parents=True, exist_ok=True)
    (out / "bodies" / name).write_text(redact(text[:MAX_BODY]), encoding="utf-8")
    rec["body_file"] = name


def write_results(out: Path, site: str, records: list[dict], cookie_names: list[dict] | None = None) -> Path:
    """Write index.json, cookie_names.json (names/expiry only) and summary.md; return summary path."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.json").write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    if cookie_names is not None:
        (out / "cookie_names.json").write_text(json.dumps(cookie_names, indent=1), encoding="utf-8")
    saved = sum(1 for r in records if "body_file" in r)
    endpoints = Counter(
        (r["method"], urlsplit(r["url"]).netloc + urlsplit(r["url"]).path, r.get("content_type", ""))
        for r in records
        if r.get("resource_type") in BODY_RESOURCE_TYPES
    )
    lines = [f"# Probe summary: {site}", "", f"{len(records)} requests recorded, {saved} bodies saved.", "",
             "| count | method | endpoint | content-type |", "|---|---|---|---|"]
    lines += [f"| {n} | {m} | {path} | {ct} |" for (m, path, ct), n in endpoints.most_common()]
    summary = out / "summary.md"
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def sanitize_har(har: dict, out: Path, site: str) -> Path:
    """Reduce a Chrome DevTools HAR export to the probe's folder format, dropping every header and cookie."""
    import base64

    entries = (har.get("log") or {}).get("entries") or []
    records: list[dict] = []
    saved = 0
    for e in entries:
        req, resp = e.get("request", {}), e.get("response", {})
        content = resp.get("content", {}) or {}
        ctype = (content.get("mimeType") or "").split(";")[0].strip()
        post = req.get("postData") or {}
        rtype = (e.get("_resourceType") or "").lower()
        rec = make_record(
            len(records), req.get("method", "GET"), req.get("url", ""), resp.get("status", 0),
            {"xhr": "xhr", "fetch": "fetch", "document": "document"}.get(rtype, rtype or "other"),
            ctype, post.get("mimeType", ""), post.get("text"),
        )
        text = content.get("text")
        if text and wants_body(rec["url"], rec["resource_type"], ctype, saved):
            if content.get("encoding") == "base64":
                try:
                    text = base64.b64decode(text).decode("utf-8", errors="replace")
                except ValueError:
                    text = ""
            if text:
                write_body(out, rec, text)
                saved += 1
        records.append(rec)
    return write_results(out, site, records)
