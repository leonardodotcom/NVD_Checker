#!/usr/bin/env python3
"""Phase 0 probe: record how CNNVD / CNVD behave so the adapters can be written against real data.

These sites show a BLANK PAGE to a browser that automation launched, so this script does not
launch one. It attaches to YOUR OWN Chrome (started normally by you) and only watches the
network traffic, like the DevTools Network tab. You do everything by hand.

Steps (run from the project folder):

    python -m pip install -r requirements-cn.txt     # one-time
    python scripts/cn_probe.py cnvd                  # prints the Chrome command to run, then run it again

  1. Start Chrome with the command the script prints (it uses a separate profile folder).
  2. Run the script again; it attaches.
  3. In that Chrome window: open the site, log in (captcha / SMS included), open the vulnerability
     list, search for ONE keyword (e.g. Apache), open ONE entry.
  4. Press Enter in the terminal. A folder is written with:
       index.json     every request the page made (method, URL, status, content type)
       bodies/        copies of the JSON/HTML responses (size-capped)
       dom_*.html     the open page(s) as rendered
       summary.md     the distinct endpoints, read this first

No Chrome available or this route fails? Export a HAR from DevTools instead (see DEPLOY.md,
section 11) and run  python scripts/har_sanitize.py file.har cnvd

Privacy: cookies, Set-Cookie and Authorization headers and the bodies of login/captcha/SMS
requests are never recorded, and password/token-looking values are blanked. Still, skim the
folder before sharing; the pages may show your account name.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sources import cn_recording as rec  # noqa: E402
from app.sources.cn_capture import DEFAULT_PORT, START_URLS, connect_chrome  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site", choices=START_URLS)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help="Chrome debugging port (default 9222)")
    ap.add_argument("--out", help="output folder (default: cn_probe_out/<site>-<timestamp>)")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("Install first:  python -m pip install -r requirements-cn.txt")

    out = Path(args.out or f"cn_probe_out/{args.site}-{time.strftime('%Y%m%d-%H%M%S')}")
    records: list[dict] = []
    saved = 0

    def on_response(resp):
        nonlocal saved
        req = resp.request
        ctype = (resp.headers.get("content-type") or "").split(";")[0].strip()
        r = rec.make_record(
            len(records), req.method, req.url, resp.status, req.resource_type, ctype,
            req.headers.get("content-type", ""), req.post_data,
        )
        if rec.wants_body(req.url, req.resource_type, ctype, saved):
            try:
                rec.write_body(out, r, resp.body().decode("utf-8", errors="replace"))
                saved += 1
            except Exception as exc:  # the response can be gone after a navigation
                r["body_error"] = str(exc)[:100]
        records.append(r)

    with sync_playwright() as p:
        browser, context = connect_chrome(p, args.port)
        context.on("response", on_response)
        print(f"\nAttached to your Chrome. Recording started. Open {START_URLS[args.site]} in that window.")
        print("1) Log in.  2) Open the vulnerability list, search ONE keyword, open ONE entry.")
        input("3) Press Enter here when done... ")
        for i, pg in enumerate(context.pages):
            try:
                (out / f"dom_{i}.html").parent.mkdir(parents=True, exist_ok=True)
                (out / f"dom_{i}.html").write_text(rec.redact(pg.content()), encoding="utf-8")
                records.append({"n": len(records), "dom_snapshot": f"dom_{i}.html", "url": pg.url})
            except Exception:
                pass
        cookie_names = [  # names and expiry only, never values: tells us how long a session lasts
            {"name": c["name"], "domain": c["domain"], "expires": c.get("expires"), "httpOnly": c.get("httpOnly")}
            for c in context.cookies()
        ]
        browser.close()  # only disconnects; your Chrome stays open

    summary = rec.write_results(out, args.site, records, cookie_names)
    print(f"\nDone. Read {summary} first, skim the folder, then share it.")


if __name__ == "__main__":
    main()
