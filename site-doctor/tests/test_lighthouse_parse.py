"""Tests for audit/lighthouse.py's parse_report().

parse_report is the pure part of the Lighthouse integration: raw report
dict -> AuditResult. No subprocess, no Chrome, no Node needed, so it is
testable in CI with a small hand-written fake report.

Only the audit IDs in TRACKED_AUDITS are supposed to survive parsing --
that allowlist is what keeps Lighthouse's ~11,000-line raw report from
ever reaching an LLM call.
"""

import pytest

from audit.lighthouse import parse_report
from models.schemas import Category


FAKE_REPORT = {
    "categories": {
        "seo": {"score": 0.72},
        "accessibility": {"score": 0.81},
        "performance": {"score": 0.9},
    },
    "audits": {
        # failing outright -> becomes an Issue
        "document-title": {
            "score": 0,
            "title": "Document doesn't have a <title> element",
            "description": "The title gives screen reader users an overview.",
        },
        # partial failure -> still an Issue (anything below 1 counts)
        "heading-order": {
            "score": 0.5,
            "title": "Heading elements are not in a sequentially-descending order",
            "description": "Properly ordered headings convey structure.",
        },
        # passing -> must NOT become an Issue
        "image-alt": {
            "score": 1,
            "title": "Image elements have [alt] attributes",
            "description": "Informative elements should have short alt text.",
        },
        # not applicable to this page -> must NOT become an Issue
        "meta-description": {
            "score": None,
            "title": "Document does not have a meta description",
            "description": "Meta descriptions may be included in search results.",
        },
        # not in TRACKED_AUDITS -> must be discarded entirely
        "total-byte-weight": {
            "score": 0.1,
            "title": "Avoids enormous network payloads",
            "description": "Large payloads cost users money.",
        },
    },
}


def test_scores_are_converted_to_percentages():
    """Lighthouse reports scores as 0-1 floats; the rest of the app shows
    them as 0-100."""
    result = parse_report(FAKE_REPORT, "https://site.com")

    assert result.scores[Category.SEO] == pytest.approx(72.0)
    assert result.scores[Category.ACCESSIBILITY] == pytest.approx(81.0)
    assert result.scores[Category.PERFORMANCE] == pytest.approx(90.0)


def test_url_is_stamped_onto_the_result():
    """Each page's AuditResult has to know which page it came from --
    triage later flattens all of them into one list."""
    result = parse_report(FAKE_REPORT, "https://site.com/pricing")
    assert result.url == "https://site.com/pricing"


def test_only_failing_tracked_audits_become_issues():
    result = parse_report(FAKE_REPORT, "https://site.com")

    found = {issue.id for issue in result.issues}
    assert found == {"document-title", "heading-order"}

    # passing (score 1) and not-applicable (score None) are excluded
    assert "image-alt" not in found
    assert "meta-description" not in found
    # untracked audit IDs never survive the allowlist
    assert "total-byte-weight" not in found


def test_issues_get_the_category_from_the_tracked_audits_map():
    result = parse_report(FAKE_REPORT, "https://site.com")
    by_id = {issue.id: issue for issue in result.issues}

    assert by_id["document-title"].category is Category.SEO
    assert by_id["heading-order"].category is Category.ACCESSIBILITY


def test_missing_category_is_omitted_rather_than_crashing():
    """audit_url() retries with --only-categories=seo,accessibility when a
    page hits Lighthouse's NO_LCP error, so the performance category is
    genuinely absent from the report on that path. It must be omitted from
    scores, not raise or default to 0."""
    report = {
        "categories": {"seo": {"score": 0.5}, "accessibility": {"score": 0.6}},
        "audits": {},
    }

    result = parse_report(report, "https://site.com")

    assert Category.PERFORMANCE not in result.scores
    assert result.scores[Category.SEO] == pytest.approx(50.0)


def test_empty_report_produces_an_empty_result_not_an_error():
    result = parse_report({}, "https://site.com")

    assert result.scores == {}
    assert result.issues == []


def test_description_defaults_to_empty_string_when_absent():
    report = {
        "categories": {},
        "audits": {"canonical": {"score": 0, "title": "Document has no canonical"}},
    }

    result = parse_report(report, "https://site.com")

    assert result.issues[0].description == ""
