"""Interactive login capture and recording (needs Playwright; run on a laptop with Chrome).

Why "attach" is the default: CNNVD/CNVD sit behind JavaScript anti-bot checks that
serve a blank page to a browser launched by automation. So instead of launching a
browser, we attach to the person's own, normally started Chrome (Chrome DevTools
Protocol) and only *observe*. The human does everything: login, captcha, searching.
Nothing is spoofed or disguised.
"""

import json
import shlex
import sys
import urllib.request

START_URLS = {
    "cnnvd": "https://www.cnnvd.org.cn/",
    "cnvd": "https://www.cnvd.org.cn/",
}
DEFAULT_PORT = 9222

MISSING_PLAYWRIGHT = (
    "Playwright is not installed. Install the optional capture dependencies:\n"
    "    python -m pip install -r requirements-cn.txt"
)


def chrome_launch_command(port: int = DEFAULT_PORT, platform: str | None = None) -> str:
    """Shell command that starts the person's own Chrome with the debugging port open.

    A separate --user-data-dir is required: Chrome 136+ ignores the debugging port on
    the default profile. The port listens on localhost only.
    """
    platform = platform or sys.platform
    if platform == "darwin":
        exe = r"/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome"
        profile = '"$HOME/cn-chrome-profile"'
    elif platform.startswith("win"):
        exe = r'"C:\Program Files\Google\Chrome\Application\chrome.exe"'
        profile = r'"%USERPROFILE%\cn-chrome-profile"'
    else:
        exe = "google-chrome"
        profile = '"$HOME/cn-chrome-profile"'
    return f"{exe} --remote-debugging-port={port} --user-data-dir={profile}"


def cdp_ready(port: int = DEFAULT_PORT) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as resp:
            return bool(json.load(resp).get("webSocketDebuggerUrl"))
    except (OSError, ValueError):
        return False


def attach_instructions(port: int = DEFAULT_PORT) -> str:
    return (
        "Start YOUR OWN Chrome with the debugging port open (close other windows of that profile first):\n\n"
        f"    {chrome_launch_command(port)}\n\n"
        "Then run this command again. The port only listens on this computer; close that Chrome when you are done."
    )


def connect_chrome(playwright, port: int = DEFAULT_PORT):
    """Attach to the person's Chrome; returns (browser, default_context). Exits with help if not running."""
    if not cdp_ready(port):
        sys.exit(f"No Chrome found on debugging port {port}.\n\n{attach_instructions(port)}")
    browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    if not browser.contexts:
        sys.exit("Connected, but Chrome has no open window. Open one and try again.")
    return browser, browser.contexts[0]


def capture_state(site: str, url: str | None = None, launch: bool = False, port: int = DEFAULT_PORT) -> dict:
    """Let the human log in and return Playwright's storage_state (cookies + local storage)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit(MISSING_PLAYWRIGHT)

    target = url or START_URLS[site]
    with sync_playwright() as p:
        if launch:
            print(f"Opening {target} in a browser window. (Sites with anti-bot checks may show a blank page; use the default attach mode then.)")
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(locale="zh-CN")
            context.new_page().goto(target)
        else:
            browser, context = connect_chrome(p, port)
            print(f"Attached to your Chrome. In that window open {target} and log in.")
        print("Log in as usual (captcha / SMS included), open any vulnerability list page to confirm you are in,")
        print("then come back here and press Enter. Your password is never read or stored; only the session is saved.")
        input("Press Enter once you are logged in... ")
        state = context.storage_state()
        browser.close()  # attach mode: only disconnects, Chrome stays open
    return state
