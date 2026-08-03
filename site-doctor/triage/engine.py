"""triage/engine.py

Ranks and plain-language-ifies mechanical Issues (Lighthouse + security),
and decides which high-severity UX suggestions get promoted into the fix
loop as low-confidence, surface-only Issues.

Never sends raw Lighthouse/tool output to the LLM -- only the already-
filtered Issue fields (id, title, description, category) go into the
prompt.
"""

from __future__ import annotations

import json
import os
import re
from dotenv import load_dotenv
from openai import OpenAI

from models.schemas import AuditResult, Category, Issue, Severity, UXSuggestion

load_dotenv()

TRIAGE_PROMPT = """You are triaging website audit findings for a non-technical
site owner. For each issue below, return:
- severity: "high", "medium", or "low" -- how much this actually hurts
  users/SEO/conversions, not just technical strictness.
- plain_language_summary: one or two plain-English sentences a non-technical
  person would understand, explaining what's wrong and why it matters.
- fix_confidence: a number 0.0-1.0 for how safely this can be auto-fixed by
  editing the page's HTML alone, with NO human design judgment required.
  Simple, unambiguous fixes (missing meta description, missing alt text,
  missing canonical tag) should score high (0.7-1.0). Anything requiring a
  visual/design decision (color contrast, heading restructuring) should
  score low (0.0-0.3).

Return ONLY valid JSON in this shape, one entry per issue id:
{{
  "issue-id-1": {{"severity": "high", "plain_language_summary": "...", "fix_confidence": 0.9}},
  "issue-id-2": {{"severity": "low", "plain_language_summary": "...", "fix_confidence": 0.2}}
}}

Issues to triage:
{issues_json}
"""


def _strip_code_fences(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text.strip()


def aggregate_for_llm(audit_results: list[AuditResult]) -> list[dict]:
    """Flattens per-page AuditResults into one list of already-filtered
    issue summaries -- id/title/description/category only, never raw
    Lighthouse JSON.

    Uses a composite "url::audit_id" as the "id" sent to the LLM, NOT the
    bare Lighthouse audit id -- the same audit id (e.g. "heading-order")
    commonly recurs across multiple pages, so a bare id would collide and
    silently drop/merge distinct per-page issues. The real Issue.id stays
    untouched (still the raw Lighthouse audit key) since reaudit_node
    needs that later to know which specific check to re-run."""
    flattened = []
    for result in audit_results:
        for issue in result.issues:
            flattened.append(
                {
                    "id": f"{result.url}::{issue.id}",
                    "title": issue.title,
                    "description": issue.description,
                    "category": issue.category.value,
                    "source_url": result.url,
                }
            )
    return flattened


def triage_lighthouse_issues(audit_before: list[AuditResult]) -> list[Issue]:
    """Flattens audit_before, calls gpt-4o-mini once to rank + summarize
    every issue in a single batch call, and returns fully-populated Issue
    objects (source_url stamped, severity/plain_language_summary/
    fix_confidence filled in)."""
    flattened = aggregate_for_llm(audit_before)
    if not flattened:
        return []

    # keyed by the same composite "url::audit_id" used above -- see
    # aggregate_for_llm's docstring for why a bare issue.id is unsafe here
    issue_lookup: dict[str, tuple[Issue, str]] = {}
    for result in audit_before:
        for issue in result.issues:
            composite_key = f"{result.url}::{issue.id}"
            issue_lookup[composite_key] = (issue, result.url)

    prompt = TRIAGE_PROMPT.format(issues_json=json.dumps(flattened, indent=2))
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        response_format={"type": "json_object"},
        )
    except Exception as exc:
        print(f"LLM triage call failed: {exc}")
        return []
    raw_text = response.choices[0].message.content or "{}"
    triage_results = json.loads(_strip_code_fences(raw_text))

    triaged: list[Issue] = []
    for composite_key, (issue, url) in issue_lookup.items():
        result = triage_results.get(composite_key, {})
        issue.severity = Severity(result.get("severity", "low"))
        issue.plain_language_summary = result.get(
            "plain_language_summary", issue.description
        )
        issue.fix_confidence = float(result.get("fix_confidence", 0.0))
        issue.source_url = url
        issue.source = "lighthouse"
        triaged.append(issue)

    # highest severity first
    severity_order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
    triaged.sort(key=lambda i: severity_order.get(i.severity, 3))
    return triaged


def triage_security_findings(security_findings: list[Issue], home_url: str) -> list[Issue]:
    """Security Issues already carry a severity and a human-readable
    title/description from security_audit_node -- no LLM call needed.
    Just stamps source/source_url and a low fix_confidence, since headers
    and TLS config are server-level settings, NOT something fixable by
    editing the local HTML copy the way Lighthouse issues are."""
    for finding in security_findings:
        finding.source = "security"
        finding.source_url = finding.source_url or home_url
        finding.fix_confidence = 0.0  # never auto-fixable via HTML patch
        if not finding.plain_language_summary:
            finding.plain_language_summary = finding.description
    return security_findings


def promote_high_severity_ux_suggestions(
    ux_suggestions: list[UXSuggestion],
    threshold: Severity = Severity.HIGH,
) -> list[Issue]:
    severity_rank = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
    promoted = []
    for suggestion in ux_suggestions:
        if severity_rank.get(suggestion.severity, 3) <= severity_rank[threshold]:
            promoted.append(
                Issue(
                    id=f"promoted-{suggestion.id}",   # <-- was f"ux-{suggestion.id}"
                    category=Category.UX,             # <-- was Category.ACCESSIBILITY
                    title=suggestion.observation,
                    description=suggestion.recommendation,
                    plain_language_summary=suggestion.observation,
                    severity=suggestion.severity,
                    fix_confidence=0.1,
                    source_url=suggestion.page_url,
                    source="ux",
                )
            )
    return promoted