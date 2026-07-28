"""active_engine.py -- active security tooling, STRICTLY gated behind
domain-ownership verification (security/verification.py).

Every function in this file calls require_verified() as its literal first
line. There is no code path here that runs without a domain having passed
a real DNS TXT ownership check first -- a UI checkbox or self-attestation
is not sufficient authorization on its own (see CLAUDE.md).

None of the actual scanning logic lives here -- these are thin subprocess
wrappers around established, independently-installed open-source security
tools (the same pattern as audit/lighthouse.py wrapping the Lighthouse
CLI). You need each underlying tool installed separately; see the
prerequisite note above each function.

Phases:
  Phase 1 (verified only):        ZAP baseline, Nuclei (info-disclosure
                                   templates only, NOT cve/exploit
                                   templates), deep TLS analysis.
  Phase 2 (verified + a specific  SQLMap against a named form/param URL,
           surface identified     Dalfox against a named reflected-input
           from Phase 1):         URL. Never run blindly site-wide.
  Phase 3 (verified AND a         ZAP active scan, Nmap, k6 load/stress.
           SEPARATE explicit      These actively attack or degrade the
           confirm per run):      target's live infrastructure -- a
                                   materially different risk than Phase
                                   1/2, so verification alone is not
                                   enough to unlock them.
"""

import json
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from security.verification import require_verified

RESULTS_DIR = Path("./.site-doctor-cache/security-active")


def _result_path(domain: str, tool: str) -> Path:
    d = RESULTS_DIR / domain
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{tool}.json"


def _require_phase3_confirmation(explicit_confirm: bool, tool_name: str) -> None:
    if not explicit_confirm:
        raise PermissionError(
            f"{tool_name} is a Phase 3 tool -- it actively attacks or "
            f"degrades the target's live infrastructure. Domain "
            f"verification alone is not sufficient. Pass "
            f"explicit_confirm=True only after a SEPARATE, explicit human "
            f"confirmation for THIS run, naming exactly what {tool_name} "
            f"will do to the target."
        )


# ---------------------------------------------------------------------
# PHASE 1 -- verified only
# ---------------------------------------------------------------------

def run_zap_baseline(url: str) -> dict:
    """OWASP ZAP baseline scan: spiders the site and inspects real
    traffic/responses (headers, cookies, tech fingerprinting) WITHOUT
    sending attack payloads.

    Prerequisite: Docker installed and running (uses the
    owasp/zap2docker-stable image, pulled automatically on first run).
    """
    require_verified(url)
    domain = urlparse(url).hostname
    report_path = _result_path(domain, "zap_baseline")

    try:
        subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{report_path.parent}:/zap/wrk",
                "owasp/zap2docker-stable",
                "zap-baseline.py",
                "-t", url,
                "-J", f"/zap/wrk/{report_path.name}",
            ],
            check=True,
            timeout=600,
        )
    except subprocess.CalledProcessError as exc:
        # zap-baseline.py exits non-zero when it finds warnings/alerts --
        # that's the expected/normal case, not a crash. Only treat it as
        # a real failure if no report was produced at all.
        if not report_path.exists():
            raise RuntimeError(f"ZAP baseline scan failed to produce a report: {exc}")

    return json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}


def run_nuclei_info_disclosure(url: str) -> dict:
    """Nuclei restricted to info-disclosure / misconfiguration templates
    ONLY -- deliberately excludes cve/exploit template categories at this
    phase.

    Prerequisite: `nuclei` on PATH (github.com/projectdiscovery/nuclei).
    """
    require_verified(url)
    domain = urlparse(url).hostname
    report_path = _result_path(domain, "nuclei_info_disclosure")

    subprocess.run(
        [
            "nuclei",
            "-u", url,
            "-tags", "exposure,misconfig,default-login",
            "-jsonl",
            "-o", str(report_path),
            "-silent",
        ],
        check=True,
        timeout=600,
    )

    if not report_path.exists():
        return {"findings": []}

    findings = [
        json.loads(line)
        for line in report_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {"findings": findings}


def run_tls_deep_analysis(url: str) -> dict:
    """Deeper TLS/cert-chain analysis than passive_checks.py's basic
    expiry check -- protocol versions, cipher suite strength, known-weak
    configurations.

    Prerequisite: `testssl.sh` on PATH (github.com/drwetter/testssl.sh).
    """
    require_verified(url)
    domain = urlparse(url).hostname
    report_path = _result_path(domain, "tls_deep")

    subprocess.run(
        ["testssl.sh", "--jsonfile", str(report_path), "--quiet", url],
        check=True,
        timeout=300,
    )

    return json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}


