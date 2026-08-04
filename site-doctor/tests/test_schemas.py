"""Tests for models/schemas.py -- the contract every LangGraph node shares.

Cheap to test and high value: if a default or a required field silently
changes shape, the failure otherwise shows up several nodes downstream as
something confusing.
"""

from datetime import timezone

import pytest
from pydantic import ValidationError

from models.schemas import (
    AuditResult,
    Category,
    CrawlResult,
    Issue,
    PageResult,
    Severity,
    SiteDoctorState,
    UXSuggestion,
)


# ---- Issue ----

def test_issue_requires_its_core_fields():
    with pytest.raises(ValidationError):
        Issue(id="document-title")  # missing category/title/description


def test_issue_rejects_an_unknown_category():
    """Category is an enum specifically so a typo fails loudly at the
    boundary instead of flowing through the pipeline as a bad string."""
    with pytest.raises(ValidationError):
        Issue(
            id="x",
            category="not-a-real-category",
            title="t",
            description="d",
        )


def test_issue_defaults():
    issue = Issue(id="canonical", category=Category.SEO, title="t", description="d")

    assert issue.source == "lighthouse"
    assert issue.severity is None
    assert issue.fix_confidence is None
    assert issue.plain_language_summary is None
    assert issue.suggested_solution is None
    assert issue.solution_sources == []


def test_issue_solution_sources_is_not_shared_between_instances():
    """Guards the classic mutable-default bug: if solution_sources were a
    plain [] instead of default_factory=list, appending to one Issue's
    sources would silently append to every Issue's."""
    first = Issue(id="a", category=Category.SEO, title="t", description="d")
    second = Issue(id="b", category=Category.SEO, title="t", description="d")

    first.solution_sources.append("https://example.com")

    assert second.solution_sources == []


def test_issue_rejects_an_unknown_source():
    with pytest.raises(ValidationError):
        Issue(
            id="x",
            category=Category.SEO,
            title="t",
            description="d",
            source="lighthouse-ish",
        )


# ---- UXSuggestion ----

def test_ux_suggestion_requires_a_valid_severity():
    with pytest.raises(ValidationError):
        UXSuggestion(
            id="ux-1",
            category="clutter",
            severity="catastrophic",
            observation="o",
            recommendation="r",
        )


def test_ux_suggestion_page_url_is_optional():
    suggestion = UXSuggestion(
        id="ux-1",
        category="clutter",
        severity=Severity.HIGH,
        observation="o",
        recommendation="r",
    )
    assert suggestion.page_url is None


# ---- CrawlResult ----

def test_crawled_at_is_timezone_aware_and_evaluated_per_instance():
    """Regression test for a real fixed bug: default_factory was once given
    datetime.utcnow() -- the *called* result -- which freezes one timestamp
    at import time and reuses it for every instance forever. It must be a
    deferred callable, and the value must carry a timezone."""
    first = CrawlResult(crawl_id="a", start_url="https://site.com")
    second = CrawlResult(crawl_id="b", start_url="https://site.com")

    assert first.crawled_at.tzinfo is timezone.utc
    # separate instances must not share one frozen datetime object
    assert first.crawled_at is not second.crawled_at


def test_crawl_result_defaults_to_no_pages():
    result = CrawlResult(crawl_id="a", start_url="https://site.com")
    assert result.pages == []


def test_page_result_screenshots_default_empty():
    """Screenshots are only captured when UX review is selected, so an
    empty list is the normal SEO-only case, not a failure."""
    page = PageResult(url="https://site.com", slug="home", html_path="p.html")

    assert page.screenshot_paths == []
    assert page.depth == 0


# ---- AuditResult ----

def test_audit_result_defaults():
    result = AuditResult(url="https://site.com")
    assert result.scores == {}
    assert result.issues == []


# ---- SiteDoctorState ----

def test_state_requires_a_url():
    with pytest.raises(ValidationError):
        SiteDoctorState()


def test_state_defaults_match_the_crawler_defaults():
    """max_depth/max_pages here must stay in step with crawl_site()'s own
    defaults, so a standalone crawler run and a full graph run behave the
    same on blank input."""
    state = SiteDoctorState(url="https://site.com")

    assert state.selected_checks == ["seo", "ux"]
    assert state.max_depth == 2
    assert state.max_pages == 10
    assert state.max_retries_per_fix == 2


def test_state_starts_with_every_result_field_empty():
    state = SiteDoctorState(url="https://site.com")

    assert state.crawl_result is None
    assert state.audit_before == []
    assert state.audit_after == []
    assert state.ux_suggestions == []
    assert state.security_findings == []
    assert state.triaged_issues == []
    assert state.fixes == []
    assert state.report_path is None
