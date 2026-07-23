"""The LangGraph state machine for Site Doctor.

Week 1 goal: get crawl_node -> audit_node working end to end.
Everything past that (triage/fix/approve/apply/reaudit) is stubbed
so you can see the intended shape and fill it in incrementally.
"""

from langgraph.graph import StateGraph, END

from models.schemas import SiteDoctorState
from crawler.crawl import crawl_page, screenshot_page
from audit.lighthouse import audit_url
from ux_review.vision_review import review_screenshots


# ---- Nodes ----

def _parse_selected_checks(raw_answer: str) -> list[str]:
    if not raw_answer.strip():
        return ["seo", "ux"]

    normalized = raw_answer.lower().replace(",", " ")
    tokens = normalized.split()

    if "all" in tokens:
        return ["seo", "ux", "security"]

    selected_checks = []
    for check in ("seo", "ux", "security"):
        if check in tokens:
            selected_checks.append(check)

    return selected_checks or ["seo", "ux"]


def check_selection_node(state: SiteDoctorState) -> dict:
    """Prompt for which checks to run before the crawl starts."""
    raw_answer = input("Which checks to run? [seo, ux, security] default: seo ux: ")
    selected_checks = _parse_selected_checks(raw_answer)
    print(f"selected_checks={selected_checks}")
    return {"selected_checks": selected_checks}

def crawl_node(state: SiteDoctorState) -> dict:
    print("node: crawl")
    local_path = crawl_page(state.url)
    if "ux" in state.selected_checks:
        screenshot_paths = screenshot_page(state.url)
    else:
        screenshot_paths = []
    return {"local_copy_path": local_path, "screenshot_paths": screenshot_paths}


def seo_audit_node(state: SiteDoctorState) -> dict:
    # v1: audit the live URL directly. Once fixes exist, point this at
    # a local static server serving local_copy_path instead.
    print("node: seo_audit")
    result = audit_url(state.url)
    return {"audit_before": result}


def ux_review_node(state: SiteDoctorState) -> dict:
    print("node: ux_review")
    screenshot_paths = state.screenshot_paths or screenshot_page(state.url)
    suggestions = review_screenshots(screenshot_paths)
    return {"ux_suggestions": suggestions}


def security_audit_node(state: SiteDoctorState) -> dict:
    """TODO: passive security checks (headers, TLS, exposed version/CVE
    lookups). Only runs if explicitly opted into via selected_checks."""
    print("node: security_audit")
    return {}


def route_checks(state: SiteDoctorState) -> list[str]:
    mapping = {"seo": "seo_audit", "ux": "ux_review", "security": "security_audit"}
    return [mapping[check] for check in state.selected_checks if check in mapping]


def triage_node(state: SiteDoctorState) -> dict:
    """TODO (Week 2): call Claude to rank state.audit_before.issues by
    severity and fix_confidence, and fill in plain_language_summary
    for each. UX suggestions already carry their own recommendation, so
    they pass through unchanged for v1."""
    print("node: triage")
    return {}


def fix_node(state: SiteDoctorState) -> dict:
    """TODO (Week 3-4): for each issue above a confidence threshold,
    call Claude to generate a Fix (before/after snippet) and append
    to state.fixes."""
    return {}


def approve_node(state: SiteDoctorState) -> dict:
    """TODO (Week 5): surface state.fixes to the user (via the
    Streamlit UI) and wait for approval on each. This is a natural
    LangGraph `interrupt` point for human-in-the-loop."""
    return {}


def apply_node(state: SiteDoctorState) -> dict:
    """TODO (Week 5): write approved fixes into the local HTML copy."""
    return {}


def reaudit_node(state: SiteDoctorState) -> dict:
    """TODO (Week 6): re-run the audit against the patched local copy,
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
    graph.add_conditional_edges("crawl", route_checks, ["seo_audit", "ux_review", "security_audit"])
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
    import sys

    def render_report(state: SiteDoctorState) -> str:
        lines = []
        lines.append("Issues Found")
        if state.audit_before and state.audit_before.issues:
            for issue in state.audit_before.issues:
                summary = issue.plain_language_summary or issue.description
                lines.append(f"- [{issue.severity.value if issue.severity else 'unrated'}] {issue.title}: {summary}")
        else:
            lines.append("- None")

        lines.append("")
        lines.append("Usability & Conversion Suggestions")
        if state.ux_suggestions:
            for suggestion in state.ux_suggestions:
                lines.append(
                    f"- [{suggestion.severity.value}] {suggestion.category}: {suggestion.observation} {suggestion.recommendation}"
                )
        else:
            lines.append("- None")

        return "\n".join(lines)

    app = build_graph()
    target = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    final_state = SiteDoctorState.model_validate(app.invoke(SiteDoctorState(url=target)))
    print(render_report(final_state))
