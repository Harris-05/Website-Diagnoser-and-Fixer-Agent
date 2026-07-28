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
                                 ux_report_path()-style helper still not
                                 explicitly reconfirmed in this file's own
                                 code, but save_ux_report() (in
                                 vision_review.py) IS confirmed wired up
                                 and working via graph.py this session --
                                 verify storage.py's exact implementation
                                 next time this file is opened.
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
                                 Takes (url, screenshot_paths) and stamps
                                 the URL onto each returned suggestion
                                 (confirmed). Also exports save_ux_report()
                                 (grouped markdown report per crawl,
                                 confirmed imported and called from
                                 graph.py's ux_review_node). Prompt
                                 substantially rewritten in an earlier
                                 session — see §6. Still open:
                                 response_format={"type":"json_object"}
                                 and a UXCategory enum were both proposed
                                 but not confirmed applied.
    security/
        verification.py       <- NEW this session. Domain-ownership
                                 verification gate for future active
                                 security tooling. See §6 "Active security
                                 tooling" and the new §12 for full detail.
                                 Confirmed written and explained to the
                                 user, NOT yet tested against a real
                                 domain (needs a domain the user actually
                                 controls DNS for) or unit-tested with a
                                 mocked DNS response.
                                 PLANNED, not yet written: passive_checks.py
                                 (relocated + multi-page-migrated version
                                 of the current security_audit_node logic)
                                 and active_engine.py (ZAP/Nuclei/SQLMap/
                                 Dalfox/Nmap/k6 wrappers, each gated behind
                                 verification.require_verified() as the
                                 first line of every function).
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
| `crawl_node` | **Done** | Calls `crawl_site(state.url, max_pages=state.max_pages, max_depth=state.max_depth, isux=...)`. Confirmed fully migrated off in-node `input()` — it now reads `state.max_depth`/`state.max_pages` directly, set entirely by `check_selection_node` upfront (see below), so `crawl_node` itself is fully input-independent (important for the eventual FastAPI surface, which can't call `input()`). `isux` is derived from `"ux" in state.selected_checks` and passed through so screenshots are ONLY captured when UX review is actually selected. Still populates `state.crawl_result` (the real multi-page result) AND mirrors the home page into the legacy `local_copy_path`/`screenshot_paths` fields for any code not yet migrated. Also received a real bug fix this session — see §7 "SPA hydration" and "screenshot spinner" entries — for sites that render client-side (React/Vite SPAs) after Playwright's `wait_until="load"` fires. |
| `check_selection_node` | **Done, had a real bug this session** | Prompts for checks + max_depth + max_pages, all in one place (single upfront human-in-the-loop step, per the "consolidate all CLI prompts" decision). Had a bug where `state.max_depth = max_d` / `state.max_pages = max_p` mutated the `state` argument directly instead of including those keys in the node's **returned** dict — LangGraph doesn't pick up in-place mutations of the input state object, only what a node explicitly returns, so `max_depth`/`max_pages` silently stayed at their Pydantic default of `None` all the way into `crawl_node`, which then silently fell back to `crawl_site()`'s own hardcoded signature defaults (`max_pages=10, max_depth=2`) regardless of what the user typed. Fixed by adding `"max_depth": max_d, "max_pages": max_p` to the returned dict. **General rule going forward: LangGraph nodes must never rely on mutating the `state` object in place — always return the changed fields.** |
| `route_checks` | **Done** | Conditional-edge function; maps `selected_checks` -> node names, only those nodes actually get invoked (verified: selecting only `seo` results in `ux_suggestions: []` and `security_findings: []` because those branches never ran, not because they ran and found nothing). |
| `seo_audit_node` | **Done** | Runs Lighthouse against **every** page in `crawl_result.pages`, not just the start URL. Returns `audit_before` as a **list** of `AuditResult`, one per page (each `AuditResult` already carries its own `.url`). Wrapped in try/except per-page so one page's Lighthouse failure doesn't kill the whole run. Verified end-to-end against two real multi-page sites (autogloss.pk, quran-learning-portal-frontend.vercel.app) — all pages returned scores/issues correctly. `NO_LCP` LanternError + Windows `EPERM` temp-cleanup errors are noisy stderr from Lighthouse/chrome-launcher but do NOT break the run — the existing performance-category retry (`audit_url`'s except block) already handles `NO_LCP` pages correctly; seen again this session on the Vercel test site and still handled fine. |
| `ux_review_node` | **Done, fully confirmed this session** | Loops over `state.crawl_result.pages`, calling `review_screenshots(page.url, page.screenshot_paths)` per page inside a try/except (mirrors `seo_audit_node`'s per-page resilience pattern), accumulates into one `ux_suggestions` list, and calls `save_ux_report(state.crawl_result.crawl_id, all_suggestions)` before returning — confirmed actually wired in and imported in `graph.py` this session (previously only proposed). The earlier `TypeError: review_screenshots() missing 1 required positional argument` bug is fixed and stayed fixed across this session's runs. Still blocked end-to-end verification on an OpenAI `insufficient_quota` (429) billing issue on the user's account (unrelated to code, seen again this session) — structurally confirmed working (correctly iterates every page, per-page try/except holds), just not yet verified against a real successful vision-model response. |
| `security_audit_node` | **Done (passive-only), single-page still a known gap** | Full implementation now confirmed in code: checks 5 HTTP security headers (HSTS, CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy) via a single passive GET request, plus TLS certificate validity/expiry and a "not served over HTTPS" check via a standard TLS handshake — each missing/failing check becomes an `Issue` with `Category.SECURITY` and an appropriate `Severity`. Explicitly does NOT do active scanning of any kind, consistent with the hard constraint in §6. Still only audits `state.url` (home page) — has NOT been migrated to loop over `crawl_result.pages` the way `seo_audit_node`/`ux_review_node` were. This is now a bigger decision than just "add a loop," though — see the new §6 "Active security tooling" entry and §10 for why active-tool escalation (a much bigger feature the user wants eventually) needs a verification gate designed BEFORE that expansion happens. |
| `triage_node` | **STUB** | Guard logic updated for the new list-based `audit_before`, but the actual ranking/plain-language-summary LLM call is not yet implemented. This was the very first node the user was asked to write and it's been deferred through several detours. An `aggregate_for_llm()` helper was sketched in an earlier session (see §6) to collapse the per-page `audit_before` list into one compact dict for this node's future LLM call — not yet wired in. |
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
                            # STILL PROPOSED, not yet confirmed applied:
                            # tighten to a UXCategory(str, Enum) mirroring
                            # the 14 category strings now used in
                            # VISION_REVIEW_PROMPT (see §6), so a
                            # malformed category from the model fails at
                            # parse time instead of silently passing
                            # through as a random string.
    severity: Severity
    observation: str
    recommendation: str
    page_url: str | None = None   # CONFIRMED this session — which page
                                   # this suggestion is about.
                                   # review_screenshots() stamps this after
                                   # parsing the model's response, and
                                   # save_ux_report() groups by it. Both
                                   # confirmed actually wired into
                                   # graph.py/vision_review.py now, not
                                   # just proposed.

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
    max_depth: int | None = None   # CONFIRMED this session -- lives on
                                    # state, defaults to None. Set entirely
                                    # by check_selection_node (single
                                    # upfront prompt), read directly by
                                    # crawl_node. NOTE the earlier bug: the
                                    # first implementation set this via
                                    # direct state mutation
                                    # (state.max_depth = max_d) inside
                                    # check_selection_node instead of
                                    # returning it, so it silently stayed
                                    # None all the way to crawl_node, which
                                    # then silently fell back to
                                    # crawl_site()'s own hardcoded defaults
                                    # (2/10). Fixed by returning
                                    # {"max_depth": max_d, ...} from the
                                    # node instead. See §7.
    max_pages: int | None = None   # CONFIRMED this session -- same as
                                    # above. Defaults to 10 at the input()
                                    # prompt if left blank
                                    # (`int(input(...).strip() or 10)`),
                                    # which now matches crawl_site()'s own
                                    # signature default of 10 -- the
                                    # earlier "defaults don't match" note
                                    # in §9 is resolved for max_pages.
                                    # max_depth's input-prompt default is 2,
                                    # also matching crawl_site()'s default
                                    # of 2 -- fully reconciled now.
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
- **Active security tooling (ZAP active scan, SQLMap, Dalfox, Nuclei,
  Nmap, k6 load/stress/spike) is deliberately OUT of the current build,
  and must NOT be added to the default "audit any URL" flow — this was
  discussed at length this session and is a firm architectural line, not
  just a style preference.** The user's intent is for Site Doctor to
  become a genuinely production-level agent, and does intend to use these
  tools eventually, but ONLY against sites they own or have explicit
  permission to test — never as a default option available for any
  arbitrary URL a user types in, which is how Site Doctor's check-selection
  flow currently works for everything else. The reasoning: every one of
  those tools actively attacks the target (injects payloads, floods it
  with traffic, exploits CVEs, port-scans infrastructure) rather than
  passively observing it, and running them against infrastructure without
  clear authorization is a real legal exposure (CFAA and equivalents)
  regardless of good intent or portfolio-project framing — this is the
  same category of problem the user already caught and fixed once before
  (see the "security off by default, passive-only" decision above this
  bullet, which predates this session).
  **Agreed direction for when active tooling IS eventually built** (none
  of this is implemented yet — it's a design agreement, not code):
    - A checkbox/self-attestation ("I have permission") is NOT sufficient
      authorization on its own and should not be the gate for unlocking
      active tools.
    - Real domain-ownership verification is needed first — e.g. a DNS TXT
      record challenge or a specific file-upload challenge at the site
      root, the same pattern Google Search Console and most SaaS platforms
      use, checked by Site Doctor before active scanning becomes
      selectable for that domain at all.
    - Verification should be scoped and stored PER DOMAIN (not per
      session) — e.g. a `(domain, verified_at, verification_method)`
      record — so re-auditing a previously-verified domain doesn't require
      re-verification, but auditing any different domain always does. This
      also creates an audit trail.
    - Passive security (current implementation: headers + TLS) stays
      available to anyone with no verification required, exactly as it is
      today — this line does not change.
    - Active security should be a genuinely separate mode architecturally,
      not just another flag inside `selected_checks` sitting next to
      `seo`/`ux`/passive `security` — the CLI/UI shouldn't even offer it
      as a selectable option until domain verification passes.
    - Even after verification, tools should still be staged/phased for
      cost and target-impact reasons (baseline tools like ZAP-baseline/
      Nuclei/SSL Labs first; SQLMap/Dalfox only conditionally, if Phase 1
      surfaces a relevant attack surface; k6 load/stress/spike testing
      behind its own additional explicit confirmation even after domain
      verification, since those tools deliberately degrade the target's
      availability, which is a materially different risk than the others).
    - `verify_ownership_node` (a DNS TXT check node sitting in front of
      any future active-tool escalation) was proposed as the mechanism
      that would make "explicit permission" actually enforceable rather
      than just stated — not yet designed in detail or built.

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
| OpenAI `429 insufficient_quota` during a live `ux_review_node` run — NOT a code bug, the account's OpenAI billing/credit balance was exhausted. Recurred again this session against a second test site, still unresolved. | Check platform.openai.com billing/credit balance and confirm `OPENAI_API_KEY` in `.env` points to a funded project (multi-project accounts can have a $0 key active by mistake); also check the org's usage-limits page for a hard cap set below the actual balance. |
| **SPA hydration gap ("first screenshot is empty / only 1 page crawled"):** React/Vite/other client-rendered SPAs can finish Playwright's `wait_until="load"` before the app has actually mounted — `page.content()` at that moment can be just a loading-spinner shell inside `<div id="root">`, with zero real `<a href>` tags anywhere, which silently truncated BFS crawling to just the start page (looked like a "not enough links found" bug, but was actually a timing bug — verified via a real captured HTML snapshot showing only the spinner markup and Vite `modulepreload` chunk links, no rendered content) | In `WebsiteCrawler.crawl()`, right after `page.goto(...)` and before `html = page.content()`, add a short bounded wait: `page.wait_for_function("document.querySelectorAll('a[href]').length > 0", timeout=8000)` wrapped in try/except (no-op on static sites where links already exist; harmlessly times out on genuinely link-less pages). Fixed and verified this session — a previously single-page-only SPA (quran-learning-portal-frontend.vercel.app) correctly crawled 10 pages afterward. Note: a sitemap.xml-based fallback is still a good idea for the genuinely harder case of `onClick`/`history.pushState()`-only routing with NO real `<a href>` tags anywhere even after full hydration — proposed, not built. |
| **Screenshot of the loading spinner ("first screenshot is a scroll wheel/spinner"):** even after the link-hydration wait above, `_capture_screenshots()` could still fire before the REST of the page (hero image, data-fetched cards, etc.) finished rendering — finding a nav link doesn't mean the whole page is visually done loading | Added a short, bounded `page.wait_for_load_state("networkidle", timeout=5000)` (wrapped in try/except) inside `_capture_screenshots()`, right before the scroll/screenshot loop begins. Deliberately NOT used at the `goto()` level (some sites never truly idle due to chat widgets/analytics, per the earlier `wait_until="load"` decision) — but safe here since it only delays screenshot capture and never blocks the crawl loop itself. Fixed this session. |
| **LangGraph state-mutation bug ("max_depth/max_pages typed by the user never reached crawl_node, silently fell back to hardcoded defaults 2/10"):** `check_selection_node` set `state.max_depth = max_d` / `state.max_pages = max_p` directly on the input `state` object instead of including those keys in its RETURNED dict. LangGraph only merges what a node explicitly returns between steps — it does not pick up in-place attribute mutations on the state object it hands a node, even though nothing raises an error, so this failed completely silently (confirmed via the final printed state showing `max_depth: 2, max_pages: 10` even though the user had typed `15` and `60`) | Add the changed fields to the node's returned dict instead: `return {"selected_checks": selected, "max_depth": max_d, "max_pages": max_p}`. Fixed this session. **General rule for every future node: never rely on mutating the `state` argument in place — LangGraph nodes must return a dict of the fields that changed, full stop.** This is worth double-checking against every existing node next time each is touched, since it's an easy mistake to reintroduce and fails with no error message at all. |
| **Misconception (not an actual bug, but worth recording since it caused real alarm mid-session): "one vision LLM call eats ~1 million tokens per page."** This came from logging `len(encoded_image)` — the base64 string length — and mistaking that for a token count. Base64 length is a text-encoding artifact of getting binary image bytes through JSON; it has no direct relationship to how many tokens OpenAI actually bills. | Clarified via a live web search: OpenAI decodes the base64 back to real pixel data server-side BEFORE tokenizing, and `gpt-4o-mini` specifically tokenizes images via a 32×32-pixel patch count, auto-capped at ~1,536 tokens per image no matter how large/high-resolution the source file is. With 4 screenshots/page, real image-token cost is roughly ~6,000 tokens/page max, not "millions." Across a ~10-page UX review run, total cost is tens of thousands of tokens — fractions of a cent at `gpt-4o-mini`'s $0.15/million input rate. The recurring `insufficient_quota` 429 errors are a genuine $0-balance/billing problem on the account, unrelated to this. Also confirmed: there is no way to send OpenAI's Chat Completions API a "raw image" instead of base64/URL — those are the only two supported transport methods for `image_url`, and a locally-stored screenshot with no public URL has no third option; the current code's approach (base64 data URI) is already correct and is not a cost problem. A `_encode_image()` resize-to-JPEG tweak (max ~1280px wide, quality 75, via Pillow) was proposed purely for upload-latency/reliability reasons, NOT to fix a token-cost bug that turned out not to exist — not yet confirmed applied to `vision_review.py`. |

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

Note (RESOLVED this session): `crawl_site()`'s own default parameters
(`max_pages=10, max_depth=2`) now match the fallback defaults used in
`check_selection_node`'s interactive prompts (`int(input(...).strip() or 2)`
for depth, `or 10` for pages), so a standalone
`python -m crawler.website_crawler` run and a full graph run behave
consistently on blank input. `SiteDoctorState.max_depth`/`max_pages`
themselves default to `None` on the Pydantic model — they're always
expected to be set by `check_selection_node` before `crawl_node` runs, not
relied on as a schema-level default in normal graph usage.

---

## 10. Immediate next steps (roughly in priority order)

1. **Resolve the OpenAI `insufficient_quota` billing issue** so
   `ux_review_node` can be verified end-to-end against a live vision call
   — the multi-page loop, resilience logic, `page_url` stamping, and
   `save_ux_report()` call are all now confirmed wired in and structurally
   correct; this is purely a billing/account blocker, not a code task.
2. **Add sitemap.xml checking** as a first step in `crawl_site()`/
   `WebsiteCrawler.crawl()`, before falling back to BFS — the hydration-wait
   fix (§7) solves the "SPA renders links late" case, but a genuinely
   harder case remains: SPAs that route via `onClick`/`history.pushState()`
   with NO real `<a href>` tags anywhere, even after full hydration. No
   amount of waiting fixes that; sitemap.xml (or a `Sitemap:` line in
   robots.txt) is the reliable fallback source of the page list there.
3. **Clean up `audit/lighthouse.py`**: delete the shadowed first
   `run_lighthouse()` definition (dead code, only the second one with the
   `categories` param actually runs). Still not done as of this session.
4. **Finish `triage_node`** — the original first task, deferred multiple
   times. Needs to loop over `state.audit_before` (list per page), rank
   issues by severity, and generate `plain_language_summary` per issue via
   an OpenAI call. The `aggregate_for_llm()` helper sketched in an earlier
   session (collapses per-page `AuditResult`s into one compact dict) is a
   good starting point for the "never send raw tool output" constraint
   here. Reference: `ux_review/vision_review.py`'s JSON-parsing pattern
   (`_strip_code_fences` / `_parse_suggestions`) for how the rest of the
   codebase structures LLM calls — also consider adding
   `response_format={"type": "json_object"}` to any new OpenAI calls
   (proposed for vision_review, still not confirmed applied there either;
   worth adopting as the default pattern going forward for every OpenAI
   call in the codebase).
5. **Migrate `security_audit_node` to multi-page**, same per-page loop +
   try/except pattern as `seo_audit_node`/`ux_review_node`. Note: do this
   BEFORE any active-tooling work, and keep it scoped to the existing
   passive checks only (headers + TLS) — this is unrelated to, and should
   not be entangled with, the active-tooling design work in item 6 below.
6. **Design (don't build yet) the domain-verification gate** for future
   active security tooling — see the full §6 "Active security tooling"
   entry for the agreed direction (DNS TXT or file-upload ownership
   challenge, per-domain verification record, separate architectural mode
   from passive security, staged phases even after verification). This is
   a substantial feature on its own and deserves its own design pass
   before any of ZAP/SQLMap/Dalfox/Nuclei/Nmap/k6 get integrated — treat
   `verify_ownership_node` as the first concrete piece of that work when
   it's picked up.
7. **`fix_node` → `approve_node` → `apply_node` → `reaudit_node`** — the
   full act/verify/retry loop, still entirely unbuilt.
8. Consider tightening `UXSuggestion.category` from a bare `str` to a
   `UXCategory(str, Enum)` mirroring the 13 category values now named in
   `VISION_REVIEW_PROMPT`, so a malformed category from the model fails
   fast at Pydantic parse time instead of silently passing through. Still
   proposed, not applied.
9. **Audit every existing node for the same "mutate state in place instead
   of returning it" bug class** found in `check_selection_node` this
   session (§7) — it's a silent failure mode with no error message, so it's
   worth a deliberate one-time check across `crawl_node`, `seo_audit_node`,
   `ux_review_node`, and `security_audit_node` rather than assuming it's
   isolated to the one instance already found and fixed.

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
  -> graph.py -> storage.py -> schemas.py -> website_crawler.py) in short
  back-and-forth turns across sessions; some proposed changes (UXCategory
  enum, response_format json mode) are still not confirmed applied in
  actual code — see the "PROPOSED"/"still open" markers throughout this
  doc before assuming they exist. Other items proposed in an earlier
  session (page_url field, save_ux_report/ux_report_path,
  max_depth/max_pages on state) were confirmed actually applied this
  session via real pasted code and terminal output.
- Explicitly stated goal: wants Site Doctor to become a genuinely
  production-level agent over time, including active security tooling
  (ZAP, SQLMap, Dalfox, Nuclei, Nmap, k6) eventually — but ONLY against
  sites they own or have explicit permission to test, never as a default
  option for arbitrary URLs. Understands and agrees with the legal
  reasoning for why a simple confirmation checkbox isn't sufficient
  authorization for that (see §6) — this isn't a constraint being imposed
  against their wishes, it's an agreed design direction for how to build
  the production version safely. Don't relitigate this from scratch next
  session; the agreement is already documented in §6.