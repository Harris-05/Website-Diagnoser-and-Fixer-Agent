# CLAUDE.md — Site Doctor Project Context

This file is a complete handoff document for the **Site Doctor** project.
Paste this into a new chat along with the actual code files if you need to
continue work with a different Claude session — it captures the
architecture, the decisions behind it, what's actually built vs. stubbed,
and every non-obvious bug/gotcha already hit and fixed, so you don't have
to rediscover them.

---

## 1. What this project is

**Site Doctor** is a LangGraph multi-agent system that crawls a website
and audits it across three independent, user-selectable dimensions:

- **SEO** — mechanical, rule-based checks via Google Lighthouse (SEO,
  accessibility, performance categories)
- **UX** — judgment-based usability/conversion review via a vision-capable
  LLM looking at screenshots
- **Security** — passive-only posture checks (HTTP security headers, TLS
  certificate validity). Opt-in, off by default, explicitly forbidden from
  ever doing active scanning/exploitation/load-testing.

The end goal (not yet built): for mechanically verifiable SEO issues, the
system proposes a fix, gets human approval, applies it to a **local**
copy, and re-audits to verify the fix actually worked — an act → verify →
retry loop. This is deliberately NOT a "RAG wrapper" — the value is in
this verification loop, not summarization.

**Why this project/architecture was chosen:** across a long conversation,
the user considered and rejected several other ideas (legal contract
review assistant, finance/covenant-monitoring tools, a bug-fixing agent,
an accessibility-only auditor, a research claim-verifier) before landing
on this one, specifically because it (a) is something the user personally
understands without domain expertise, (b) has a genuine "act, verify,
retry" loop that justifies using LangGraph over a simple linear script,
and (c) is buildable and testable end-to-end on a zero/low budget using
`gpt-4o-mini`.

---

## 2. Tech stack

| Layer | Tool | Notes |
|---|---|---|
| Orchestration | LangGraph | `StateGraph`, human-in-the-loop nodes, conditional fan-out |
| LLM | OpenAI (`gpt-4o-mini`) | User has OpenAI key, not Anthropic — all LLM calls use `openai` SDK directly, not LangChain wrappers |
| Crawling | Playwright (sync API) | Headless Chromium |
| SEO audit | Lighthouse CLI (Node.js) | Invoked as a subprocess |
| Schema/state | Pydantic v2 | All cross-node data is typed |
| Dev environment | Windows (PowerShell), Python 3.14, venv | Several bugs below are Windows-specific |

---

## 3. Repository structure

```
site-doctor/
    agent/
        graph.py            <- LangGraph state machine (THE central file)
    crawler/
        crawl.py             <- crawl_page/screenshot_page (single-page,
                                 legacy) + crawl_site() (delegates to
                                 WebsiteCrawler)
        utils.py              <- normalize_url, is_internal_link, slugify,
                                 extract_links
        storage.py            <- manages .site-doctor-cache/crawl_<id>/
                                 layout; save_html, save_manifest,
                                 load_manifest, path builders
        website_crawler.py    <- WebsiteCrawler class: real BFS traversal
    audit/
        lighthouse.py         <- wraps Lighthouse CLI subprocess, parses
                                 ONLY tracked audit IDs (never sends raw
                                 report anywhere)
    ux_review/
        vision_review.py      <- sends multiple screenshots in ONE call to
                                 a vision LLM, parses UXSuggestion objects
    models/
        schemas.py             <- ALL Pydantic models (see §5)
    tests/                     <- empty, not yet used
```

---

## 4. The graph (agent/graph.py) — current shape

```
  check_selection (human-in-the-loop: which checks to run)
        |
      crawl (multi-page BFS via crawl_site())
        |
  conditional fan-out based on selected_checks
        |
   +----+----+---------------+
   v         v               v
seo_audit  ux_review   security_audit   <- ONLY selected branches run
   |         |               |
   +----+----+---------------+
        |
      triage
        |
       fix -> approve -> apply -> reaudit -+-> END
                          ^________________|
                    (loop back if a fix didn't clear)
```

### Node-by-node status

