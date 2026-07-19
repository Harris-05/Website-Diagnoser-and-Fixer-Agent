"""Fetches a page with Playwright and saves a local, self-contained copy
that Lighthouse (and later, our fix-writer) can operate on."""

from pathlib import Path
from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path("./.site-doctor-cache")


def crawl_page(url: str) -> str:
    """Render the page and save a local HTML copy. Returns the local file path."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        html = page.content()
        browser.close()

    # naive filename from URL — fine for v1, single-page scope
    filename = url.replace("https://", "").replace("http://", "").replace("/", "_") + ".html"
    local_path = OUTPUT_DIR / filename
    local_path.write_text(html, encoding="utf-8")

    return str(local_path)


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    path = crawl_page(target)
    print(f"Saved local copy: {path}")
