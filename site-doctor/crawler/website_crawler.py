"""BFS multi-page crawler: starting from one URL, discovers and visits
internal pages up to max_pages / max_depth, saving each page's HTML and
screenshots via storage.py and returning one CrawlResult covering the
whole run."""

import uuid
from collections import deque

from playwright.sync_api import sync_playwright

from models.schemas import CrawlResult, PageResult
from crawler.utils import normalize_url, extract_links, slugify
from crawler.storage import save_html, save_manifest, screenshot_path


class WebsiteCrawler:
    def __init__(self, max_pages: int = 10, max_depth: int = 2, max_screenshots: int = 4):
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.max_screenshots = max_screenshots

    def crawl(self, start_url: str, isux: bool = False) -> CrawlResult:
        crawl_id = uuid.uuid4().hex[:8]
        scheme = start_url.split("://")[0] if "://" in start_url else "https"

        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(normalize_url(start_url), 0)])
        pages: list[PageResult] = []

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            while queue and len(pages) < self.max_pages:
                url_key, depth = queue.popleft()
                if url_key in visited:
                    continue
                visited.add(url_key)

                full_url = self._with_scheme(url_key, scheme)

                try:
                    page.goto(full_url, wait_until="load", timeout=30000)
                except Exception as exc:
                    print(f"Skipping {full_url}: {exc}")
                    continue

                # React/Vite/SPA sites can finish "load" before the app has
                # actually hydrated -- at that point page.content() is just
                # a loading spinner inside <div id="root">, with no real
                # <a href> tags anywhere yet (see CLAUDE.md bug log). Give
                # the app a short, bounded window to mount real content
                # before we snapshot the DOM or take screenshots off this
                # page object. On a static/SSR page this resolves
                # instantly since links already exist -- effectively a
                # no-op there. On a genuinely link-less SPA (onClick-only
                # routing, or a real single-page site) it just times out
                # harmlessly and we proceed with whatever's there.
                try:
                    page.wait_for_function(
                        "document.querySelectorAll('a[href]').length > 0",
                        timeout=8000,
                    )
                except Exception:
                    pass

                html = page.content()
                slug = slugify(url_key)

                saved_html_path = save_html(crawl_id, slug, html)
                saved_screenshot_paths: list[str] = []
                if isux:
                    saved_screenshot_paths = self._capture_screenshots(page, crawl_id, slug)

                pages.append(
                    PageResult(
                        url=full_url,
                        slug=slug,
                        html_path=saved_html_path,
                        screenshot_paths=saved_screenshot_paths,
                        depth=depth,
                    )
                )

                if depth < self.max_depth:
                    for link in extract_links(html, full_url):
                        if link not in visited:
                            queue.append((link, depth + 1))

            browser.close()

        result = CrawlResult(crawl_id=crawl_id, start_url=start_url, pages=pages)
        save_manifest(result)
        return result

    @staticmethod
    def _with_scheme(url_key: str, scheme: str) -> str:
        # normalize_url() strips the scheme for use as a dedup key;
        # re-attach it here since Playwright needs a full URL to navigate.
        return url_key if "://" in url_key else f"{scheme}://{url_key}"

    def _capture_screenshots(self, page, crawl_id: str, slug: str) -> list[str]:
        """Same scroll-and-capture logic as the single-page version, now
        writing into the per-crawl, per-page cache layout."""
        # Finding a nav link (the earlier wait in crawl()) doesn't mean the
        # WHOLE page finished rendering -- data-fetched content (hero,
        # cards, etc.) can still be mid-load and showing a spinner. Give it
        # a short bounded window to settle before we start screenshotting.
        # Same reasoning as goto()'s wait_until -- we avoid "networkidle"
        # there because some sites never truly idle (chat widgets,
        # analytics) -- but a short, bounded, best-effort wait here is
        # safe since it only delays screenshots, never blocks the crawl.
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        viewport_height = page.viewport_size["height"]
        page_height = page.evaluate("document.body.scrollHeight")
        num_shots = min(self.max_screenshots, max(1, -(-page_height // viewport_height)))

        paths = []
        for i in range(num_shots):
            page.evaluate(f"window.scrollTo(0, {i * viewport_height})")
            page.wait_for_timeout(300)
            shot_path = screenshot_path(crawl_id, slug, i)
            page.screenshot(path=str(shot_path))
            paths.append(str(shot_path))
        return paths


if __name__ == "__main__":
    target = input("Enter the URL to crawl: ").strip()
    max_pages = int(input("Max pages (default 5): ").strip() or 5)
    crawler = WebsiteCrawler(max_pages=max_pages, max_depth=2)
    result = crawler.crawl(target)
    print(f"\nCrawled {len(result.pages)} pages, crawl_id={result.crawl_id}")
    for pg in result.pages:
        print(f"  [{pg.depth}] {pg.url} -> {pg.slug} ({len(pg.screenshot_paths)} screenshots)")