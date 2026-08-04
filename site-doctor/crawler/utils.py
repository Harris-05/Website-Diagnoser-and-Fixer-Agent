"""URL and link-handling utilities for the multi-page crawler."""

import re
from urllib.parse import urljoin, urlparse
from pathlib import Path
from bs4 import BeautifulSoup

# href prefixes that are never crawlable pages
_SKIP_PREFIXES = ("mailto:", "tel:", "javascript:", "#")


def normalize_url(url: str) -> str:
    """
    Normalize a URL by removing trailing slash, query strings, and fragments,
    so equivalent URLs (with/without trailing slash, differing query params)
    are recognized as the same page.

    Args:
        url (str): The URL to normalize.

    Returns:
        str: The normalized URL.
    """
    url=url.split("//")[1]
    url = url.split("?")[0]
    url = url.split("#")[0]
    url = url.rstrip("/")
    return url


def is_internal_link(url: str, base_url: str) -> bool:
    """
    Check if a URL is internal relative to a base URL, by comparing hostnames
    (not string-prefix matching on the full URL, which is spoofable by
    e.g. "example.com.evil.com").

    Args:
        url (str): An ABSOLUTE URL to check (resolve relative URLs first
            with urljoin before calling this).
        base_url (str): The base URL whose hostname defines "internal".

    Returns:
        bool: True if url shares the same hostname as base_url.
    """
    url_host = urlparse(url).netloc.lower()
    base_host = urlparse(base_url).netloc.lower()
    return url_host == base_host


def slugify(url_or_path: str) -> str:
    """
    Turn a URL or path into a filesystem-safe folder name.

    Args:
        url_or_path (str): A URL or path, e.g. "https://site.com/about-us/".

    Returns:
        str: A safe slug, e.g. "about-us". Falls back to "home" for the
        root path, since an empty string is not a valid folder name.
    """
    path = urlparse(url_or_path).path if "://" in url_or_path else url_or_path
    path = path.strip("/").lower()

    if not path:
        return "home"

    slug = re.sub(r"[^a-z0-9]+", "-", path).strip("-")
    return slug or "home"


def extract_links(html: str, base_url: str) -> list[str]:
    """
    Extract all internal, crawlable links from an HTML string, resolving
    relative hrefs (e.g. "/about") to absolute URLs against base_url before
    checking whether they're internal.

    Args:
        html (str): The HTML content to parse.
        base_url (str): The URL the HTML was fetched from, used to resolve
            relative links to absolute ones.

    Returns:
        list[str]: A de-duplicated list of internal links in normalize_url()
        form, i.e. WITHOUT a scheme -- "site.com/about", not
        "https://site.com/about". These are de-duplication keys for the BFS
        queue, not navigable URLs; WebsiteCrawler._with_scheme() re-attaches
        the scheme before Playwright uses them. Non-page links (mailto:,
        tel:, javascript:, in-page #anchors) are excluded.
    """
    soup = BeautifulSoup(html, "html.parser")
    links: set[str] = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()

        if not href or href.startswith(_SKIP_PREFIXES):
            continue

        absolute_url = urljoin(base_url, href)

        if is_internal_link(absolute_url, base_url):
            links.add(normalize_url(absolute_url))

    return list(links)


def main():

    url = input("Enter a URL to normalize: ")
    print(f"Normalized URL: {normalize_url(url)}")
    print(f"Slug: {slugify(url)}")

    base = input("Enter a base URL: ")
    print(normalize_url(base))
    html_path=Path(f"./.site-doctor-cache/{normalize_url(base)}_.html")
    html = html_path.read_text(encoding="utf-8")
    print(f"Extracted links: {extract_links(html, base)}")

if __name__ == "__main__":
    main()