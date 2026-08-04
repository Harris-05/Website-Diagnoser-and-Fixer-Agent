"""Tests for crawler/utils.py -- the URL handling the BFS crawler depends on.

These are the functions with the most history of subtle bugs (hostname
spoofing, unresolved relative links), so they get the most coverage.
"""

import pytest

from crawler.utils import extract_links, is_internal_link, normalize_url, slugify


# ---- normalize_url ----

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://site.com/about/?ref=nav#top", "site.com/about"),
        ("https://site.com/", "site.com"),
        ("http://site.com/a/b/", "site.com/a/b"),
        ("https://site.com?q=1", "site.com"),
    ],
)
def test_normalize_url_strips_scheme_query_fragment_and_trailing_slash(raw, expected):
    """Two URLs that point at the same page must normalize identically --
    this string is the crawler's de-duplication key, so a mismatch here
    means the same page gets crawled twice."""
    assert normalize_url(raw) == expected


def test_normalize_url_requires_a_scheme():
    """Documents current behaviour, not desired behaviour: normalize_url
    does url.split("//")[1], so a scheme-less URL raises IndexError rather
    than being handled. Flagged in FINDINGS-FOR-HARIS.md -- if that gets
    changed deliberately, this test is expected to fail and should be
    updated then."""
    with pytest.raises(IndexError):
        normalize_url("site.com/about")


# ---- is_internal_link ----

def test_is_internal_link_accepts_same_host():
    assert is_internal_link("https://site.com/about", "https://site.com") is True


def test_is_internal_link_rejects_spoofed_prefix_host():
    """Regression test for a real fixed bug: the original implementation
    used startswith() on the whole URL, so "site.com.evil.com" matched
    "site.com" and an attacker-controlled domain counted as internal. The
    fix compares parsed hostnames for exact equality -- keep it that way."""
    assert is_internal_link("https://site.com.evil.com/x", "https://site.com") is False


def test_is_internal_link_rejects_plain_external_host():
    assert is_internal_link("https://other.com/x", "https://site.com") is False


def test_is_internal_link_ignores_hostname_case():
    assert is_internal_link("https://SITE.com/x", "https://site.com") is True


def test_is_internal_link_treats_a_different_port_as_external():
    """Documents current behaviour: the comparison is on netloc, which
    includes the port, so site.com:8080 is NOT internal to site.com. Worth
    knowing before running the crawler against a local dev server."""
    assert is_internal_link("https://site.com:8080/x", "https://site.com") is False


# ---- slugify ----

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://site.com/about-us/", "about-us"),
        ("https://site.com/a/b", "a-b"),
        ("/About_Us/", "about-us"),
    ],
)
def test_slugify_produces_filesystem_safe_names(raw, expected):
    assert slugify(raw) == expected


def test_slugify_falls_back_to_home_for_the_root_path():
    """An empty string is not a valid folder name, and the root page needs
    somewhere to live in the cache layout."""
    assert slugify("https://site.com/") == "home"
    assert slugify("https://site.com") == "home"


# ---- extract_links ----

SAMPLE_HTML = """
<html><body>
  <a href="/">Home</a>
  <a href="/about">About</a>
  <a href="/about/">About with trailing slash</a>
  <a href="https://site.com/contact?ref=nav">Contact</a>
  <a href="https://other.com/x">External site</a>
  <a href="mailto:hi@site.com">Email</a>
  <a href="tel:+1234">Phone</a>
  <a href="javascript:void(0)">Script</a>
  <a href="#section">In-page anchor</a>
  <a href="">Empty href</a>
</body></html>
"""


def test_extract_links_resolves_relative_hrefs_and_filters_correctly():
    """Covers three fixed/important behaviours at once:

    - relative "/about" is resolved against base_url BEFORE the internal
      check (an earlier version checked first and dropped every relative
      link)
    - external hosts and non-page schemes are excluded
    - /about and /about/ collapse to one entry via normalize_url

    Note the returned values are normalize_url() output, so they have no
    scheme -- the docstring in utils.py calls them "absolute", which is
    misleading. Asserting the real shape here.
    """
    links = extract_links(SAMPLE_HTML, "https://site.com")

    assert set(links) == {"site.com", "site.com/about", "site.com/contact"}


def test_extract_links_returns_no_duplicates():
    links = extract_links(SAMPLE_HTML, "https://site.com")
    assert len(links) == len(set(links))


def test_extract_links_on_html_with_no_anchors():
    """A page that renders its nav client-side can legitimately have zero
    <a href> tags -- must return an empty list, not raise."""
    assert extract_links("<html><body><p>hi</p></body></html>", "https://site.com") == []
