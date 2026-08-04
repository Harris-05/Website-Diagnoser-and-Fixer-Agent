"""Non-interactive entry point for Site Doctor -- the one a container runs.

Why this file exists
--------------------
`python -m agent.graph` is interactive by design. Its entry node,
check_selection_node, calls input() three times, and report_node prompts
again mid-pipeline. A container has no keyboard, so that path would start
and then hang on stdin forever.

Rather than change agent/graph.py, this file builds its own graph out of
the SAME node functions and replaces only the two that prompt:

    check_selection_node  ->  config_node        (reads argparse instead)
    report_node           ->  headless_report_node (no y/n prompt)

Every other node -- crawl, seo_audit, ux_review, triage, fix -- is Haris's,
imported and used unchanged. approve/apply/reaudit are left out because all
three are stubs that return {} today, and should_retry always returns END.

Usage:
    python run_audit.py --url https://example.com --checks seo --max-pages 5
"""

import argparse
import os
import sys

from dotenv import load_dotenv

# Safe to import at module level: models/schemas.py and report/generate_pdf.py
# pull in pydantic and reportlab only. agent.graph is NOT safe here -- see the
# comment inside build_headless_graph().
from models.schemas import SiteDoctorState
from report.generate_pdf import generate_report_pdf

# "security" is deliberately absent -- see _parse_checks().
VALID_CHECKS = ("seo", "ux")


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="run_audit.py",
        description="Run a Site Doctor audit without any interactive prompts.",
    )
    parser.add_argument("--url", required=True, help="URL to audit, including scheme")
    parser.add_argument(
        "--checks",
        default="seo",
        help="comma-separated list of %s (default: seo)" % ",".join(VALID_CHECKS),
    )
    parser.add_argument("--max-pages", type=int, default=5, help="default: 5")
    parser.add_argument("--max-depth", type=int, default=1, help="default: 1")
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="skip PDF generation (the audit still runs)",
    )
    return parser.parse_args(argv)


def _parse_checks(raw: str) -> list[str]:
    """Validate --checks, and refuse 'security' with an explanation.

    security_audit_node currently calls run_active_security_tests(), which
    starts with require_verified() and raises PermissionError for any domain
    without a DNS TXT verification record -- so selecting security kills the
    whole run. That is a real problem in the pipeline, not something this
    runner should paper over, so it fails loudly here instead of producing a
    confusing traceback from three modules away. See FINDINGS-FOR-HARIS.md #1.
    """
    requested = [item.strip().lower() for item in raw.split(",") if item.strip()]

    if "security" in requested:
        raise ValueError(
            "The 'security' check is not available from this runner.\n"
            "security_audit_node calls run_active_security_tests(), which raises\n"
            "PermissionError on any domain without DNS verification -- it would\n"
            "crash the run. See FINDINGS-FOR-HARIS.md finding #1."
        )

    unknown = [item for item in requested if item not in VALID_CHECKS]
    if unknown:
        raise ValueError(
            "Unknown check(s): %s. Valid checks: %s"
            % (", ".join(unknown), ", ".join(VALID_CHECKS))
        )

    if not requested:
        raise ValueError("No checks selected. Pass at least one of: %s" % ", ".join(VALID_CHECKS))

    return requested


def make_config_node(selected_checks, max_depth, max_pages):
    """Build the node that stands in for check_selection_node, with no prompts.

    A factory rather than an inline closure so it can be called directly in a
    test, without reaching into LangGraph's compiled internals.
    """

    def config_node(state: SiteDoctorState) -> dict:
        # RETURNED, not assigned onto `state`. LangGraph ignores in-place
        # mutation of the state object and only picks up what a node returns --
        # exactly the bug recorded in CLAUDE.md section 4.
        return {
            "selected_checks": selected_checks,
            "max_depth": max_depth,
            "max_pages": max_pages,
        }

    return config_node


def make_report_node(want_report):
    """Build the node that replaces report_node's 'Generate PDF report? [Y/n]'
    prompt. Same generate_report_pdf() call, same output."""

    def headless_report_node(state: SiteDoctorState) -> dict:
        if not want_report:
            return {"report_path": None}

        crawl_id = state.crawl_result.crawl_id if state.crawl_result else "report"
        output_path = f".site-doctor-cache/site_doctor_report_{crawl_id}.pdf"
        return {"report_path": generate_report_pdf(state, output_path)}

    return headless_report_node


def build_headless_graph(selected_checks, max_depth, max_pages, want_report):
    """Compile a prompt-free version of the Site Doctor graph."""
    # Imported here rather than at module level on purpose: agent.graph imports
    # fix/suggest.py, which constructs an OpenAI client at import time. A
    # top-level import would make even `--help` fail when no API key is set.
    from langgraph.graph import END, StateGraph

    from agent.graph import (
        crawl_node,
        fix_node,
        route_checks,
        seo_audit_node,
        triage_node,
        ux_review_node,
    )

    graph = StateGraph(SiteDoctorState)

    graph.add_node("config", make_config_node(selected_checks, max_depth, max_pages))
    graph.add_node("crawl", crawl_node)
    graph.add_node("seo_audit", seo_audit_node)
    graph.add_node("ux_review", ux_review_node)
    graph.add_node("triage", triage_node)
    graph.add_node("fix", fix_node)
    graph.add_node("report", make_report_node(want_report))

    graph.set_entry_point("config")
    graph.add_edge("config", "crawl")
    # route_checks maps selected_checks -> node names. "security" can never
    # appear here because _parse_checks() rejects it before we get this far.
    graph.add_conditional_edges("crawl", route_checks, ["seo_audit", "ux_review"])
    graph.add_edge("seo_audit", "triage")
    graph.add_edge("ux_review", "triage")
    graph.add_edge("triage", "fix")
    graph.add_edge("fix", "report")
    graph.add_edge("report", END)

    return graph.compile()


def _print_summary(final_state: dict) -> None:
    """One block of output a log or CI run can be read back from."""
    crawl_result = final_state.get("crawl_result")
    pages = len(crawl_result.pages) if crawl_result else 0
    triaged = final_state.get("triaged_issues") or []
    report_path = final_state.get("report_path")

    print("\n--- Audit summary ---")
    print(f"Pages crawled:  {pages}")
    print(f"Issues triaged: {len(triaged)}")
    print(f"Report:         {report_path or 'not generated'}")


def main(argv=None) -> int:
    args = _parse_args(argv)
    load_dotenv()

    try:
        checks = _parse_checks(args.checks)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # Checked before building the graph so the failure is one clear line rather
    # than an OpenAI constructor error raised during an import.
    if not os.getenv("OPENAI_API_KEY"):
        print(
            "error: OPENAI_API_KEY is not set.\n"
            "The triage and fix steps need it. Pass it with "
            "`docker run -e OPENAI_API_KEY=...` or put it in a .env file.",
            file=sys.stderr,
        )
        return 2

    print(f"Auditing {args.url}")
    print(f"Checks: {', '.join(checks)} | max_pages={args.max_pages} max_depth={args.max_depth}")

    app = build_headless_graph(
        selected_checks=checks,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        want_report=not args.no_report,
    )

    try:
        final_state = app.invoke(SiteDoctorState(url=args.url))
    except Exception as exc:
        print(f"error: audit failed: {exc}", file=sys.stderr)
        return 1

    _print_summary(final_state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
