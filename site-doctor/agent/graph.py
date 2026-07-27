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

import socket
import ssl
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

from langgraph.graph import StateGraph, END

from models.schemas import SiteDoctorState, Issue, Category, Severity, UXSuggestion, AuditResult
from crawler.crawl import crawl_site
from audit.lighthouse import audit_url
from ux_review.vision_review import review_screenshots,save_ux_report


# ---- Nodes ----

def check_selection_node(state: SiteDoctorState) -> dict:
    """Human-in-the-loop entry point: ask which checks to run before any
    crawling begins. Security defaults to OFF and requires both explicit
    selection AND an authorization confirmation (SRS FR-03, FR-04, FR-14)."""
    print("\nWhich checks do you want to run?")
    print("  [1] SEO       (Lighthouse: SEO / accessibility / performance)")
    print("  [2] UX        (vision-based usability review)")
    print("  [3] Security  (passive checks only -- OFF by default)")
    raw = input("Enter numbers separated by commas (default: 1,2): ").strip()

    selected_numbers = {n.strip() for n in raw.split(",") if n.strip()} if raw else {"1", "2"}
    mapping = {"1": "seo", "2": "ux", "3": "security"}
    selected = [mapping[n] for n in selected_numbers if n in mapping]

    max_d=int(input("Enter the max depth : ").strip() or 2)

    max_p=int(input("Enter the max pages : ").strip() or 10)
    state.max_depth=max_d
    state.max_pages=max_p
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
    return {"selected_checks": selected}


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


_REQUIRED_SECURITY_HEADERS = {
    "strict-transport-security": (
        "Missing HSTS header (Strict-Transport-Security) -- allows "
        "connections to be downgraded to plain HTTP."
    ),
    "content-security-policy": (
        "Missing Content-Security-Policy header -- reduces protection "
        "against cross-site scripting and injection attacks."
    ),
    "x-content-type-options": (
        "Missing X-Content-Type-Options header -- browsers may MIME-sniff "
        "responses in unexpected ways."
    ),
    "x-frame-options": (
        "Missing X-Frame-Options header -- the page can potentially be "
        "embedded in a clickjacking iframe."
    ),
    "referrer-policy": (
        "Missing Referrer-Policy header -- full page URLs may leak to "
        "third parties via the Referer header."
    ),
}


def security_audit_node(state: SiteDoctorState) -> dict:
    """Passive security posture checks ONLY: HTTP security headers and TLS
    certificate validity. No active scanning, no exploitation attempts, no
    load/stress testing under any configuration (SRS FR-15, FR-16). Only
    reachable when explicitly selected via check_selection_node."""
    print("Security Audit Node Entered")
    parsed = urlparse(state.url)
    hostname = parsed.hostname
    findings: list[Issue] = []

    # --- HTTP security headers (passive: a single normal GET request) ---
    try:
        req = urllib.request.Request(
            state.url, method="GET", headers={"User-Agent": "SiteDoctor/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            headers = {k.lower(): v for k, v in resp.getheaders()}
    except Exception as exc:
        headers = {}
        findings.append(
            Issue(
                id="security-fetch-failed",
                category=Category.SECURITY,
                title="Could not fetch page to inspect security headers",
                description=str(exc),
                severity=Severity.LOW,
            )
        )

    for header, description in _REQUIRED_SECURITY_HEADERS.items():
        if header not in headers:
            findings.append(
                Issue(
                    id=f"security-missing-{header}",
                    category=Category.SECURITY,
                    title=f"Missing {header} header",
                    description=description,
                    severity=Severity.MEDIUM,
                )
            )

    # --- TLS certificate validity (passive: standard TLS handshake) ---
    if parsed.scheme == "https" and hostname:
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((hostname, 443), timeout=10) as sock:
                with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()

            expires = datetime.strptime(
                cert["notAfter"], "%b %d %H:%M:%S %Y %Z"
            ).replace(tzinfo=timezone.utc)
            days_left = (expires - datetime.now(timezone.utc)).days

            if days_left < 14:
                findings.append(
                    Issue(
                        id="security-cert-expiring",
                        category=Category.SECURITY,
                        title="TLS certificate expiring soon",
                        description=(
                            f"Certificate expires in {days_left} days "
                            f"({expires.date()})."
                        ),
                        severity=Severity.HIGH if days_left < 3 else Severity.MEDIUM,
                    )
                )
        except ssl.SSLCertVerificationError as exc:
            findings.append(
                Issue(
                    id="security-cert-invalid",
                    category=Category.SECURITY,
                    title="TLS certificate failed verification",
                    description=str(exc),
                    severity=Severity.HIGH,
                )
            )
        except Exception as exc:
            findings.append(
                Issue(
                    id="security-tls-check-failed",
                    category=Category.SECURITY,
                    title="Could not verify TLS configuration",
                    description=str(exc),
                    severity=Severity.LOW,
                )
            )
    elif parsed.scheme != "https":
        findings.append(
            Issue(
                id="security-no-https",
                category=Category.SECURITY,
                title="Site is not served over HTTPS",
                description="All traffic, including any submitted forms, is unencrypted.",
                severity=Severity.HIGH,
            )
        )
    print("Security Audit Node Completed")
    return {"security_findings": findings}


def triage_node(state: SiteDoctorState) -> dict:
    """Ranks and plain-language-ifies the mechanical Issues. UX suggestions
    already come out of the vision model in a fairly final, human-readable
    form, so they pass through untouched for v1."""
    if not state.audit_before:
        return {}

    total_issues = sum(len(result.issues) for result in state.audit_before)
    if not total_issues:
        return {}

    # TODO: your triage implementation goes here. Note audit_before is now
    # a LIST of AuditResult (one per crawled page) -- iterate
    # state.audit_before, and within each result.issues, ranking by
    # severity and filling in plain_language_summary as before. Each
    # AuditResult.url tells you which page a given issue came from, useful
    # for the report grouping later.
    return {}


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