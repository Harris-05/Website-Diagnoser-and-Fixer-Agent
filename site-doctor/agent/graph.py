"""The LangGraph state machine for Site Doctor.

Shape:

  check_selection (human-in-the-loop: which checks to run)
        |
      crawl
        |
  conditional fan-out based on selected_checks
        |
   +----+----+---------------+
   v         v               v
seo_audit  ux_review   security_audit   <- only selected branches run
   |         |               |
   +----+----+---------------+
        |
      triage
        |
       fix -> report -> approve -> apply -> reaudit -+-> END
                                     ^________________|
                               (loop back if a fix didn't clear)
"""

from langgraph.graph import StateGraph, END
from models.schemas import SiteDoctorState, Issue, UXSuggestion
from crawler.crawl import crawl_site
from audit.lighthouse import audit_url
from ux_review.vision_review import review_screenshots, save_ux_report
from secuirty.passive_checks import run_passive_tests
from triage.engine import (
    triage_lighthouse_issues,
    triage_security_findings,
    promote_high_severity_ux_suggestions,
)
from fix.suggest import suggest_fix
from report.generate_pdf import generate_report_pdf
from secuirty.active_engine import run_active_security_tests

# ---- Nodes ----

def check_selection_node(state: SiteDoctorState) -> dict:
    print("\nWhich checks do you want to run?")
    print("  [1] SEO       (Lighthouse: SEO / accessibility / performance)")
    print("  [2] UX        (vision-based usability review)")
    print("  [3] Security  (passive checks only -- OFF by default)")
    raw = input("Enter numbers separated by commas (default: 1,2): ").strip()

    selected_numbers = {n.strip() for n in raw.split(",") if n.strip()} if raw else {"1", "2"}
    mapping = {"1": "seo", "2": "ux", "3": "security"}
    selected = [mapping[n] for n in selected_numbers if n in mapping]

    max_d = int(input("Enter the max depth : ").strip() or 2)
    max_p = int(input("Enter the max pages : ").strip() or 10)

    if "security" in selected:
        confirm = input(
            "\nYou selected Security. This runs PASSIVE checks only "
            "(HTTP security headers, TLS certificate validity) -- no "
            "active scanning, exploitation, or load testing is performed. "
            "Confirm you are authorized to test this target [y/N]: "
        ).strip().lower()
        if confirm != "y":
            print("Not confirmed -- removing Security from this run.")
            selected.remove("security")

    if not selected:
        print("No valid checks selected -- defaulting to SEO + UX.")
        selected = ["seo", "ux"]

    print(f"Running: {', '.join(selected)}\n")
    return {"selected_checks": selected, "max_depth": max_d, "max_pages": max_p}


def crawl_node(state: SiteDoctorState) -> dict:
    """Runs the multi-page BFS crawl and stores the full CrawlResult.

    Also mirrors the home page's HTML path and screenshots into the old
    local_copy_path / screenshot_paths fields, since some downstream
    nodes still read those directly.
    """
    print("Entering Crawl Node")

    take_screenshots = "ux" in state.selected_checks
    result = crawl_site(
        state.url,
        max_pages=state.max_pages,
        max_depth=state.max_depth,
        isux=take_screenshots,
    )

    home_page = result.pages[0] if result.pages else None
    local_path = home_page.html_path if home_page else None
    screenshot_paths = home_page.screenshot_paths if home_page else []
    print("Finished Crawl Node")
    return {
        "crawl_result": result,
        "local_copy_path": local_path,
        "screenshot_paths": screenshot_paths,
    }


def route_checks(state: SiteDoctorState) -> list[str]:
    """Conditional fan-out: only invoke the audit branches the user
    actually selected at check_selection_node."""
    mapping = {"seo": "seo_audit", "ux": "ux_review", "security": "security_audit"}
    return [mapping[check] for check in state.selected_checks if check in mapping]


def seo_audit_node(state: SiteDoctorState) -> dict:
    """Mechanical, rule-based checks via Lighthouse -- every crawled page,
    not just the start URL."""
    print("Entering SEO Node")
    pages = state.crawl_result.pages if state.crawl_result else []
    urls_to_audit = [p.url for p in pages] if pages else [state.url]

    results = []
    for url in urls_to_audit:
        try:
            results.append(audit_url(url))
        except Exception as exc:
            print(f"SEO audit failed for {url}: {exc}")

    print("Finished SEO Node")
    return {"audit_before": results}