| Node | Status | Notes |
|---|---|---|
| `check_selection_node` | **Done** | Prompts user (CLI `input()`) for SEO/UX/Security by number. Defaults to SEO+UX if blank. Security requires a SEPARATE explicit `y` confirmation naming exactly what "passive only" means, in addition to being selected. |
| `crawl_node` | **Done** | Calls `crawl_site(state.url, max_pages=5, max_depth=1)`. Populates `state.crawl_result` (the real multi-page result) AND mirrors the home page into the legacy `local_copy_path`/`screenshot_paths` fields, since `ux_review_node` hasn't been migrated to read from `crawl_result` yet. |
| `route_checks` | **Done** | Conditional-edge function; maps `selected_checks` -> node names, only those nodes actually get invoked (verified: selecting only `seo` results in `ux_suggestions: []` and `security_findings: []` because those branches never ran, not because they ran and found nothing). |
| `seo_audit_node` | **Done** | Runs Lighthouse against **every** page in `crawl_result.pages`, not just the start URL. Returns `audit_before` as a **list** of `AuditResult`, one per page (each `AuditResult` already carries its own `.url`). Wrapped in try/except per-page so one page's Lighthouse failure doesn't kill the whole run. |
| `ux_review_node` | **Done, but not yet multi-page** | Still only reviews `state.screenshot_paths` (the home page, via the legacy mirror from `crawl_node`). NOT yet updated to loop over `crawl_result.pages` the way `seo_audit_node` was. **This is the next natural piece of work**, mirroring the SEO multi-page upgrade. |
| `security_audit_node` | **Done (basic, passive-only)** | Checks 5 HTTP security headers (HSTS, CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy) via a single GET request, and TLS certificate validity/expiry via a standard TLS handshake. Explicitly does NOT do active scanning. Only audits `state.url` (home page) currently — same multi-page gap as UX review. |
| `triage_node` | **STUB** | Guard logic updated for the new list-based `audit_before`, but the actual ranking/plain-language-summary LLM call is not yet implemented. This was the very first node the user was asked to write and it's been deferred through several detours. |
| `fix_node` | **STUB** | Not started. |
| `approve_node` | **STUB** | Not started. Intended as a LangGraph human-in-the-loop interrupt point. |
| `apply_node` | **STUB** | Not started. |
| `reaudit_node` | **STUB** | Not started. |
| `should_retry` | **STUB** | Currently always returns `END` — no retry logic yet. |

---

## 5. Schema reference (models/schemas.py)

```python
class Category(str, Enum):
    SEO = "seo"
    ACCESSIBILITY = "accessibility"
    PERFORMANCE = "performance"
    SECURITY = "security"

class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class Issue(BaseModel):
    """Mechanically verifiable finding (Lighthouse OR security checks).
    Has a real pass/fail check -- the ONLY type that goes through the
    fix/apply/reaudit/retry loop."""
    id: str
    category: Category
    title: str
    description: str
    plain_language_summary: Optional[str] = None   # filled in by triage
    severity: Optional[Severity] = None
    fix_confidence: Optional[float] = None
    affected_selector: Optional[str] = None

class UXSuggestion(BaseModel):
    """Judgment-call finding from vision review. NO ground truth to
    re-check mechanically -- surfaced to human, never auto-applied."""
    id: str
    category: str          # e.g. clutter, cta-overload, hierarchy
    severity: Severity
    observation: str
    recommendation: str

class Fix(BaseModel):
    """A proposed patch for a specific Issue (never a UXSuggestion)."""
    issue_id: str
    description: str
    before: str
    after: str
    approved: Optional[bool] = None
    applied: bool = False
    verified_cleared: Optional[bool] = None
    attempts: int = 0

class AuditResult(BaseModel):
    url: str
    scores: dict[Category, float] = {}
    issues: list[Issue] = []

class PageResult(BaseModel):
    """One crawled page's artifacts + where they live on disk."""
    url: str
    slug: str
    html_path: str
    screenshot_paths: list[str] = []
    depth: int = 0

class CrawlResult(BaseModel):
    """Full result of a multi-page crawl run."""
    crawl_id: str
    start_url: str
    pages: list[PageResult] = []
    crawled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SiteDoctorState(BaseModel):
    """The full LangGraph state, shared across every node."""
    url: str
    selected_checks: list[str] = ["seo", "ux"]     # security OFF by default
    crawl_result: Optional[CrawlResult] = None
    local_copy_path: Optional[str] = None           # LEGACY mirror, home page only
    screenshot_paths: list[str] = []                # LEGACY mirror, home page only
    audit_before: list[AuditResult] = []            # ONE PER PAGE (changed from single Optional)
    audit_after: list[AuditResult] = []             # same shape, for reaudit later
    ux_suggestions: list[UXSuggestion] = []
    security_findings: list[Issue] = []
    fixes: list[Fix] = []
    max_retries_per_fix: int = 2
```

