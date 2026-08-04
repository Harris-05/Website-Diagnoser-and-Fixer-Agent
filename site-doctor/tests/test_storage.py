"""Tests for crawler/storage.py -- the on-disk cache contract.

Everything downstream (Lighthouse, the vision review, the PDF report)
locates artifacts through these path builders and through manifest.json,
so the layout is a real interface and worth pinning down.

Every test takes the isolated_cache fixture (see conftest.py) because
CACHE_ROOT is relative to the current directory and page_dir() creates
folders as a side effect of building a path.
"""

from crawler import storage
from models.schemas import CrawlResult, PageResult


def test_crawl_dir_layout(isolated_cache):
    assert storage.crawl_dir("abc123") == isolated_cache / "crawl_abc123"


def test_page_dir_is_created_on_access(isolated_cache):
    """Callers rely on this: save_html() writes straight to the path
    without mkdir-ing first, so page_dir has to have made the folder."""
    path = storage.page_dir("abc123", "about-us")

    assert path == isolated_cache / "crawl_abc123" / "pages" / "about-us"
    assert path.is_dir()


def test_artifact_paths_match_the_documented_layout(isolated_cache):
    crawl_root = isolated_cache / "crawl_abc123"
    page_root = crawl_root / "pages" / "home"

    assert storage.html_path("abc123", "home") == page_root / "page.html"
    assert storage.screenshot_path("abc123", "home", 0) == page_root / "0.png"
    assert storage.screenshot_path("abc123", "home", 3) == page_root / "3.png"
    assert storage.manifest_path("abc123") == crawl_root / "manifest.json"
    assert storage.ux_report_path("abc123") == crawl_root / "ux_report.md"


def test_save_html_writes_utf8_and_returns_the_path(isolated_cache):
    """UTF-8 is explicit throughout because Windows defaults to cp1252 and
    crashes on non-Latin-1 characters -- a bug this project already hit."""
    html = "<html><body><p>Prix: 50€ — café</p></body></html>"

    returned = storage.save_html("abc123", "home", html)

    written = storage.html_path("abc123", "home")
    assert written.read_text(encoding="utf-8") == html
    assert returned == str(written)


def test_manifest_round_trip_preserves_pages(isolated_cache):
    """save_manifest -> load_manifest is how a later run (or a debugging
    session) picks up a completed crawl, so it has to survive the JSON
    round trip intact."""
    original = CrawlResult(
        crawl_id="abc123",
        start_url="https://site.com",
        pages=[
            PageResult(
                url="https://site.com",
                slug="home",
                html_path="page.html",
                screenshot_paths=["0.png", "1.png"],
                depth=0,
            ),
            PageResult(
                url="https://site.com/about",
                slug="about",
                html_path="page.html",
                depth=1,
            ),
        ],
    )

    storage.save_manifest(original)
    loaded = storage.load_manifest("abc123")

    assert loaded.crawl_id == original.crawl_id
    assert loaded.start_url == original.start_url
    assert [p.url for p in loaded.pages] == [
        "https://site.com",
        "https://site.com/about",
    ]
    assert loaded.pages[0].screenshot_paths == ["0.png", "1.png"]
    assert loaded.pages[1].screenshot_paths == []
    assert loaded.pages[1].depth == 1
    assert loaded.crawled_at == original.crawled_at


def test_save_manifest_creates_the_crawl_dir_for_a_zero_page_crawl(isolated_cache):
    """Regression test: save_manifest used to raise FileNotFoundError when
    no page succeeded, because nothing had created the crawl folder yet."""
    empty = CrawlResult(crawl_id="empty1", start_url="https://site.com")

    returned = storage.save_manifest(empty)

    assert storage.manifest_path("empty1").is_file()
    assert returned == str(storage.manifest_path("empty1"))
    assert storage.load_manifest("empty1").pages == []
