"""Manages the on-disk cache layout for a single crawl run.

Layout:
.site-doctor-cache/
    crawl_<id>/
        manifest.json
        pages/
            <slug>/
                page.html
                0.png
                1.png
                ...
"""

from pathlib import Path

from models.schemas import CrawlResult

CACHE_ROOT = Path("./.site-doctor-cache")


def crawl_dir(crawl_id: str) -> Path:
    """Root directory for a single crawl run."""
    return CACHE_ROOT / f"crawl_{crawl_id}"


def page_dir(crawl_id: str, slug: str) -> Path:
    """Directory for one page's artifacts within a crawl. Created on access."""
    d = crawl_dir(crawl_id) / "pages" / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def html_path(crawl_id: str, slug: str) -> Path:
    return page_dir(crawl_id, slug) / "page.html"


def screenshot_path(crawl_id: str, slug: str, index: int) -> Path:
    return page_dir(crawl_id, slug) / f"{index}.png"


def manifest_path(crawl_id: str) -> Path:
    return crawl_dir(crawl_id) / "manifest.json"

def ux_report_path(crawl_id: str) -> Path:
    return crawl_dir(crawl_id) / "ux_report.md"

def save_html(crawl_id: str, slug: str, html: str) -> str:
    """Write a page's HTML to its slot in the cache. Returns the saved path."""
    path = html_path(crawl_id, slug)
    path.write_text(html, encoding="utf-8")
    return str(path)


def save_manifest(crawl_result: CrawlResult) -> str:
    """Write manifest.json for a completed crawl -- the single source of
    truth downstream consumers (Lighthouse, vision review, future AI
    summarizers) should read instead of scanning folders directly."""
    path = manifest_path(crawl_result.crawl_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(crawl_result.model_dump_json(indent=2), encoding="utf-8")
    return str(path)


def load_manifest(crawl_id: str) -> CrawlResult:
    """Load a previously saved crawl's manifest back into a CrawlResult."""
    path = manifest_path(crawl_id)
    return CrawlResult.model_validate_json(path.read_text(encoding="utf-8"))