**Important architectural rule maintained throughout:** `Issue` (mechanical,
verifiable) and `UXSuggestion` (judgment-based, not verifiable) are
DELIBERATELY separate types, never merged into one polymorphic "finding"
type. `Fix` only ever attaches to an `Issue.id`, never a `UXSuggestion`.
This distinction is enforced in the SRS, SDD, and DB design docs too (see
§8) — don't blur it when adding new features.

---

## 6. Key design decisions and their rationale

- **Human-in-the-loop check selection, security off by default.** The
  user explicitly wanted this after realizing an earlier draft would have
  run "stress testing" against arbitrary sites — a real legal problem
  (unauthorized computer access laws apply even without malicious intent).
  Current implementation: passive-only (headers + TLS), explicit opt-in,
  explicit authorization confirmation. This constraint should NOT be
  relaxed without deliberately revisiting it.
- **Manifest-driven cache layout**
  (`.site-doctor-cache/crawl_<id>/pages/<slug>/page.html` + `N.png` +
  `manifest.json` at the crawl root) instead of flat filenames — avoids
  filename collisions between runs/pages, and gives downstream consumers
  (Lighthouse, vision review, a future AI summarizer) one JSON file to
  read instead of having to infer structure from folder scanning.
- **Compatibility-layer migration strategy.** When `CrawlResult`/`PageResult`
  were introduced, old fields (`local_copy_path`, `screenshot_paths`) were
  KEPT and mirrored from the new data, rather than ripping out working
  code. `seo_audit_node` has since been migrated to use `crawl_result`
  directly; `ux_review_node` and `security_audit_node` have NOT — they're
  next.
- **Never send raw tool output to an LLM.** Lighthouse's raw JSON report
  is ~11,000 lines. `audit/lighthouse.py`'s `parse_report()` immediately
  discards everything except a small `TRACKED_AUDITS` allowlist of audit
  IDs and the 3 category scores — the raw report is never retained in
  state or sent anywhere near an LLM call.
- **Multiple screenshots sent in ONE vision LLM call, not N separate
  calls**, with the prompt explicitly told they're the same page in
  scroll order — otherwise the model has no way to know screenshot 2
  isn't a totally different page, and might flag "missing CTA" on a
  mid-page screenshot when one exists higher up.
- **`gpt-4o-mini`, not a frontier model**, used everywhere — deliberate
  cost control given the user has no budget to spend on this project.

---

## 7. Known bugs already hit and fixed (don't reintroduce these)

| Bug | Fix |
|---|---|
| `Path.read_text()` on Windows defaults to `cp1252`, crashes on Lighthouse's UTF-8 JSON output (emoji/smart-quotes in page content) | Always pass `encoding="utf-8"` explicitly on every `read_text`/`write_text` call |
| Lighthouse `NO_LCP` / `EPERM` crash on Windows with old headless mode | Use `--chrome-flags=--headless=new` (not bare `--headless`) |
| `default_factory=datetime.utcnow()` (called immediately) vs `default_factory=datetime.utcnow` or `lambda: ...` (deferred) — Pydantic error `'datetime.datetime' object is not callable` | Always wrap in `lambda:` for `default_factory` unless passing a bare function reference with no arguments |
| `extract_links()` didn't resolve relative hrefs (`/about`) to absolute URLs before checking if internal — silently dropped almost all links on any real site | Always `urljoin(base_url, href)` BEFORE any internal/external check |
| `is_internal_link` did substring `startswith` matching — `"site.com.evil.com".startswith("site.com")` is `True`, a spoofing gap | Compare `urlparse(url).netloc` (hostname) for exact equality instead |
| `normalize_url()` strips the URL scheme entirely — breaks direct use for Playwright navigation (`page.goto()` needs a full URL) | `WebsiteCrawler._with_scheme()` re-attaches the scheme before every `page.goto()` call; normalized (scheme-less) strings are only used as the BFS visited-set dedup key |
| `wait_until="networkidle"` in Playwright times out (15s+) on real sites with chat widgets/analytics that never go fully idle | Use `wait_until="load"` with `timeout=30000` instead |
| `save_manifest()` crashed with `FileNotFoundError` if the crawl produced zero successful pages (directory never got created) | `path.parent.mkdir(parents=True, exist_ok=True)` before every write, don't assume a directory exists |
| Editing a stale local mirror of `schemas.py` and handing back a "partial" snippet caused the user to accidentally delete `PageResult`/`CrawlResult` when merging | When schema drift is suspected, replace the WHOLE file rather than patching a snippet against an assumed-current version |

