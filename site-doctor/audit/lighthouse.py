"""Runs Lighthouse against a URL (or local file server) and parses the
JSON report into our Issue/AuditResult schema.

Requires: npm install -g lighthouse
"""

import json
import subprocess
from pathlib import Path

from models.schemas import AuditResult, Category, Issue

# Lighthouse audit IDs we care about for v1, mapped to our categories.
# (Not exhaustive — expand as you add more fix types.)
TRACKED_AUDITS = {
    "document-title": Category.SEO,
    "meta-description": Category.SEO,
    "image-alt": Category.ACCESSIBILITY,
    "heading-order": Category.ACCESSIBILITY,
    "canonical": Category.SEO,
    "color-contrast": Category.ACCESSIBILITY,
    "uses-optimized-images": Category.PERFORMANCE,
    "structured-data": Category.SEO,
}


def run_lighthouse(url: str) -> dict:
    """Runs the Lighthouse CLI and returns the parsed JSON report."""
    report_path = Path("./.site-doctor-cache/lighthouse-report.json")
    report_path.parent.mkdir(exist_ok=True)

    subprocess.run(
        [
            "lighthouse",
            url,
            "--output=json",
            f"--output-path={report_path}",
            "--chrome-flags=--headless",
            "--quiet",
        ],
        check=True,
    )

    return json.loads(report_path.read_text())


def parse_report(raw: dict, url: str) -> AuditResult:
    scores = {
        Category.SEO: raw["categories"]["seo"]["score"] * 100,
        Category.ACCESSIBILITY: raw["categories"]["accessibility"]["score"] * 100,
        Category.PERFORMANCE: raw["categories"]["performance"]["score"] * 100,
    }

    issues = []
    for audit_id, category in TRACKED_AUDITS.items():
        audit = raw["audits"].get(audit_id)
        if audit and audit.get("score") is not None and audit["score"] < 1:
            issues.append(
                Issue(
                    id=audit_id,
                    category=category,
                    title=audit["title"],
                    description=audit.get("description", ""),
                )
            )

    return AuditResult(url=url, scores=scores, issues=issues)


def audit_url(url: str) -> AuditResult:
    raw = run_lighthouse(url)
    return parse_report(raw, url)


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    result = audit_url(target)
    print(result.model_dump_json(indent=2))