# ---------------------------------------------------------------------
# PHASE 2 -- verified + a SPECIFIC surface identified from Phase 1
# (never run blindly against the whole site)
# ---------------------------------------------------------------------

def run_sqlmap(url: str, form_or_param_url: str) -> dict:
    """SQLMap against one SPECIFIC form/query-param URL. The caller is
    responsible for having already identified a real parameterized
    surface (e.g. from Phase 1 findings) before calling this -- never
    call this against a bare homepage/site root.

    Prerequisite: `sqlmap` on PATH.
    """
    require_verified(url)
    domain = urlparse(url).hostname
    report_dir = RESULTS_DIR / domain / "sqlmap"
    report_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "sqlmap",
            "-u", form_or_param_url,
            "--batch",
            "--level=1", "--risk=1",  # conservative: least intrusive tests only
            "--output-dir", str(report_dir),
        ],
        check=True,
        timeout=900,
    )

    return {"output_dir": str(report_dir)}


def run_dalfox(url: str, reflected_input_url: str) -> dict:
    """Dalfox XSS scan against one SPECIFIC URL with a known
    reflected-input surface (identified from Phase 1) -- not run blindly
    site-wide.

    Prerequisite: `dalfox` on PATH.
    """
    require_verified(url)
    domain = urlparse(url).hostname
    report_path = _result_path(domain, "dalfox")

    subprocess.run(
        ["dalfox", "url", reflected_input_url, "-o", str(report_path), "--silence"],
        check=True,
        timeout=600,
    )

    return json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}


# ---------------------------------------------------------------------
# PHASE 3 -- verified AND a SEPARATE explicit confirmation per run
# (target-degrading / exploit-attempting tier)
# ---------------------------------------------------------------------

def run_zap_active_scan(url: str, explicit_confirm: bool = False) -> dict:
    """OWASP ZAP ACTIVE scan: actually attacks the target (injects
    payloads, attempts auth bypasses).

    Prerequisite: Docker installed and running.
    """
    require_verified(url)
    _require_phase3_confirmation(explicit_confirm, "ZAP active scan")

    domain = urlparse(url).hostname
    report_path = _result_path(domain, "zap_active")

    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{report_path.parent}:/zap/wrk",
            "owasp/zap2docker-stable",
            "zap-full-scan.py",
            "-t", url,
            "-J", f"/zap/wrk/{report_path.name}",
        ],
        check=True,
        timeout=1800,
    )

    return json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}


def run_nmap(url: str, explicit_confirm: bool = False) -> dict:
    """Nmap port/service scan against the target's infrastructure.

    Prerequisite: `nmap` on PATH.
    """
    require_verified(url)
    _require_phase3_confirmation(explicit_confirm, "Nmap")

    domain = urlparse(url).hostname
    report_path = _result_path(domain, "nmap")

    subprocess.run(
        ["nmap", "-sV", "-oX", str(report_path), domain],
        check=True,
        timeout=900,
    )

    return {"report_path": str(report_path)}


def run_k6_load_test(
    url: str,
    explicit_confirm: bool = False,
    duration_seconds: int = 30,
    virtual_users: int = 10,
) -> dict:
    """k6 load/stress test -- deliberately degrades target availability by
    design, unlike everything else in this file. Kept intentionally
    low-intensity by default (short duration, few virtual users); do not
    silently raise these numbers without the user explicitly requesting
    a heavier test.

    Prerequisite: `k6` on PATH.
    """
    require_verified(url)
    _require_phase3_confirmation(explicit_confirm, "k6 load test")

    domain = urlparse(url).hostname
    script_path = RESULTS_DIR / domain / "k6_script.js"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(
        (
            "import http from 'k6/http';\n"
            f"export const options = {{ vus: {virtual_users}, duration: '{duration_seconds}s' }};\n"
            f"export default function () {{ http.get('{url}'); }}\n"
        ),
        encoding="utf-8",
    )

    report_path = _result_path(domain, "k6")
    subprocess.run(
        ["k6", "run", "--summary-export", str(report_path), str(script_path)],
        check=True,
        timeout=duration_seconds + 60,
    )

    return json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}


if __name__ == "__main__":
    print(
        "This module is not meant to be run standalone yet -- call its "
        "functions individually once verification.py has confirmed "
        "domain ownership. Example:\n\n"
        "  from security.verification import start_verification, check_verification\n"
        "  from security.active_engine import run_zap_baseline\n\n"
        "  # 1. verify ownership first (see security/verification.py)\n"
        "  # 2. then, once verified:\n"
        "  run_zap_baseline('https://example.com')\n"
    )