---

## 8. Documentation already produced

Full IEEE-style docs exist as LaTeX + compiled PDF for this project
(compiled cleanly with `pdflatex`, diagrams via TikZ):

1. **SRS** (Software Requirements Specification) — functional/non-functional
   requirements, external interfaces, constraints (incl. the security
   opt-in/passive-only constraint as a hard Mandatory requirement),
   assumptions.
2. **SDD** (Software Design Document) — architecture diagrams, component
   responsibility table, database design (planned Postgres persistence
   layer — NOT yet implemented in code, pipeline is currently stateless
   per run), API design (planned REST surface), sequence diagrams, error
   handling table, security design.
3. **Use Case Specification** — UC-01 through UC-05 (Analyze Website,
   Select Checks, Approve Fix, Authorize Security Check, View/Download
   Report), each with main/alternative/exception flows.
4. **UML diagram set** — use case, class, sequence, activity, component,
   deployment diagrams.
5. **Database Design Document** — standalone version of the SDD's DB
   section: ER diagram, table definitions, relationships, indexes,
   normalization (3NF) rationale, constraints.

These describe the TARGET architecture including a planned hosted
deployment (FastAPI + PostgreSQL + Streamlit/React frontend) — the
current actual implementation is a local CLI-driven script, not that
hosted version. Don't confuse "documented" with "built" — check §4/§5
above for actual code status.

---

## 9. How to run what exists today

```bash
# from site-doctor/ directory, with venv active
pip install -r requirements.txt --break-system-packages
playwright install chromium
npm install -g lighthouse   # or rely on the npx fallback in audit/lighthouse.py
export OPENAI_API_KEY=your-key-here   # or $env:OPENAI_API_KEY on PowerShell

# run individual pieces standalone:
python -m crawler.website_crawler     # test BFS crawl alone
python -m audit.lighthouse            # test Lighthouse alone
python -m ux_review.vision_review     # test vision review alone (needs screenshots to exist)

# run the full graph:
python -m agent.graph
```

---

## 10. Immediate next steps (roughly in priority order)

1. **Finish `triage_node`** — the original first task, deferred multiple
   times. Needs to loop over `state.audit_before` (now a list per page),
   rank issues by severity, and generate `plain_language_summary` per
   issue via an OpenAI call. Reference: `ux_review/vision_review.py`'s
   JSON-parsing pattern for how the rest of the codebase structures LLM
   calls.
2. **Migrate `ux_review_node` to multi-page**, same pattern as
   `seo_audit_node`'s recent upgrade — loop over `crawl_result.pages`
   instead of only reading the legacy `screenshot_paths` mirror.
3. **Migrate `security_audit_node` to multi-page** similarly.
4. **`fix_node` → `approve_node` → `apply_node` → `reaudit_node`** — the
   full act/verify/retry loop, still entirely unbuilt.
5. Consider whether `ux_suggestions`/`security_findings` need a `page_url`
   field added now that multiple pages exist (currently `UXSuggestion` and
   the security `Issue`s have no page-attribution field — this will
   matter once those nodes go multi-page).

---

## 11. User context (for tone/pacing in a new session)

- Knows LangChain/LangGraph fundamentals already; does NOT want code
  fully written for them by default — prefers being given the
  shape/hints and writing it themselves, with review after. (This shifted
  over the course of the conversation toward more direct "just give me
  the code" requests during debugging-heavy stretches — use judgment on
  which mode is wanted based on how the request is phrased.)
- Has an OpenAI API key, explicitly on a limited/no budget — always
  default to `gpt-4o-mini`, minimize token usage, never send raw/unfiltered
  tool output to an LLM.
- On Windows (PowerShell), Python 3.14, venv — several encoding/subprocess
  quirks are Windows-specific (see §7).
- Wants this to be a genuine portfolio piece / meaningful contribution,
  not a "RAG wrapper" — the act-verify-retry loop is the point, protect
  that framing when suggesting features.
