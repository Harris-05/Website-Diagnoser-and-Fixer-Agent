"""Runs Lighthouse against a URL (or local file server) and parses the
JSON report into our Issue/AuditResult schema.

Requires: npm install -g lighthouse
"""

import hashlib
import json
import subprocess
from shutil import which
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


def run_lighthouse(url: str, categories: str = "seo,accessibility,performance") -> dict:
    """Runs the Lighthouse CLI and returns the parsed JSON report."""
    # unique filename per URL -- avoids every page's audit overwriting the
    # same shared report file, which is confusing to debug and would be a
    # real race condition if audits ever run concurrently
    url_hash = hashlib.sha1(f"{url}:{categories}".encode("utf-8")).hexdigest()[:10]
    report_path = Path(f"./.site-doctor-cache/lighthouse-report_{url_hash}.json")
    report_path.parent.mkdir(exist_ok=True)

    lighthouse_cmd = which("lighthouse") or which("lighthouse.cmd")
    if lighthouse_cmd is None:
        npx_cmd = which("npx") or which("npx.cmd")
    else:
        npx_cmd = None

    if lighthouse_cmd is None and npx_cmd is None:
        raise RuntimeError(
            "Could not find the Lighthouse CLI on PATH. Install it with "
            "`npm install -g lighthouse` or run through `npx --yes lighthouse ...`."
        )

    command = [lighthouse_cmd] if lighthouse_cmd is not None else [npx_cmd, "--yes", "lighthouse"]

    subprocess.run(
        [
            *command,
            url,
            "--output=json",
            f"--output-path={report_path}",
            f"--only-categories={categories}",
            # "=new" is required -- the legacy headless mode fails with
            # LanternError: NO_LCP on Windows for many real sites, since
            # it can't reliably compute a paint trace for the performance
            # category
            "--chrome-flags=--headless=new",
            "--quiet",
        ],
        check=True,
    )

    return json.loads(report_path.read_text(encoding="utf-8"))


def parse_report(raw: dict, url: str) -> AuditResult:
    scores = {}
    category_keys = {
        "seo": Category.SEO,
        "accessibility": Category.ACCESSIBILITY,
        "performance": Category.PERFORMANCE,
    }
    for key, category_enum in category_keys.items():
        cat_data = raw.get("categories", {}).get(key)
        # defensive: a category can be entirely absent from the report if
        # it was excluded via --only-categories (used by the performance
        # fallback in audit_url below), not just if the run failed
        if cat_data and cat_data.get("score") is not None:
            scores[category_enum] = cat_data["score"] * 100

    issues = []
    for audit_id, category in TRACKED_AUDITS.items():
        audit = raw.get("audits", {}).get(audit_id)
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
    try:
        raw = run_lighthouse(url)
    except subprocess.CalledProcessError:
        # Some pages hit LanternError: NO_LCP even with --headless=new --
        # Lighthouse's performance trace can't find a paint target on that
        # specific page. Rather than lose SEO/accessibility data too,
        # retry once without the performance category.
        print(f"Full audit failed for {url}, retrying without performance category...")
        raw = run_lighthouse(url, categories="seo,accessibility")

    return parse_report(raw, url)


if __name__ == "__main__":
    import sys
    target = input("Enter URL to audit: ").strip()
    result = audit_url(target)
    print(result.model_dump_json(indent=2))