import urllib
from models.schemas import SiteDoctorState, Issue, Category, Severity, UXSuggestion, AuditResult
from urllib.parse import urlparse
from datetime import datetime, timezone
import socket
import ssl

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

def run_passive_tests(url: str) -> dict:
    parsed = urlparse(url)
    hostname = parsed.hostname
    findings: list[Issue] = []

    # --- HTTP security headers (passive: a single normal GET request) ---
    try:
        req = urllib.request.Request(
            url, method="GET", headers={"User-Agent": "SiteDoctor/1.0"}
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
    return {"findings": findings}
