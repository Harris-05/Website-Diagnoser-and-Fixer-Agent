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
                                 load_manifest, path builders.
                                 PENDING: ux_report_path() helper proposed
                                 (mirrors manifest_path) — not yet added.
        website_crawler.py    <- WebsiteCrawler class: real BFS traversal.
                                 Now takes an `isux` flag threaded through
                                 crawl() -> per-page loop, so screenshots
                                 are only captured when UX review is
                                 selected (see §4/§6).
    audit/
        lighthouse.py         <- wraps Lighthouse CLI subprocess, parses
                                 ONLY tracked audit IDs (never sends raw
                                 report anywhere). Runs per-page now (see
                                 §4). NOTE: file currently has TWO
                                 definitions of run_lighthouse() — the
                                 first (no `categories` param) is dead
                                 code silently shadowed by the second;
                                 not yet cleaned up.
    ux_review/
        vision_review.py      <- sends multiple screenshots in ONE call to
                                 a vision LLM, parses UXSuggestion objects.
                                 Now takes (url, screenshot_paths) and
                                 stamps the URL onto each returned
                                 suggestion (see §4). Prompt substantially
                                 rewritten this session — see §6.
                                 PENDING: save_ux_report() (grouped
                                 markdown report per crawl) proposed,
                                 not yet added.
    models/
        schemas.py             <- ALL Pydantic models (see §5).
                                 PENDING: UXSuggestion.page_url field and
                                 SiteDoctorState.max_depth/max_pages
                                 fields discussed/added this session —
                                 confirm final field names/defaults next
                                 session (see §5, §10).
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
| `crawl_node` | **Done, evolving** | Calls `crawl_site(state.url, max_pages=..., max_depth=..., isux=...)`. `max_pages`/`max_depth` were first made interactive via `input()` directly inside this node, then (per the user's latest change) moved onto `SiteDoctorState` instead so a single upfront prompt sets them and every downstream node — including `crawl_node` itself — stays input-independent (crucial for the eventual FastAPI surface in the SDD, which can't call `input()`). `isux` is now derived from `"ux" in state.selected_checks` and passed through so screenshots are ONLY captured when UX review is actually selected — SEO-only runs no longer pay the Playwright screenshot cost. Still populates `state.crawl_result` (the real multi-page result) AND mirrors the home page into the legacy `local_copy_path`/`screenshot_paths` fields for any code not yet migrated. **Open item:** exact final home for the max_depth/max_pages prompt (inside `check_selection_node` vs. a new dedicated setup node) and the state field names/defaults were not confirmed with final code before this doc was written — verify next session. |
| `route_checks` | **Done** | Conditional-edge function; maps `selected_checks` -> node names, only those nodes actually get invoked (verified: selecting only `seo` results in `ux_suggestions: []` and `security_findings: []` because those branches never ran, not because they ran and found nothing). |
| `seo_audit_node` | **Done** | Runs Lighthouse against **every** page in `crawl_result.pages`, not just the start URL. Returns `audit_before` as a **list** of `AuditResult`, one per page (each `AuditResult` already carries its own `.url`). Wrapped in try/except per-page so one page's Lighthouse failure doesn't kill the whole run. Verified end-to-end against a real 5-page site (autogloss.pk) — all 5 pages returned scores/issues correctly. `NO_LCP` LanternError + Windows `EPERM` temp-cleanup errors are noisy stderr from Lighthouse/chrome-launcher but do NOT break the run — the existing performance-category retry (`audit_url`'s except block) already handles `NO_LCP` pages correctly. |
| `ux_review_node` | **Migrated to multi-page this session** | Now loops over `state.crawl_result.pages`, calling `review_screenshots(page.url, page.screenshot_paths)` per page inside a try/except (mirrors the `seo_audit_node` per-page resilience pattern) and accumulating into one `ux_suggestions` list. Verified end-to-end against autogloss.pk: correctly iterated all 5 pages (previously crashed with `TypeError: review_screenshots() missing 1 required positional argument` because `graph.py` still had the old single-arg call — that's fixed now). Currently blocked on an OpenAI `insufficient_quota` (429) billing issue on the user's account, unrelated to code — needs billing/plan check on platform.openai.com before it can be verified against a live vision call. **Open item:** `save_ux_report()` (grouped-by-page-URL markdown report, see §6) was proposed but not yet confirmed added to the node. |
| `security_audit_node` | **Done (basic, passive-only)** | Checks 5 HTTP security headers (HSTS, CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy) via a single GET request, and TLS certificate validity/expiry via a standard TLS handshake. Explicitly does NOT do active scanning. Only audits `state.url` (home page) currently — same multi-page gap as before, NOT addressed this session. |
| `triage_node` | **STUB** | Guard logic updated for the new list-based `audit_before`, but the actual ranking/plain-language-summary LLM call is not yet implemented. This was the very first node the user was asked to write and it's been deferred through several detours. An `aggregate_for_llm()` helper was sketched this session (see §6) to collapse the per-page `audit_before` list into one compact dict for this node's future LLM call — not yet wired in. |
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
                            # PROPOSED (not yet confirmed applied): tighten
                            # to a UXCategory(str, Enum) mirroring the 14
                            # category strings now used in
                            # VISION_REVIEW_PROMPT (see §6), so a
                            # malformed category from the model fails at
                            # parse time instead of silently passing
                            # through as a random string.
    severity: Severity
    observation: str
    recommendation: str
    page_url: str | None = None   # ADDED this session — which page this
                                   # suggestion is about. Needed once
                                   # ux_review_node started looping over
                                   # multiple pages; review_screenshots()
                                   # now stamps this after parsing the
                                   # model's response. CONFIRM this field
                                   # made it into the actual file — it was
                                   # proposed and the multi-page flow
                                   # depends on it, but wasn't pasted back
                                   # for verification.

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
    screenshot_paths: list[str] = []   # now populated conditionally --
                                        # only non-empty when the crawl was
                                        # run with isux=True (see §4/§6)
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
    max_depth: int          # ADDED this session -- moved off crawl_node's
                             # local input() so every node is
                             # input-independent. Exact field name/default
                             # not reconfirmed in code -- verify next
                             # session.
    max_pages: int          # ADDED this session -- same as above.
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
  PROPOSED extension (not yet added): a `ux_report_path(crawl_id)`
  helper in `storage.py`, mirroring `manifest_path()`, so the grouped UX
  markdown report lives at `.site-doctor-cache/crawl_<id>/ux_report.md`
  — same root as the manifest, single source of truth per crawl.
- **Compatibility-layer migration strategy.** When `CrawlResult`/`PageResult`
  were introduced, old fields (`local_copy_path`, `screenshot_paths`) were
  KEPT and mirrored from the new data, rather than ripping out working
  code. `seo_audit_node` and `ux_review_node` have now BOTH been migrated
  to use `crawl_result` directly (UX review migrated this session);
  `security_audit_node` has NOT — it's next.
- **Never send raw tool output to an LLM.** Lighthouse's raw JSON report
  is ~11,000 lines. `audit/lighthouse.py`'s `parse_report()` immediately
  discards everything except a small `TRACKED_AUDITS` allowlist of audit
  IDs and the 3 category scores — the raw report is never retained in
  state or sent anywhere near an LLM call. Extends naturally to the
  proposed `aggregate_for_llm()` helper (sketched this session, not yet
  wired into `triage_node`): it collapses the already-filtered per-page
  `audit_before` list into one compact `{"pages": [{url, scores, issues}]}`
  dict for a single `gpt-4o-mini` triage call, without re-parsing any raw
  Lighthouse JSON a second time.
- **Screenshots are now conditional on UX being selected.** `crawl_site()`
  and `WebsiteCrawler.crawl()` take an `isux: bool` flag; the per-page
  loop only calls `self._capture_screenshots()` when `isux=True`. An
  SEO-only run no longer pays the Playwright screenshot cost or leaves
  `PageResult.screenshot_paths` populated with images nothing will read.
- **UX review prompt substantially rewritten this session.** The vision
  prompt now frames the model as a senior UX/CRO/accessibility reviewer
  and checks against 13 named categories (visual hierarchy, CTA
  effectiveness, navigation, clutter, typography/readability,
  color/contrast, consistency, trust/credibility, visual-only
  accessibility, information architecture, conversion optimization,
  mobile friendliness, overall professionalism), with explicit
  anti-hallucination guardrails ("only report issues that are clearly
  visible," "do not guess," "if evidence is insufficient, do not mention
  it") and severity definitions (high = blocks conversion/major
  usability, medium = noticeable friction, low = cosmetic). This is a
  meaningfully longer prompt than the original (~4-5x), which is an
  intentional token/cost tradeoff given the no-budget constraint — text
  tokens are cheap relative to the image tokens that already dominate
  vision-call cost. PROPOSED, not yet confirmed applied:
  `response_format={"type": "json_object"}` on the
  `client.chat.completions.create()` call, to force valid JSON at the API
  level rather than relying solely on the prompt's "return ONLY valid
  JSON" instruction + the existing `_strip_code_fences` fallback.
- **Multiple screenshots sent in ONE vision LLM call, not N separate
  calls**, with the prompt explicitly told they're the same page in
  scroll order — otherwise the model has no way to know screenshot 2
  isn't a totally different page, and might flag "missing CTA" on a
  mid-page screenshot when one exists higher up. This principle now
  extends across pages too: `ux_review_node` calls
  `review_screenshots(url, screenshot_paths)` once PER PAGE (not once per
  screenshot), keeping the "all screenshots of one page in a single call"
  rule intact while adding a page-level loop on top of it.
- **`gpt-4o-mini`, not a frontier model**, used everywhere — deliberate
  cost control given the user has no budget to spend on this project.

---

## 7. Known bugs already hit and fixed (don't reintroduce these)

| Bug | Fix |
|---|---|
| `Path.read_text()` on Windows defaults to `cp1252`, crashes on Lighthouse's UTF-8 JSON output (emoji/smart-quotes in page content) | Always pass `encoding="utf-8"` explicitly on every `read_text`/`write_text` call |
| Lighthouse `NO_LCP` / `EPERM` crash on Windows with old headless mode | Use `--chrome-flags=--headless=new` (not bare `--headless`). NOTE: even with this flag, some individual pages (e.g. `/booking`, `/about` on a real test site) still hit `NO_LCP` — this is a per-page paint-trace limitation, not a flag misconfiguration. `audit_url()`'s existing except-block retry (drop the `performance` category, keep `seo,accessibility`) is the correct handling, already in place and verified working. The accompanying Windows `EPERM` temp-dir cleanup error from `chrome-launcher` is separate noise (antivirus/file-lock related) riding on the same failed process — cosmetic, does not affect the retry. |
| `default_factory=datetime.utcnow()` (called immediately) vs `default_factory=datetime.utcnow` or `lambda: ...` (deferred) — Pydantic error `'datetime.datetime' object is not callable` | Always wrap in `lambda:` for `default_factory` unless passing a bare function reference with no arguments |
| `extract_links()` didn't resolve relative hrefs (`/about`) to absolute URLs before checking if internal — silently dropped almost all links on any real site | Always `urljoin(base_url, href)` BEFORE any internal/external check |
| `is_internal_link` did substring `startswith` matching — `"site.com.evil.com".startswith("site.com")` is `True`, a spoofing gap | Compare `urlparse(url).netloc` (hostname) for exact equality instead |
| `normalize_url()` strips the URL scheme entirely — breaks direct use for Playwright navigation (`page.goto()` needs a full URL) | `WebsiteCrawler._with_scheme()` re-attaches the scheme before every `page.goto()` call; normalized (scheme-less) strings are only used as the BFS visited-set dedup key |
| `wait_until="networkidle"` in Playwright times out (15s+) on real sites with chat widgets/analytics that never go fully idle | Use `wait_until="load"` with `timeout=30000` instead |
| `save_manifest()` crashed with `FileNotFoundError` if the crawl produced zero successful pages (directory never got created) | `path.parent.mkdir(parents=True, exist_ok=True)` before every write, don't assume a directory exists |
| Editing a stale local mirror of `schemas.py` and handing back a "partial" snippet caused the user to accidentally delete `PageResult`/`CrawlResult` when merging | When schema drift is suspected, replace the WHOLE file rather than patching a snippet against an assumed-current version |
| `agent/graph.py`'s `ux_review_node` still called the OLD single-arg `review_screenshots(state.screenshot_paths)` after `vision_review.py`'s signature changed to `review_screenshots(url, screenshot_paths)` — crashed with `TypeError: missing 1 required positional argument` | Migrate the CALLER, not just the callee, whenever a shared function's signature changes — `ux_review_node` was rewritten to loop over `state.crawl_result.pages` and call the new two-arg signature per page. Fixed and verified this session. |
| `audit/lighthouse.py` ended up with TWO definitions of `run_lighthouse()` (an old no-`categories`-param version and a new one) after an edit — Python silently keeps only the last one, so the first is dead code that can confuse future reading of the file | Not yet cleaned up — delete the first (shadowed) definition next time the file is touched. |
| OpenAI `429 insufficient_quota` during a live `ux_review_node` run — NOT a code bug, the account's OpenAI billing/credit balance was exhausted | Check platform.openai.com billing/credit balance and confirm `OPENAI_API_KEY` in `.env` points to a funded project (multi-project accounts can have a $0 key active by mistake); also check the org's usage-limits page for a hard cap set below the actual balance. |

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
above for actual code status. Note: the eventual FastAPI surface is also
why input-independence (moving `max_depth`/`max_pages` off in-node
`input()` calls and onto state, §4) matters now — `input()` calls
anywhere in a node body will hang a future non-interactive caller.

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

Note: `crawl_site()`'s own default parameters (`max_pages=10, max_depth=2`)
no longer match the defaults used in the interactive prompt path
(`max_depth=1, max_pages=5`) now that `max_depth`/`max_pages` live on
`SiteDoctorState` and are always passed explicitly from the graph. Worth
reconciling both to the same numbers so a standalone
`python -m crawler.website_crawler` run and a full graph run don't
silently behave differently.

---

## 10. Immediate next steps (roughly in priority order)

1. **Confirm/finalize this session's in-flight changes** before building
   further on top of them:
   - `SiteDoctorState.max_depth` / `max_pages` — confirm field names,
     defaults, and exactly which node now owns the `input()` prompt for
     them (candidates: fold into `check_selection_node`, or a new
     dedicated setup node before `crawl_node`).
   - `UXSuggestion.page_url` — confirm it's actually in `schemas.py` and
     that `review_screenshots()` is stamping it correctly (needed for any
     grouped UX report to work).
   - Resolve the OpenAI `insufficient_quota` billing issue so
     `ux_review_node` can be verified end-to-end against a live vision
     call (multi-page loop + resilience logic already verified structurally,
     just not the actual model output/report yet).
2. **Wire up `save_ux_report()`** in `ux_review/vision_review.py` (writes
   a markdown report grouping `ux_suggestions` by `page_url` as headings)
   plus the matching `ux_report_path(crawl_id)` helper in
   `crawler/storage.py`, and call it from `ux_review_node`. Also decide
   how to represent a page whose review call FAILED (quota error, etc.)
   vs. a page that was reviewed and had zero issues — currently
   `save_ux_report` as sketched would render a failed page identically to
   a clean one ("No issues found"), which is misleading.
3. **Clean up `audit/lighthouse.py`**: delete the shadowed first
   `run_lighthouse()` definition (dead code, only the second one with the
   `categories` param actually runs).
4. **Finish `triage_node`** — the original first task, deferred multiple
   times. Needs to loop over `state.audit_before` (list per page), rank
   issues by severity, and generate `plain_language_summary` per issue via
   an OpenAI call. The `aggregate_for_llm()` helper sketched this session
   (collapses per-page `AuditResult`s into one compact dict) is a good
   starting point for the "never send raw tool output" constraint here.
   Reference: `ux_review/vision_review.py`'s JSON-parsing pattern
   (`_strip_code_fences` / `_parse_suggestions`) for how the rest of the
   codebase structures LLM calls — also consider adding
   `response_format={"type": "json_object"}` to any new OpenAI calls
   (proposed for vision_review this session, not yet confirmed applied;
   worth adopting as the default pattern going forward).
5. **Migrate `security_audit_node` to multi-page**, same pattern as
   `seo_audit_node`/`ux_review_node`'s per-page loop + try/except.
6. **`fix_node` → `approve_node` → `apply_node` → `reaudit_node`** — the
   full act/verify/retry loop, still entirely unbuilt.
7. Consider tightening `UXSuggestion.category` from a bare `str` to a
   `UXCategory(str, Enum)` mirroring the 13 category values now named in
   `VISION_REVIEW_PROMPT`, so a malformed category from the model fails
   fast at Pydantic parse time instead of silently passing through.

---

## 11. User context (for tone/pacing in a new session)

- Knows LangChain/LangGraph fundamentals already; does NOT want code
  fully written for them by default — prefers being given the
  shape/hints and writing it themselves, with review after. (This shifted
  over the course of the conversation toward more direct "just give me
  the code" requests during debugging-heavy stretches — use judgment on
  which mode is wanted based on how the request is phrased.) This session
  skewed toward direct code/diffs during active debugging (the graph.py
  TypeError, the lighthouse errors), consistent with that pattern.
- Has an OpenAI API key, explicitly on a limited/no budget — always
  default to `gpt-4o-mini`, minimize token usage, never send raw/unfiltered
  tool output to an LLM. Currently blocked on an `insufficient_quota`
  billing issue on that key/account (see §7) — not a code problem.
- On Windows (PowerShell), Python 3.14, venv — several encoding/subprocess
  quirks are Windows-specific (see §7).
- Wants this to be a genuine portfolio piece / meaningful contribution,
  not a "RAG wrapper" — the act-verify-retry loop is the point, protect
  that framing when suggesting features.
- Actively iterating fast across files (lighthouse.py -> vision_review.py
  -> graph.py -> storage.py -> schemas.py) in short back-and-forth turns
  this session; several proposed changes (page_url field, UXCategory enum,
  response_format json mode, save_ux_report/ux_report_path,
  aggregate_for_llm) were suggested but not all confirmed as applied in
  actual code by end of session — see the "PENDING"/"PROPOSED" markers
  throughout this doc and the checklist in §10 item 1 before assuming
  they exist.