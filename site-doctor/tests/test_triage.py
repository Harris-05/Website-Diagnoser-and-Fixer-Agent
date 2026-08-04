"""Tests for triage/engine.py -- everything except the one LLM call.

triage_lighthouse_issues() itself makes a network call, so it is not
tested here. But the parts around it are pure, and two of them are exactly
where this module's known bugs lived:

  - the prompt's literal-JSON braces crashing str.format()
  - aggregate_for_llm()'s per-page key colliding across pages

The second one is listed in the project notes as "fixed in code review,
still not confirmed working". These tests confirm it, with no API key and
no tokens spent.
"""

from triage.engine import (
    TRIAGE_PROMPT,
    _strip_code_fences,
    aggregate_for_llm,
    promote_high_severity_ux_suggestions,
    triage_security_findings,
)
from models.schemas import AuditResult, Category, Issue, Severity, UXSuggestion


def _issue(issue_id, category=Category.SEO, title="t", description="d"):
    return Issue(id=issue_id, category=category, title=title, description=description)


# ---- the prompt template ----

def test_triage_prompt_formats_without_raising():
    """Regression test for a bug that killed a live run: the prompt embeds
    a literal JSON example, and str.format() treats every { } as a
    placeholder. The literal braces must stay doubled ({{ }}) so only
    {issues_json} is substituted."""
    rendered = TRIAGE_PROMPT.format(issues_json="[]")

    assert "[]" in rendered


def test_triage_prompt_renders_its_json_example_as_real_single_braces():
    """The doubled braces are an escaping mechanism, not literal output --
    the model must receive valid-looking JSON, i.e. single braces."""
    rendered = TRIAGE_PROMPT.format(issues_json="[]")

    assert '"issue-id-1": {"severity"' in rendered
    assert "{{" not in rendered
    assert "}}" not in rendered


# ---- _strip_code_fences ----

def test_strip_code_fences_removes_a_json_fenced_block():
    """Models wrap JSON in markdown fences even when told not to."""
    raw = '```json\n{"a": 1}\n```'
    assert _strip_code_fences(raw) == '{"a": 1}'


def test_strip_code_fences_removes_an_unlabelled_fence():
    assert _strip_code_fences('```\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_code_fences_leaves_bare_json_alone():
    assert _strip_code_fences('  {"a": 1}  ') == '{"a": 1}'


# ---- aggregate_for_llm ----

def test_aggregate_for_llm_keeps_same_audit_id_on_different_pages_distinct():
    """THE important one. "heading-order" recurs on most pages of a site.
    Keying by the bare Lighthouse audit id collapsed those into a single
    entry, silently losing every page's copy but one. The key is a
    composite "url::audit_id" instead."""
    audits = [
        AuditResult(url="https://site.com", issues=[_issue("heading-order")]),
        AuditResult(url="https://site.com/about", issues=[_issue("heading-order")]),
    ]

    flattened = aggregate_for_llm(audits)

    assert len(flattened) == 2
    assert {entry["id"] for entry in flattened} == {
        "https://site.com::heading-order",
        "https://site.com/about::heading-order",
    }


def test_aggregate_for_llm_sends_only_filtered_fields():
    """Never send raw tool output to an LLM: only id/title/description/
    category/source_url may leave this function."""
    audits = [
        AuditResult(
            url="https://site.com",
            issues=[_issue("canonical", title="No canonical", description="why")],
        )
    ]

    entry = aggregate_for_llm(audits)[0]

    assert set(entry) == {"id", "title", "description", "category", "source_url"}
    assert entry["category"] == "seo"  # plain string, not the enum object
    assert entry["source_url"] == "https://site.com"


def test_aggregate_for_llm_on_no_findings():
    assert aggregate_for_llm([]) == []
    assert aggregate_for_llm([AuditResult(url="https://site.com")]) == []


# ---- triage_security_findings ----

def test_security_findings_are_never_marked_auto_fixable():
    """Security findings are HTTP headers and TLS config -- server-level
    settings that editing a local HTML copy cannot fix. fix_confidence is
    forced to 0.0 so no downstream auto-fix threshold ever picks them up."""
    findings = [_issue("missing-hsts", category=Category.SECURITY)]

    triaged = triage_security_findings(findings, "https://site.com")

    assert triaged[0].fix_confidence == 0.0
    assert triaged[0].source == "security"


def test_security_findings_fall_back_to_the_home_url():
    findings = [_issue("missing-hsts", category=Category.SECURITY)]

    triaged = triage_security_findings(findings, "https://site.com")

    assert triaged[0].source_url == "https://site.com"


def test_security_findings_keep_their_own_source_url_if_set():
    finding = _issue("missing-hsts", category=Category.SECURITY)
    finding.source_url = "https://site.com/login"

    triaged = triage_security_findings([finding], "https://site.com")

    assert triaged[0].source_url == "https://site.com/login"


def test_security_findings_get_a_plain_language_summary():
    findings = [_issue("missing-hsts", category=Category.SECURITY, description="no HSTS")]

    triaged = triage_security_findings(findings, "https://site.com")

    assert triaged[0].plain_language_summary == "no HSTS"


# ---- promote_high_severity_ux_suggestions ----

def _ux(suggestion_id, severity):
    return UXSuggestion(
        id=suggestion_id,
        category="clutter",
        severity=severity,
        observation="The hero section has six competing buttons",
        recommendation="Reduce to one primary call to action",
        page_url="https://site.com",
    )


def test_only_high_severity_ux_suggestions_are_promoted():
    """Deliberate design choice: medium and low UX suggestions stay
    report-only and never enter the fix pipeline."""
    suggestions = [
        _ux("ux-1", Severity.HIGH),
        _ux("ux-2", Severity.MEDIUM),
        _ux("ux-3", Severity.LOW),
    ]

    promoted = promote_high_severity_ux_suggestions(suggestions)

    assert [issue.id for issue in promoted] == ["promoted-ux-1"]


def test_promoted_ux_issues_carry_ux_category_and_low_confidence():
    """UX findings are judgment calls with no mechanical pass/fail check,
    so a low fix_confidence keeps them below any auto-fix threshold."""
    promoted = promote_high_severity_ux_suggestions([_ux("ux-1", Severity.HIGH)])
    issue = promoted[0]

    assert issue.category is Category.UX
    assert issue.source == "ux"
    assert issue.fix_confidence == 0.1
    assert issue.severity is Severity.HIGH
    assert issue.source_url == "https://site.com"


def test_promoted_ux_issue_maps_observation_and_recommendation():
    promoted = promote_high_severity_ux_suggestions([_ux("ux-1", Severity.HIGH)])
    issue = promoted[0]

    assert issue.title == "The hero section has six competing buttons"
    assert issue.description == "Reduce to one primary call to action"
    assert issue.plain_language_summary == issue.title


def test_promotion_threshold_can_be_widened():
    """threshold is a parameter, so medium can be included deliberately --
    but HIGH stays the default."""
    suggestions = [_ux("ux-1", Severity.HIGH), _ux("ux-2", Severity.MEDIUM)]

    promoted = promote_high_severity_ux_suggestions(suggestions, threshold=Severity.MEDIUM)

    assert {issue.id for issue in promoted} == {"promoted-ux-1", "promoted-ux-2"}


def test_promoting_nothing_returns_an_empty_list():
    assert promote_high_severity_ux_suggestions([]) == []
    assert promote_high_severity_ux_suggestions([_ux("ux-1", Severity.LOW)]) == []
