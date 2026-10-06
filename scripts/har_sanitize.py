#!/usr/bin/env python3
"""Turn a Chrome DevTools HAR export into the same sanitised folder the probe writes.

No Playwright needed. How to export:
  Chrome DevTools (F12) > Network tab > tick "Preserve log" > log in, open the vulnerability list,
  search ONE keyword, open ONE entry > right-click the list > "Save all as HAR with content"
  (if offered, choose the *sanitized* variant too).

    python scripts/har_sanitize.py cnvd.har cnvd [--out FOLDER]

All headers and cookies are dropped, bodies of login/captcha/SMS requests are skipped and
password/token-looking values are blanked. Delete the original .har afterwards: it contains your cookies.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sources.cn_recording import sanitize_har  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("har")
    ap.add_argument("site", choices=("cnnvd", "cnvd"))
    ap.add_argument("--out", help="output folder (default: cn_probe_out/<site>-har-<timestamp>)")
    args = ap.parse_args()
    try:
        har = json.loads(Path(args.har).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Cannot read HAR file: {exc}")
    out = Path(args.out or f"cn_probe_out/{args.site}-har-{time.strftime('%Y%m%d-%H%M%S')}")
    summary = sanitize_har(har, out, args.site)
    print(f"Done. Read {summary} first, skim the folder, then share it.")
    print(f"Delete {args.har} afterwards: it still contains your cookies.")


if __name__ == "__main__":
    main()
