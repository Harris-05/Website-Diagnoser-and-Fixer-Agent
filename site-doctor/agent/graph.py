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
       fix -> approve -> apply -> reaudit -+-> END
                          ^________________|
                    (loop back if a fix didn't clear)
"""

from datetime import datetime, timezone
from langgraph.graph import StateGraph, END
from models.schemas import SiteDoctorState, Issue, Category, Severity, UXSuggestion, AuditResult
from crawler.crawl import crawl_site
from audit.lighthouse import audit_url
from ux_review.vision_review import review_screenshots,save_ux_report
from secuirty.passive_checks import run_passive_tests
from triage.engine import triage_lighthouse_issues, triage_security_findings, promote_high_severity_ux_suggestions
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
            "\nYou selected Security. Confirm you are authorized to test this target "
            "[y/N]: "
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
    local_copy_path / screenshot_paths fields, since seo_audit_node and
    ux_review_node haven't been migrated to read from crawl_result yet --
    this keeps the rest of the graph working unchanged while that
    migration happens incrementally.
    """
    print("Entering Crawl Node")

    if "ux" in state.selected_checks:
        #Only take screenshots if UX review is selected
        result = crawl_site(state.url, max_pages=state.max_pages, max_depth=state.max_depth,isux=True)
    else:
        result=crawl_site(state.url, max_pages=state.max_pages, max_depth=state.max_depth,isux=False)

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
    """Mechanical, rule-based checks via Lighthouse. Ground-truth verifiable —
    these issues go through the fix/verify/retry loop later.

    Audits EVERY page the crawler found, not just the start URL -- each
    AuditResult already carries its own .url, so downstream consumers
    (triage, report) can tell which page each issue came from without any
    extra bookkeeping.
    """
    print("Entering SEO Node ")
    pages = state.crawl_result.pages if state.crawl_result else []
    urls_to_audit = [p.url for p in pages] if pages else [state.url]

    results = []
    for url in urls_to_audit:
        try:
            results.append(audit_url(url))
        except Exception as exc:
            print(f"SEO audit failed for {url}: {exc}")

    print("Seo Audit Node")
    return {"audit_before": results}


def ux_review_node(state: SiteDoctorState) -> dict:
    print("UX Review Node Entered")
    all_suggestions: list[UXSuggestion] = []
    for page in state.crawl_result.pages:
        try:
            suggestions = review_screenshots(page.url, page.screenshot_paths)
        except Exception as e:
            print(f"UX review failed for {page.url}: {e}")
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
    return {"security_findings": findings}


def triage_node(state: SiteDoctorState) -> dict:
    """Combines Lighthouse issues, security findings, and auto-promoted
    high-severity UX suggestions into one ranked, human-readable,
    fix-loop-ready list. UX suggestions below the severity threshold and
    ALL security findings still appear in triaged_issues (for the report)
    but carry fix_confidence=0.0/low, so fix_node naturally treats them as
    surface-only recommendations rather than auto-fix candidates."""
    triaged: list[Issue] = []

    if state.audit_before:
        triaged.extend(triage_lighthouse_issues(state.audit_before))

    if state.security_findings:
        triaged.extend(
            triage_security_findings(state.security_findings, state.url)
        )

    if state.ux_suggestions:
        triaged.extend(
            promote_high_severity_ux_suggestions(state.ux_suggestions)
        )

    print(f"Triage complete: {len(triaged)} issues ranked and summarized")
    return {"triaged_issues": triaged}


def fix_node(state: SiteDoctorState) -> dict:
    """TODO (Week 3-4): for each Issue above a confidence threshold, call
    OpenAI to generate a Fix and append to state.fixes. UXSuggestions and
    security_findings are NOT run through this node — no mechanical
    fix/verify loop applies to judgment calls or infra-level findings."""
    return {}


def approve_node(state: SiteDoctorState) -> dict:
    """TODO (Week 5): surface state.fixes to the user and wait for approval."""
    return {}


def apply_node(state: SiteDoctorState) -> dict:
    """TODO (Week 5): write approved fixes into the local HTML copy."""
    return {}


def reaudit_node(state: SiteDoctorState) -> dict:
    """TODO (Week 6): re-run Lighthouse against the patched local copy,
    compare against audit_before, mark each Fix.verified_cleared."""
    return {}


def should_retry(state: SiteDoctorState) -> str:
    """TODO (Week 6): route back to fix_node if a fix didn't clear and
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
    graph.add_node("approve", approve_node)
    graph.add_node("apply", apply_node)
    graph.add_node("reaudit", reaudit_node)

    graph.set_entry_point("check_selection")
    graph.add_edge("check_selection", "crawl")

    # conditional fan-out: only the branches the user selected actually run
    graph.add_conditional_edges(
        "crawl", route_checks, ["seo_audit", "ux_review", "security_audit"]
    )

    # fan-in: triage waits for every branch that WAS invoked
    graph.add_edge("seo_audit", "triage")
    graph.add_edge("ux_review", "triage")
    graph.add_edge("security_audit", "triage")

    graph.add_edge("triage", "fix")
    graph.add_edge("fix", "approve")
    graph.add_edge("approve", "apply")
    graph.add_edge("apply", "reaudit")
    graph.add_conditional_edges("reaudit", should_retry, {"fix": "fix", END: END})

    return graph.compile()


if __name__ == "__main__":
    app = build_graph()
    target = input("Enter the URL to review: ").strip()
    final_state = app.invoke(SiteDoctorState(url=target))
    print(final_state)