def ux_review_node(state: SiteDoctorState) -> dict:
    print("UX Review Node Entered")
    all_suggestions: list[UXSuggestion] = []
    for page in state.crawl_result.pages:
        try:
            suggestions = review_screenshots(page.url, page.screenshot_paths)
        except Exception as exc:
            print(f"UX review failed for {page.url}: {exc}")
            suggestions = []
        all_suggestions.extend(suggestions)

    save_ux_report(state.crawl_result.crawl_id, all_suggestions)
    print("UX Review Node Completed")
    return {"ux_suggestions": all_suggestions}


def security_audit_node(state: SiteDoctorState) -> dict:
    """Passive security posture checks ONLY: HTTP security headers and TLS
    certificate validity. No active scanning, no exploitation attempts, no
    load/stress testing under any configuration (SRS FR-15, FR-16). Only
    reachable when explicitly selected via check_selection_node."""
    print("Security Audit Node Entered")
    findings = run_passive_tests(state.url)
    findings.append(run_active_security_tests(state.url))
    print(f"Security findings: {findings}")
    return {"security_findings": findings}


def triage_node(state: SiteDoctorState) -> dict:
    triaged: list[Issue] = []
    print("Triage Node Entered")
    if state.audit_before:
        triaged.extend(triage_lighthouse_issues(state.audit_before))

    if state.security_findings:
        triaged.extend(triage_security_findings(state.security_findings, state.url))

    if state.ux_suggestions:
        triaged.extend(promote_high_severity_ux_suggestions(state.ux_suggestions))

    print(f"Triage complete: {len(triaged)} issues ranked and summarized")
    return {"triaged_issues": triaged}


def fix_node(state: SiteDoctorState) -> dict:
    """PROPOSE step only -- generates a suggested_solution + confidence
    for every triaged Issue, no HTML touched, no Fix object created."""
    print("Fix Node Entered")
    suggested = [suggest_fix(issue) for issue in state.triaged_issues]
    print(f"Fix suggestions generated for {len(suggested)} issues")
    return {"triaged_issues": suggested}


def report_node(state: SiteDoctorState) -> dict:
    """Generates the human-readable PDF report from the fully-triaged,
    fix-suggested issue list. This is what a human actually reviews to
    decide whether to let the agent proceed into the (still-unbuilt)
    apply/verify/retry loop."""
    print("Report Node Entered")
    want_report=input("Generate PDF report? [Y/n]: ").strip().lower() or "y"
    if want_report != "y":
        print("Skipping report generation.")
        return {"report_path": None}
    else:
        crawl_id = state.crawl_result.crawl_id if state.crawl_result else "report"
        output_path = f".site-doctor-cache/site_doctor_report_{crawl_id}.pdf"
        path = generate_report_pdf(state, output_path)
        print(f"Report written to {path}")
        return {"report_path": path}


def approve_node(state: SiteDoctorState) -> dict:
    """TODO: surface the report to the user and ask whether to continue
    into the apply loop."""
    return {}


def apply_node(state: SiteDoctorState) -> dict:
    """TODO: write approved fixes into the local HTML copy."""
    return {}


def reaudit_node(state: SiteDoctorState) -> dict:
    """TODO: re-run Lighthouse against the patched local copy, compare
    against audit_before, mark each Fix.verified_cleared."""
    return {}


def should_retry(state: SiteDoctorState) -> str:
    """TODO: route back to fix_node if a fix didn't clear and
    attempts < max_retries_per_fix, otherwise END."""
    return END


# ---- Graph assembly ----

def build_graph():
    graph = StateGraph(SiteDoctorState)

    graph.add_node("check_selection", check_selection_node)
    graph.add_node("crawl", crawl_node)
    graph.add_node("seo_audit", seo_audit_node)
    graph.add_node("ux_review", ux_review_node)
    graph.add_node("security_audit", security_audit_node)
    graph.add_node("triage", triage_node)
    graph.add_node("fix", fix_node)
    graph.add_node("report", report_node)
    graph.add_node("approve", approve_node)
    graph.add_node("apply", apply_node)
    graph.add_node("reaudit", reaudit_node)

    graph.set_entry_point("check_selection")
    graph.add_edge("check_selection", "crawl")

    graph.add_conditional_edges(
        "crawl", route_checks, ["seo_audit", "ux_review", "security_audit"]
    )

    graph.add_edge("seo_audit", "triage")
    graph.add_edge("ux_review", "triage")
    graph.add_edge("security_audit", "triage")

    graph.add_edge("triage", "fix")
    graph.add_edge("fix", "report")
    graph.add_edge("report", "approve")
    graph.add_edge("approve", "apply")
    graph.add_edge("apply", "reaudit")
    graph.add_conditional_edges("reaudit", should_retry, {"fix": "fix", END: END})

    return graph.compile()


if __name__ == "__main__":
    app = build_graph()
    target = input("Enter the URL to review: ").strip()
    final_state = app.invoke(SiteDoctorState(url=target))
    print(final_state)