"""Interactive login capture (needs Playwright and a display; run on a laptop)."""

import sys

START_URLS = {
    "cnnvd": "https://www.cnnvd.org.cn/",
    "cnvd": "https://www.cnvd.org.cn/",
}

MISSING_PLAYWRIGHT = (
    "Playwright is not installed. Install the optional capture dependencies:\n"
    "    python -m pip install -r requirements-cn.txt\n"
    "    python -m playwright install chromium"
)


def capture_state(site: str, url: str | None = None) -> dict:
    """Open a visible browser, let the human log in, and return Playwright's storage_state."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit(MISSING_PLAYWRIGHT)

    target = url or START_URLS[site]
    print(f"Opening {target} in a browser window.")
    print("Log in as usual (captcha / SMS included), open any vulnerability list page to confirm you are in,")
    print("then come back here and press Enter. Your password is never read or stored; only the session is saved.")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="zh-CN")
        page = context.new_page()
        page.goto(target)
        input("Press Enter once you are logged in... ")
        state = context.storage_state()
        browser.close()
    return state
