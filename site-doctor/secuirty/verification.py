"""Domain-ownership verification gate for active security tooling.

Active security tools (ZAP active scan, Nuclei exploit templates, SQLMap,
Dalfox, Nmap, k6 load/stress) must NEVER run against a domain until this
module confirms the caller actually controls that domain. A UI checkbox
or self-attestation ("I have permission") is NOT sufficient authorization
on its own -- see CLAUDE.md for the full reasoning.

Verification method: DNS TXT record challenge -- the same pattern used by
Google Search Console and most SaaS platforms. The caller is asked to add
a TXT record containing a token this module generates, then the module
resolves DNS to confirm it's actually there before marking the domain
verified.

Verified status is stored PER DOMAIN (not per session, not per URL) in a
local JSON store, so re-auditing a previously-verified domain doesn't
require re-verifying, but auditing any different domain always does. This
also creates a simple audit trail (verified_at, method).

Passive checks (security/passive_checks.py) are NOT gated by any of this
and never should be -- this module only matters for active_engine.py.
"""

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import dns.resolver

VERIFIED_STORE_PATH = Path("./.site-doctor-cache/verified_domains.json")
TXT_RECORD_SUBDOMAIN = "_sitedoctor-verification"
TOKEN_BYTE_LENGTH = 16


def _load_store() -> dict:
    if not VERIFIED_STORE_PATH.exists():
        return {}
    return json.loads(VERIFIED_STORE_PATH.read_text(encoding="utf-8"))


def _save_store(store: dict) -> None:
    VERIFIED_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    VERIFIED_STORE_PATH.write_text(json.dumps(store, indent=2), encoding="utf-8")


def _extract_domain(url_or_domain: str) -> str:
    """Accepts either a bare domain ("example.com") or a full URL and
    returns just the hostname, so callers can pass whichever they have
    on hand without thinking about it."""
    if "://" in url_or_domain:
        return urlparse(url_or_domain).hostname or url_or_domain
    return url_or_domain.strip("/")


def start_verification(url_or_domain: str) -> str:
    """Generates a fresh challenge token for a domain and returns
    human-readable instructions for the DNS TXT record the caller needs
    to create. Does NOT mark the domain verified -- call
    check_verification() once the record is live.

    Safe to call again for a domain that already has a pending or even a
    completed verification; it simply issues a new token and resets the
    pending state (does not affect an existing "verified" status until
    check_verification() actually re-confirms).
    """
    domain = _extract_domain(url_or_domain)
    token = secrets.token_hex(TOKEN_BYTE_LENGTH)

    store = _load_store()
    domain_record = store.setdefault(domain, {})
    domain_record["pending_token"] = token
    domain_record["challenge_issued_at"] = datetime.now(timezone.utc).isoformat()
    _save_store(store)

    record_name = f"{TXT_RECORD_SUBDOMAIN}.{domain}"
    record_value = f"sitedoctor-verify={token}"

    return (
        f"To verify ownership of {domain}, add this DNS TXT record:\n"
        f"  Name:  {record_name}\n"
        f"  Value: {record_value}\n"
        f"Then call check_verification({domain!r}). DNS changes can take "
        f"a few minutes (sometimes longer) to propagate."
    )


def check_verification(url_or_domain: str) -> bool:
    """Checks whether the pending challenge TXT record is actually live
    for this domain via a real DNS lookup. On success, marks the domain
    verified (persisted to disk) and clears the pending token. Returns
    False (does not raise) on any lookup failure or mismatch, so callers
    can safely poll this while waiting for DNS propagation."""
    domain = _extract_domain(url_or_domain)
    store = _load_store()
    record = store.get(domain)

    if not record or "pending_token" not in record:
        raise ValueError(
            f"No pending verification for {domain!r}. "
            f"Call start_verification() first."
        )

    expected_value = f"sitedoctor-verify={record['pending_token']}"
    record_name = f"{TXT_RECORD_SUBDOMAIN}.{domain}"

    try:
        answers = dns.resolver.resolve(record_name, "TXT")
        found_values = [
            b"".join(rdata.strings).decode("utf-8", errors="ignore")
            for rdata in answers
        ]
    except Exception as exc:
        print(f"DNS lookup failed for {record_name}: {exc}")
        return False

    if expected_value not in found_values:
        print(
            f"TXT record found at {record_name} but the token doesn't "
            f"match yet (or the record hasn't propagated)."
        )
        return False

    store[domain] = {
        "verified": True,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "method": "dns-txt",
    }
    _save_store(store)
    return True


def is_verified(url_or_domain: str) -> bool:
    """Read-only check against the local store: has this domain already
    been verified in a past session? Does NOT perform a new DNS lookup --
    for that, use check_verification()."""
    domain = _extract_domain(url_or_domain)
    store = _load_store()
    return store.get(domain, {}).get("verified", False)


def require_verified(url_or_domain: str) -> None:
    """THE actual gate. Every function in active_engine.py must call this
    as its first line, before doing anything else. Raises PermissionError
    if the domain hasn't been verified -- this is a code-level guard, not
    a UI checkbox or a docstring warning, so there's no path through
    active_engine.py that skips it by accident."""
    domain = _extract_domain(url_or_domain)
    if not is_verified(domain):
        raise PermissionError(
            f"'{domain}' is not verified for active security testing. "
            f"Call start_verification({domain!r}) and "
            f"check_verification({domain!r}) first."
        )


if __name__ == "__main__":
    target = input("Enter the domain or URL to verify: ").strip()

    if is_verified(target):
        print(f"{_extract_domain(target)} is already verified.")
    else:
        action = input("[1] Start verification  [2] Check pending verification: ").strip()
        if action == "1":
            print(start_verification(target))
        elif action == "2":
            ok = check_verification(target)
            print("Verified!" if ok else "Not verified yet.")