#!/usr/bin/env python3
"""Phase 0 probe: record how CNNVD / CNVD behave so the adapters can be written against real data.

Run on YOUR computer (it needs a display and your manual login):

    python -m pip install -r requirements-cn.txt && python -m playwright install chromium
    python scripts/cn_probe.py cnvd          # or: cnnvd

What happens:
  1. A browser window opens. Log in yourself (captcha / SMS included).
  2. Open the vulnerability list, search for one keyword (e.g. "Apache"), open one entry.
  3. Press Enter in the terminal. The script writes a folder with:
       index.json     every request the page made (method, URL, status, content type, size)
       bodies/        a copy of the JSON/HTML responses (capped in size)
       dom_*.html     the final page(s) as rendered
       summary.md     the distinct endpoints, to read first

Privacy: cookies, Set-Cookie, Authorization headers and request bodies of login/captcha/SMS
requests are NEVER recorded, and password/token-looking values are blanked. Still, open the
folder and skim it before sharing; the pages may show your account name.
"""

import argparse
import json
import re
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

START_URLS = {"cnnvd": "https://www.cnnvd.org.cn/", "cnvd": "https://www.cnvd.org.cn/"}
SENSITIVE_URL = re.compile(r"login|logout|passw|pwd|auth|captcha|verify|sms|token|session|signin", re.I)
SECRET_VALUE = re.compile(r'(?i)("?(?:password|passwd|pwd|token|authorization|cookie|ticket|csrf\w*)"?\s*[:=]\s*)("[^"]*"|[^&\s,}]+)')
RECORDED_TYPES = ("json", "html", "xml", "text/plain", "javascript")
MAX_BODY = 300_000
MAX_FILES = 80


def redact(text: str) -> str:
    return SECRET_VALUE.sub(lambda m: m.group(1) + '"<redacted>"', text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site", choices=START_URLS)
    ap.add_argument("--url", help="page to open first")
    ap.add_argument("--out", help="output folder (default: cn_probe_out/<site>-<timestamp>)")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("Install first:  python -m pip install -r requirements-cn.txt && python -m playwright install chromium")

    out = Path(args.out or f"cn_probe_out/{args.site}-{time.strftime('%Y%m%d-%H%M%S')}")
    (out / "bodies").mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    saved = 0

    def on_response(resp):
        nonlocal saved
        req = resp.request
        url = req.url
        ctype = (resp.headers.get("content-type") or "").split(";")[0].strip()
        sensitive = bool(SENSITIVE_URL.search(url))
        rec = {
            "n": len(records),
            "method": req.method,
            "url": url,
            "status": resp.status,
            "resource_type": req.resource_type,
            "content_type": ctype,
            "request_content_type": req.headers.get("content-type", ""),
            "sensitive_url_body_skipped": sensitive,
        }
        if not sensitive and req.post_data:
            rec["request_body"] = redact(req.post_data[:5000])
        if (
            not sensitive
            and saved < MAX_FILES
            and req.resource_type in ("document", "xhr", "fetch")
            and any(t in ctype for t in RECORDED_TYPES)
        ):
            try:
                body = resp.body()[:MAX_BODY].decode("utf-8", errors="replace")
                name = f"{rec['n']:03d}_{req.method}_{urlsplit(url).path.strip('/').replace('/', '_')[:60] or 'root'}.txt"
                (out / "bodies" / name).write_text(redact(body), encoding="utf-8")
                rec["body_file"] = name
                saved += 1
            except Exception as exc:  # response may be gone (redirect / navigation)
                rec["body_error"] = str(exc)[:100]
        records.append(rec)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="zh-CN")
        context.on("response", on_response)
        page = context.new_page()
        page.goto(args.url or START_URLS[args.site])
        print("\n1) Log in in the browser window.")
        print("2) Open the vulnerability list, search for ONE keyword (e.g. Apache), open ONE entry.")
        input("3) Press Enter here when done... ")
        for i, pg in enumerate(context.pages):
            try:
                (out / f"dom_{i}.html").write_text(redact(pg.content()), encoding="utf-8")
                records.append({"n": len(records), "dom_snapshot": f"dom_{i}.html", "url": pg.url})
            except Exception:
                pass
        # Session lifetime hints (names and expiry only, never values)
        cookies = [
            {"name": c["name"], "domain": c["domain"], "expires": c.get("expires"), "httpOnly": c.get("httpOnly")}
            for c in context.cookies()
        ]
        browser.close()

    (out / "index.json").write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "cookie_names.json").write_text(json.dumps(cookies, indent=1), encoding="utf-8")

    endpoints = Counter(
        (r["method"], urlsplit(r["url"]).netloc + urlsplit(r["url"]).path, r.get("content_type", ""))
        for r in records
        if r.get("resource_type") in ("xhr", "fetch", "document")
    )
    lines = [f"# Probe summary: {args.site}", "", f"{len(records)} requests recorded, {saved} bodies saved.", "",
             "| count | method | endpoint | content-type |", "|---|---|---|---|"]
    lines += [f"| {n} | {m} | {path} | {ct} |" for (m, path, ct), n in endpoints.most_common()]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nDone. Read {out / 'summary.md'} first, skim the folder, then share it.")


if __name__ == "__main__":
    main()
