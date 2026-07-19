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


def screenshot_page(url: str, max_screenshots: int = 4) -> list[str]:
    """Render the page and save screenshots at successive scroll positions,
    so a vision model can review sections a user would only see by scrolling,
    not just the above-the-fold view. Returns a list of local file paths,
    in scroll order (index 0 = no scroll / above the fold)."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    base_name = url.replace("https://", "").replace("http://", "").replace("/", "_")
    screenshot_paths = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")

        viewport_height = page.viewport_size["height"]
        page_height = page.evaluate("document.body.scrollHeight")

        # ceil division: how many viewport-heights it takes to cover the page,
        # capped at max_screenshots so long pages don't blow up the LLM call
        num_shots = min(max_screenshots, max(1, -(-page_height // viewport_height)))

        for i in range(num_shots):
            scroll_y = i * viewport_height
            page.evaluate(f"window.scrollTo(0, {scroll_y})")
            page.wait_for_timeout(300)  # let lazy-loaded content/animations settle

            shot_path = OUTPUT_DIR / f"{base_name}_{i}.png"
            page.screenshot(path=str(shot_path))
            screenshot_paths.append(str(shot_path))

        browser.close()

    return screenshot_paths


if __name__ == "__main__":
    target = input("Enter the URL to crawl: ").strip()
    path = crawl_page(target)
    ss_paths = screenshot_page(target)
    print(f"Saved {len(ss_paths)} screenshots: {ss_paths}")
    print(f"Saved local copy: {path}")