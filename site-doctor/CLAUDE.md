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

The end goal (not yet fully built): for mechanically verifiable issues,
the system proposes a fix, gets human approval, applies it to a **local**
copy, and re-audits to verify the fix actually worked — an act → verify →
retry loop. This is deliberately NOT a "RAG wrapper" — the value is in
this verification loop, not summarization. The pipeline now runs
`triage -> fix (suggest-only) -> [human decision point] -> approve/apply/
reaudit (the real mechanical loop, still unbuilt)` — see §4 and §15 for
why `fix_node` is explicitly a PROPOSE step, not the loop itself.

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
| LLM | OpenAI (`gpt-4o-mini`) | User has OpenAI key, not Anthropic — all LLM calls use `openai` SDK directly, not LangChain wrappers. Both Chat Completions AND the Responses API (for web-search-augmented fix suggestions, see §15) are now in use. |
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
                                 and working via graph.py.
        website_crawler.py    <- WebsiteCrawler class: real BFS traversal.
                                 Takes an `isux` flag threaded through
                                 crawl() -> per-page loop, so screenshots
                                 are only captured when UX review is
                                 selected (see §4/§6).
    audit/
        lighthouse.py         <- wraps Lighthouse CLI subprocess, parses
                                 ONLY tracked audit IDs (never sends raw
                                 report anywhere). Runs per-page now (see
                                 §4). Used to carry two definitions of
                                 run_lighthouse(); the dead shadowed one
                                 has been deleted.
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
    secuirty/
        verification.py       <- Domain-ownership verification gate for
                                 future active security tooling. See §6
                                 "Active security tooling" and §12 for
                                 full detail. Written and explained to the
                                 user, NOT yet tested against a real
                                 domain or via a mocked-DNS unit test.
        passive_checks.py      <- security_audit_node's logic relocated
                                 here, exposed as run_passive_tests(url).
                                 Still home-page-only, not yet migrated to
                                 loop over crawl_result.pages. See §12.
        active_engine.py       <- ZAP/Nuclei/testssl.sh/SQLMap/Dalfox/
                                 Nmap/k6 wrappers. Verification gate is
                                 CURRENTLY COMMENTED OUT on most functions
                                 (deliberately, for isolated testing) — see
                                 §12 for the exact per-function status
                                 table. Must be restored before real use.
    triage/
        engine.py              <- Combines Lighthouse issues, security
                                 findings, and auto-promoted high-severity
                                 UX suggestions into one ranked,
                                 human-readable, fix-loop-ready list
                                 (`triaged_issues`). See §13 for full
                                 design + the composite-key bug found and
                                 fixed. Wired into graph.py's triage_node.
                                 Also had a SECOND bug (str.format()
                                 KeyError on the literal JSON example in
                                 the prompt) caught via a live run — see
                                 §7 and §13.
    fix/
        engine.py               <- NEW this session. Generates a
                                 suggested_solution + fresh per-suggestion
                                 confidence for EVERY triaged Issue (SEO,
                                 security, UX alike) — PROPOSE step only,
                                 no HTML touched, no Fix (before/after)
                                 object created. HIGH/MEDIUM severity
                                 issues get a web-search-augmented
                                 suggestion via the Responses API;
                                 everything else uses a plain Chat
                                 Completions call. See §15 for full design
                                 + the two bugs fixed (legacy tool name,
                                 unsafe dict indexing).
    models/
        schemas.py             <- ALL Pydantic models (see §5). Issue now
                                 has suggested_solution/solution_sources
                                 fields (added this session for fix/suggest.py)
                                 in addition to source_url/source (added
                                 for triage). Full current version
                                 confirmed via a complete file paste this
                                 session, not just a diff.
    tests/                     <- pytest unit tests for the pure functions
                                 (crawler/utils.py, crawler/storage.py,
                                 parse_report(), models/schemas.py, and
                                 triage/engine.py minus its LLM call). No
                                 network, browser, Node or LLM call, so they
                                 run in CI. See §16.
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

**Important clarification confirmed this session:** `fix_node` is NOT the
apply/verify/retry loop itself. It's a PROPOSE step — for every
`triaged_issues` entry (SEO, security, and UX alike, no source-based
branching) it generates a plain-language suggested fix + a fresh
confidence score, with no HTML read or written and no `Fix` (before/after)
object created. The idea is: `fix_node`'s output becomes a human-readable
report; `approve_node` (still a stub) is where the human is actually
asked whether to let the agent continue into the REAL mechanical
apply/verify/retry loop, which is a separate, later, still-unbuilt
concern (`fix/mechanical.py`-style real patch generation, not this file).

### Node-by-node status

| Node | Status | Notes |
|---|---|---|
| `check_selection_node` | **Done, had a real bug (now fixed)** | Prompts for checks + max_depth + max_pages, all in one place (single upfront human-in-the-loop step). Had a bug where `state.max_depth = max_d` / `state.max_pages = max_p` mutated the `state` argument directly instead of including those keys in the node's **returned** dict — LangGraph doesn't pick up in-place mutations, only what a node explicitly returns, so `max_depth`/`max_pages` silently stayed at defaults regardless of what the user typed. Fixed by adding `"max_depth": max_d, "max_pages": max_p` to the returned dict. **General rule going forward: LangGraph nodes must never rely on mutating the `state` object in place — always return the changed fields.** |
| `crawl_node` | **Done** | Calls `crawl_site(state.url, max_pages=state.max_pages, max_depth=state.max_depth, isux=...)`. Fully migrated off in-node `input()` — reads `state.max_depth`/`state.max_pages` directly, set entirely by `check_selection_node` upfront, so `crawl_node` itself is fully input-independent (important for the eventual FastAPI surface). `isux` is derived from `"ux" in state.selected_checks` so screenshots are ONLY captured when UX review is actually selected. Received a real bug fix — see §7 "SPA hydration" and "screenshot spinner" entries — for sites that render client-side (React/Vite SPAs) after Playwright's `wait_until="load"` fires. |
| `route_checks` | **Done** | Conditional-edge function; maps `selected_checks` -> node names, only those nodes actually get invoked. |
| `seo_audit_node` | **Done** | Runs Lighthouse against **every** page in `crawl_result.pages`. Returns `audit_before` as a **list** of `AuditResult`, one per page. Wrapped in try/except per-page. Verified end-to-end against two real multi-page sites. `NO_LCP`/`EPERM` are noisy stderr, do NOT break the run — handled by the existing performance-category retry. |
| `ux_review_node` | **Done, fully confirmed** | Loops over `state.crawl_result.pages`, calls `review_screenshots(page.url, page.screenshot_paths)` per page inside a try/except, accumulates into `ux_suggestions`, calls `save_ux_report(...)` before returning. Still blocked on an OpenAI `insufficient_quota` (429) billing issue for full end-to-end verification against a live vision response — structurally confirmed working otherwise. |
| `security_audit_node` | **Done (passive-only), relocated, still single-page** | Logic moved to `secuirty/passive_checks.py`, exposed as `run_passive_tests(url)`. `graph.py`'s node is a thin call-through. Same checks as before (5 HTTP headers + TLS validity/expiry + HTTPS presence). Still only audits `state.url` (home page) — not yet migrated to loop over `crawl_result.pages`. Several `graph.py` imports (`socket`, `ssl`, `urllib.request`, `datetime`/`timezone`, `urlparse`, possibly `Category`/`Severity`/`AuditResult`) are now likely dead code left over from before this logic moved out. |
| `triage_node` | **Implemented, one live bug found and fixed this session** | Combines three sources into ONE flat, ranked `triaged_issues` list via `triage/engine.py` — see §13 for full design. A real live-run bug was hit and fixed this session: `TRIAGE_PROMPT.format(issues_json=...)` raised `KeyError: '\n  "issue-id-1"'` because the prompt's literal JSON example (`{"issue-id-1": {...}}`) has unescaped curly braces that `str.format()` tries to interpret as placeholders. Fixed by doubling every literal brace (`{{`/`}}`) in the prompt template, leaving only the real `{issues_json}` placeholder single. This crash happened INSIDE `triage_lighthouse_issues()`, meaning the earlier composite-key collision fix (§13) still has not been confirmed working end-to-end against real repeated-id data — the run never got past the `.format()` call to actually test it. |
| `fix_node` | **Implemented this session, not yet run live** | No longer a stub. Consumes `state.triaged_issues`, calls `suggest_fix(issue)` (from `fix/suggest.py`) on each, returns the same list with `suggested_solution`/`solution_sources`/refined `fix_confidence` populated in place. See §15 for full design, the two bugs found in code review (legacy `web_search_preview` tool name, unsafe dict indexing) and fixed before use, and the schema fields this required. |
| `approve_node` | **STUB** | Not started. Intended as a LangGraph human-in-the-loop interrupt point — the actual point where the human sees `fix_node`'s report and decides whether to let the agent proceed into the real apply/verify/retry loop. |
| `apply_node` | **STUB** | Not started. |
| `reaudit_node` | **STUB** | Not started. |
| `should_retry` | **STUB** | Currently always returns `END` — no retry logic yet. |

---

## 5. Schema reference (models/schemas.py)

Full current file confirmed via a complete paste this session (not a
diff) — this section reflects the actual current state, not a
reconstruction.

```python
class Category(str, Enum):
    SEO = "seo"
    ACCESSIBILITY = "accessibility"
    PERFORMANCE = "performance"
    SECURITY = "security"
    UX = "ux"
    # RESOLVED: UX used to be missing here, and
    # promote_high_severity_ux_suggestions() stamped promoted UX issues with
    # Category.ACCESSIBILITY as an inaccurate placeholder. Both are fixed --
    # the enum has a real UX value and triage/engine.py uses it.

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
    source_url: str | None = None
        # which page this issue came from -- needed once triage_node
        # flattens Lighthouse + security + promoted UX into ONE list
        # (triaged_issues), since each Issue needs to independently know
        # which page's HTML apply_node should patch later. Confirmed applied.
    source: Literal["lighthouse", "security", "ux"] = "lighthouse"
        # which audit produced this issue, and therefore which
        # verification method reaudit_node will need. "security" issues
        # are deliberately NOT auto-fixable via HTML patch -- see §13.
        # Confirmed applied.
    suggested_solution: str | None = None
        # NEW this session -- concrete, actionable fix text generated by
        # fix_node's suggest_fix(). PROPOSE step only, no HTML touched.
    solution_sources: list[str] = Field(default_factory=list)
        # NEW this session -- URLs cited by the web-search-eligible
        # (HIGH/MEDIUM severity) fix suggestion path in fix/suggest.py.
        # Empty for LOW-severity issues (no search call made) and for any
        # issue where the search call failed and fell back.

class UXSuggestion(BaseModel):
    """Judgment-call finding from vision review. NO ground truth to
    re-check mechanically -- surfaced to human, never auto-applied."""
    id: str
    category: str          # e.g. clutter, cta-overload, hierarchy
                            # STILL PROPOSED, not yet confirmed applied:
                            # tighten to a UXCategory(str, Enum).
    severity: Severity
    observation: str
    recommendation: str
    page_url: str | None = None   # confirmed applied and wired through
                                   # review_screenshots()/save_ux_report()

class Fix(BaseModel):
    """A proposed CONCRETE patch (before/after HTML diff) for a specific
    Issue -- distinct from Issue.suggested_solution, which is just
    descriptive text. Fix objects don't exist yet anywhere in the
    pipeline -- fix_node currently only populates suggested_solution,
    never creates a Fix. Fix creation is a LATER, still-unbuilt step
    (planned for whatever comes after approve_node says to proceed)."""
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
    scores: dict[Category, float] = Field(default_factory=dict)
    issues: list[Issue] = Field(default_factory=list)

class PageResult(BaseModel):
    """One crawled page's artifacts + where they live on disk."""
    url: str
    slug: str
    html_path: str
    screenshot_paths: list[str] = Field(default_factory=list)
        # populated conditionally -- only non-empty when the crawl was
        # run with isux=True
    depth: int = 0

class CrawlResult(BaseModel):
    """Full result of a multi-page crawl run."""
    crawl_id: str
    start_url: str
    pages: list[PageResult] = Field(default_factory=list)
    crawled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SiteDoctorState(BaseModel):
    """The full LangGraph state, shared across every node."""
    url: str
    selected_checks: list[str] = Field(default_factory=lambda: ["seo", "ux"])
    crawl_result: Optional[CrawlResult] = None
    local_copy_path: Optional[str] = None           # LEGACY mirror, home page only
    screenshot_paths: list[str] = Field(default_factory=list)   # LEGACY mirror
    audit_before: list[AuditResult] = Field(default_factory=list)  # ONE PER PAGE
    audit_after: list[AuditResult] = Field(default_factory=list)   # for reaudit later
    ux_suggestions: list[UXSuggestion] = Field(default_factory=list)
    security_findings: list[Issue] = Field(default_factory=list)
    fixes: list[Fix] = Field(default_factory=list)   # still always empty --
                                                      # nothing creates a
                                                      # real Fix object yet
    triaged_issues: list[Issue] = Field(default_factory=list)
        # triage_node's output, then fix_node mutates the SAME list in
        # place (adds suggested_solution/solution_sources, refines
        # fix_confidence) rather than creating a separate field for
        # fix_node's output. Deliberate choice, flagged as worth
        # reconsidering if debugging "what changed between triage and
        # fix" ever becomes hard to trace.
    max_retries_per_fix: int = 2
    max_depth: int = 2       # real default now, matches crawl_site()'s own
    max_pages: int = 10      # real default now, matches crawl_site()'s own
```

**Important architectural rule maintained throughout:** `Issue` (mechanical,
verifiable) and `UXSuggestion` (judgment-based, not verifiable) are
DELIBERATELY separate types, never merged into one polymorphic "finding"
type. `Fix` only ever attaches to an `Issue.id`, never a `UXSuggestion`.
This distinction is enforced in the SRS, SDD, and DB design docs too (see
§8) — don't blur it when adding new features. Note that `fix_node`
generating a `suggested_solution` string does NOT violate this rule —
that's descriptive text, not a `Fix` object; real `Fix` creation (with a
before/after HTML diff) is still a separate, later, unbuilt step.

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
  filename collisions and gives downstream consumers one JSON file to
  read.
- **Compatibility-layer migration strategy.** When `CrawlResult`/`PageResult`
  were introduced, old fields (`local_copy_path`, `screenshot_paths`) were
  KEPT and mirrored from the new data, rather than ripping out working
  code.
- **Never send raw tool output to an LLM.** Lighthouse's raw JSON report
  is ~11,000 lines. `audit/lighthouse.py`'s `parse_report()` immediately
  discards everything except a small `TRACKED_AUDITS` allowlist — the raw
  report never reaches an LLM call. This extended into `triage/engine.py`'s
  `aggregate_for_llm()` (collapses per-page issues into a compact list for
  one batched triage call) and into `fix/suggest.py`, which only ever sends
  an issue's `title`/`description`/`category` to the LLM, never raw
  Lighthouse/tool JSON.
- **Screenshots are conditional on UX being selected.** `crawl_site()` /
  `WebsiteCrawler.crawl()` take an `isux: bool` flag; screenshots are only
  captured when `isux=True`.
- **UX review prompt substantially rewritten in an earlier session** —
  frames the model as a senior UX/CRO/accessibility reviewer, 13 named
  categories, explicit anti-hallucination guardrails, severity
  definitions. `response_format={"type": "json_object"}` and a
  `UXCategory` enum were both proposed for this file — STILL not
  confirmed applied there specifically (they ARE confirmed applied in the
  newer `triage/engine.py` and `fix/suggest.py` files).
- **Multiple screenshots sent in ONE vision LLM call per page**, with the
  prompt told they're the same page in scroll order — extended across
  pages too: `ux_review_node` calls `review_screenshots(url,
  screenshot_paths)` once PER PAGE, not once per screenshot.
- **`gpt-4o-mini`, not a frontier model**, used everywhere — deliberate
  cost control. Both Chat Completions AND the Responses API (for
  `fix/suggest.py`'s web-search-augmented suggestions) now use it.
- **Active security tooling (ZAP active scan, SQLMap, Dalfox, Nuclei,
  Nmap, k6 load/stress/spike) is deliberately OUT of the current build,
  and must NOT be added to the default "audit any URL" flow — this is a
  firm architectural line, not a style preference.** The user's intent is
  for Site Doctor to become a genuinely production-level agent, and does
  intend to use these tools eventually, but ONLY against sites they own or
  have explicit permission to test — never as a default option for any
  arbitrary URL. Every one of those tools actively attacks the target
  rather than passively observing it, and running them without clear
  authorization is a real legal exposure (CFAA and equivalents) regardless
  of good intent or portfolio-project framing.
  **Agreed direction for when active tooling IS eventually built** (design
  agreement, not yet fully built — see §12 for exact current status):
    - A checkbox/self-attestation is NOT sufficient authorization on its
      own.
    - Real domain-ownership verification needed first — a DNS TXT record
      challenge (same pattern Google Search Console uses), checked before
      active scanning becomes selectable for that domain at all.
    - Verification scoped and stored PER DOMAIN, permanently, not per
      session.
    - Passive security stays available to anyone, no verification
      required — this line does not change.
    - Active security is a genuinely separate architectural mode, not
      just another flag inside `selected_checks`.
    - Tools still staged/phased even after verification (baseline tools
      first; SQLMap/Dalfox only conditionally; k6 load/stress/spike
      behind its OWN additional explicit confirmation even after domain
      verification, since it deliberately degrades target availability).
- **`fix_node` is deliberately a PROPOSE-only step, not the mechanical fix
  loop itself** — decided explicitly this session. It runs uniformly
  across ALL triaged issues regardless of `source` (SEO, security, UX
  alike), generating a suggested_solution + a fresh per-suggestion
  confidence score, with zero HTML access and zero `Fix` object creation.
  The actual apply/verify/retry mechanics stay entirely in
  `apply_node`/`reaudit_node`, gated behind a human explicitly saying "go
  ahead" in `approve_node`. This means a user who only wants
  recommendations (never wants the agent auto-editing anything) can stop
  right after this report — a deliberate, valued property of the design,
  not an oversight.

---

## 7. Known bugs already hit and fixed (don't reintroduce these)

| Bug | Fix |
|---|---|
| `Path.read_text()` on Windows defaults to `cp1252`, crashes on Lighthouse's UTF-8 JSON output | Always pass `encoding="utf-8"` explicitly on every `read_text`/`write_text` call |
| Lighthouse `NO_LCP` / `EPERM` crash on Windows with old headless mode | Use `--chrome-flags=--headless=new`. `NO_LCP` on individual pages is a per-page paint-trace limitation, not a flag issue — `audit_url()`'s except-block retry (drop `performance`, keep `seo,accessibility`) handles it correctly, verified repeatedly. `EPERM` from `chrome-launcher` temp-dir cleanup is separate cosmetic noise. |
| `default_factory=datetime.utcnow()` (called immediately) vs `default_factory=datetime.utcnow` / `lambda: ...` (deferred) | Always wrap in `lambda:` for `default_factory` unless passing a bare zero-arg function reference |
| `extract_links()` didn't resolve relative hrefs to absolute URLs before checking internal/external | Always `urljoin(base_url, href)` BEFORE any internal/external check |
| `is_internal_link` did substring `startswith` matching — spoofable (`"site.com.evil.com".startswith("site.com")` is `True`) | Compare `urlparse(url).netloc` for exact equality instead |
| `normalize_url()` strips the URL scheme, breaking direct Playwright navigation | `WebsiteCrawler._with_scheme()` re-attaches the scheme before every `page.goto()`; scheme-less strings only used as the BFS dedup key |
| `wait_until="networkidle"` times out on sites with chat widgets/analytics that never idle | Use `wait_until="load"` with `timeout=30000` |
| `save_manifest()` crashed with `FileNotFoundError` on zero successful pages | `path.parent.mkdir(parents=True, exist_ok=True)` before every write |
| Editing a stale local mirror of `schemas.py` and handing back a partial snippet risked dropping fields on merge | When schema drift is suspected, replace the WHOLE file rather than patching a snippet against an assumed-current version — this was actually done correctly this session (full `schemas.py` paste + full corrected file returned). |
| `ux_review_node` called the OLD single-arg `review_screenshots(...)` after the function's signature changed to two args | Migrate the CALLER, not just the callee, whenever a shared function's signature changes |
| `audit/lighthouse.py` had TWO definitions of `run_lighthouse()` — the first was dead code, silently shadowed by the second | Deleted the first definition. Both call sites already resolved to the second, and `run_lighthouse(url)` still works since `categories` has a default. |
| OpenAI `429 insufficient_quota` during live `ux_review_node` runs — NOT a code bug, account billing/credit balance exhausted, recurred multiple times, still unresolved | Check platform.openai.com billing/credit balance, confirm `OPENAI_API_KEY` points to a funded project, check org usage-limits page |
| **SPA hydration gap** — React/Vite SPAs can finish `wait_until="load"` before the app mounts, leaving `page.content()` as just a loading-spinner shell with zero real links, silently truncating BFS crawling to one page | Add `page.wait_for_function("document.querySelectorAll('a[href]').length > 0", timeout=8000)` (try/except-wrapped) right after `page.goto()`, before reading `page.content()`. Fixed and verified — a previously single-page-only SPA correctly crawled 10 pages afterward. A sitemap.xml fallback is still worth building for the harder case of `onClick`/`history.pushState()`-only routing with NO real `<a href>` anywhere even after hydration — proposed, not built. |
| **Screenshot of the loading spinner** — even after the link-hydration wait, the REST of the page could still be mid-render when `_capture_screenshots()` fires | Added a short, bounded `page.wait_for_load_state("networkidle", timeout=5000)` (try/except-wrapped) inside `_capture_screenshots()`, right before the scroll/screenshot loop. Deliberately not used at `goto()` level (some sites never idle) — safe here since it only delays screenshot capture. Fixed. |
| **LangGraph state-mutation bug** — `check_selection_node` mutated `state.max_depth`/`state.max_pages` directly instead of returning them; LangGraph doesn't pick up in-place mutations, so the typed values silently never reached `crawl_node` | Return the changed fields explicitly instead. **General rule: LangGraph nodes must never rely on mutating `state` in place.** Worth auditing every node for this pattern — still an open item (§10/§14). |
| **Misconception, not a real bug:** "one vision LLM call eats ~1 million tokens per page," from mistaking base64 string length for token count | Confirmed via web search: OpenAI decodes base64 to real pixels before tokenizing; `gpt-4o-mini` tokenizes images via a 32×32-pixel patch count, capped at ~1,536 tokens/image regardless of source file size. Real cost across a full multi-page UX review run is tens of thousands of tokens — fractions of a cent. The `insufficient_quota` errors are a genuine billing issue, unrelated. Also confirmed: base64 data URI is the ONLY viable transport for locally-stored screenshots with no public URL — not a workaround, the correct approach already in use. |
| **`triage/engine.py` issue-ID collision across pages** — the first version's lookup was keyed by bare `issue.id` (e.g. `"heading-order"`), which recurs across many pages of the same site, silently overwriting/collapsing distinct per-page issues | Key both `aggregate_for_llm()` and `triage_lighthouse_issues()`'s lookup on a composite `f"{page_url}::{issue.id}"` string instead, leaving the real `Issue.id` untouched (still needed as the raw Lighthouse audit key for `reaudit_node` later). Fixed in code review — **still not confirmed working against a live run**, since the very next live run hit the separate `.format()` bug below before ever reaching the point where this fix would be exercised. |
| **`triage/engine.py` `str.format()` KeyError, hit on a live run this session** — `TRIAGE_PROMPT.format(issues_json=...)` crashed with `KeyError: '\n  "issue-id-1"'`. The prompt's literal JSON example block (`{"issue-id-1": {"severity": ...}}`) contains unescaped `{`/`}` characters, which Python's `str.format()` interprets as placeholders to fill in — not just the intended `{issues_json}` — so it tried (and failed) to look up `"issue-id-1"` as a keyword argument. | Escaped every literal brace in the prompt template by doubling it (`{{`/`}}`), leaving only the real `{issues_json}` placeholder single. Fixed this session. **General rule: any prompt string built with `.format()` that also contains literal JSON example braces needs every literal brace doubled, or use a different substitution method (e.g. simple string concatenation, or an f-string, or `.replace()`) instead.** `fix/suggest.py`'s `_prompt()` function already does this correctly via an f-string with doubled braces (`f'{{"suggested_solution": ...}}'`) — worth using as the reference pattern. |
| **`fix/suggest.py` used the legacy `web_search_preview` Responses API tool name** — still functional but OpenAI's current guidance is to use `"web_search"` for new integrations; `web_search_preview` is kept only for existing/legacy code and lacks newer controls | Changed `tools=[{"type": "web_search_preview"}]` to `tools=[{"type": "web_search"}]`. Fixed in code review before first live use. |
| **`fix/suggest.py` used direct dict indexing (`parsed["suggested_solution"]`) on LLM JSON responses** — a malformed/incomplete response would raise a raw `KeyError` instead of degrading gracefully into the function's own `except Exception` fallback | Changed to `parsed.get("suggested_solution")`/`parsed.get("confidence")` with an explicit `None` check that raises a clearer `ValueError` if either is missing — still caught by `suggest_fix()`'s outer try/except, just with a more diagnosable failure mode. Fixed in code review before first live use. |

---

## 8. Documentation already produced

Full IEEE-style docs exist as LaTeX + compiled PDF for this project:

1. **SRS** — functional/non-functional requirements, external interfaces,
   constraints (incl. the security opt-in/passive-only constraint as a
   hard Mandatory requirement), assumptions.
2. **SDD** — architecture diagrams, component responsibility table,
   database design (planned Postgres — NOT yet implemented, pipeline is
   currently stateless per run), API design (planned REST surface),
   sequence diagrams, error handling table, security design.
3. **Use Case Specification** — UC-01 through UC-05.
4. **UML diagram set** — use case, class, sequence, activity, component,
   deployment diagrams.
5. **Database Design Document** — ER diagram, table definitions,
   relationships, indexes, normalization (3NF), constraints.

These describe the TARGET architecture including a planned hosted
deployment (FastAPI + PostgreSQL + Streamlit/React frontend) — the
current actual implementation is a local CLI-driven script. Don't confuse
"documented" with "built" — check §4/§5 for actual code status.

---

## 9. How to run what exists today

```bash
# from site-doctor/ directory, with venv active
pip install -r requirements.txt --break-system-packages
playwright install chromium
npm install -g lighthouse   # or rely on the npx fallback in audit/lighthouse.py
pip install dnspython --break-system-packages   # for secuirty/verification.py
export OPENAI_API_KEY=your-key-here   # or $env:OPENAI_API_KEY on PowerShell

# run individual pieces standalone:
python -m crawler.website_crawler     # test BFS crawl alone
python -m audit.lighthouse            # test Lighthouse alone
python -m ux_review.vision_review     # test vision review alone (needs screenshots to exist)
python -m secuirty.verification       # test domain-ownership verification (start/check)

# run the full graph:
python -m agent.graph

# run the unit tests (needs only requirements-dev.txt -- no browser, no
# Node, no API key). See §16.
pip install -r requirements-dev.txt
pytest -q
```

Active-tooling prerequisites (Docker, Nuclei, sqlmap, Dalfox, Nmap, k6,
testssl.sh-via-WSL) — see §12 for the full Windows install command list.

`crawl_site()`'s own default parameters (`max_pages=10, max_depth=2`)
match `SiteDoctorState`'s own field defaults now, so a standalone
`python -m crawler.website_crawler` run and a full graph run behave
consistently on blank input.

---

## 10. Immediate next steps (roughly in priority order)

1. ~~**Confirm the `triage/engine.py` composite-key fix actually holds**~~ —
   **DONE, via unit test.** `tests/test_triage.py::
   test_aggregate_for_llm_keeps_same_audit_id_on_different_pages_distinct`
   feeds `aggregate_for_llm()` two pages that both report `heading-order`
   and asserts two distinct `url::audit_id` entries come back. No API key,
   no tokens, runs in CI on every push. A live multi-page run through
   `triage_node` is still worth doing for the LLM half, but the collision
   bug itself is now covered by a regression test.
2. **Run `fix_node` live for the first time** — implemented and code-reviewed
   this session (legacy tool name + unsafe indexing both fixed
   proactively), but not yet actually executed against real
   `triaged_issues` data.
3. **Test `secuirty/verification.py` end-to-end** — real domain the user
   controls DNS for, or a unit test mocking `dns.resolver.resolve()`.
4. **Re-enable the commented-out `require_verified()`/
   `_require_phase3_confirmation()` calls in `secuirty/active_engine.py`**
   — only `run_nmap`/`run_k6_load_test` currently gate live; every other
   function has it deliberately commented out for isolated testing. Must
   be restored before real use. See §12.
5. **Resolve the OpenAI `insufficient_quota` billing issue** so
   `ux_review_node` can be verified against a live vision response.
6. **Add sitemap.xml checking** as a first step in `crawl_site()` — the
   hydration-wait fix solves late-rendering SPAs, but not
   `onClick`/`history.pushState()`-only routing with zero real `<a href>`
   tags anywhere.
7. ~~**Clean up `audit/lighthouse.py`**: delete the shadowed first
   `run_lighthouse()` definition.~~ **DONE.**
8. **Clean up now-dead imports in `graph.py`** left over from
   `security_audit_node`'s logic moving to `secuirty/passive_checks.py`.
9. **Migrate `run_passive_tests`/`security_audit_node` to multi-page** —
   separate from, and should not be entangled with, the active-tooling
   gate work.
10. **Decide the `fix_confidence` auto-fix threshold** for whatever
    eventually reads `triaged_issues` to decide "generate a real `Fix`" vs.
    "surface as recommendation only" — security (`0.0`) and promoted UX
    (`0.1`) findings are designed to always fall below almost any
    reasonable cutoff.
11. **Build `approve_node` → `apply_node` → `reaudit_node`** — the
    still-entirely-unbuilt real mechanical loop that comes after a human
    reviews `fix_node`'s report.
12. Consider tightening `UXSuggestion.category` to a `UXCategory` enum.
    Still proposed, not applied.
13. ~~Consider giving `Category` a `UX` value instead of the current
    `Category.ACCESSIBILITY` placeholder used for promoted UX issues.~~
    **DONE** — `Category.UX` exists and `triage/engine.py` uses it.
14. Reuse `verification._domain_from_url()`'s normalization inside
    `active_engine.py` instead of its current bare `urlparse(url).hostname`.
15. **Audit every existing node for the "mutate state in place instead of
    returning it" bug class** — still a deliberate one-time check worth
    doing, not yet done.

---

## 11. User context (for tone/pacing in a new session)

- Knows LangChain/LangGraph fundamentals already; does NOT want code
  fully written for them by default — prefers shape/hints and writing it
  themselves, with review after. Shifts toward direct "just give me the
  code" requests during active debugging stretches — use judgment based
  on how the request is phrased. This session skewed direct/code-first
  throughout (schema pastes, full-file requests), consistent with a
  fast-iteration, implementation-heavy session.
- Has an OpenAI API key, explicitly on a limited/no budget — always
  default to `gpt-4o-mini`, minimize token usage, never send
  raw/unfiltered tool output to an LLM. Currently blocked on an
  `insufficient_quota` billing issue on that key/account — not a code
  problem.
- On Windows (PowerShell), Python 3.14, venv — several encoding/subprocess
  quirks are Windows-specific (see §7/§12).
- Wants this to be a genuine portfolio piece / meaningful contribution,
  not a "RAG wrapper" — the act-verify-retry loop is the point. `fix_node`
  being explicitly PROPOSE-only (not the loop itself) protects this
  framing rather than undermining it — worth keeping that framing sharp
  in any future discussion of this node.
- Explicitly stated goal: wants Site Doctor to become a genuinely
  production-level agent, including active security tooling eventually —
  but ONLY against sites they own or have explicit permission to test,
  never as a default option for arbitrary URLs. Agrees with the legal
  reasoning for why a checkbox isn't sufficient authorization (§6) — this
  is an agreed design direction, don't relitigate it from scratch.
- Pattern worth knowing: user often pastes their own already-written code
  for review rather than asking for it to be written from scratch (true of
  `fix/suggest.py`, `active_engine.py`, the updated `TRIAGE_PROMPT`) — the
  useful mode in that case is a careful bug-hunt/design review, not a
  rewrite from zero.

---

## 12. Security module architecture (`secuirty/` folder)

Security work was moved out of the single inline `security_audit_node`
function into a dedicated `secuirty/` package (folder name intentional
per the user, not a typo), to support the active-tooling research the
user brought in (ZAP, Nuclei, SQLMap, Dalfox, Nmap, k6 — see §6 for the
full risk discussion).

### Package layout

```
secuirty/
    verification.py    <- WRITTEN. Domain-ownership proof, required
                          before any active tool is allowed to run.
    passive_checks.py   <- WRITTEN. security_audit_node's logic relocated
                          here, exposed as run_passive_tests(url). Still
                          home-page-only.
    active_engine.py    <- WRITTEN (skeleton + real subprocess wrappers).
                          Wraps ZAP (baseline + active), Nuclei, testssl.sh,
                          SQLMap, Dalfox, Nmap, k6.
```

### Important nuance: ZAP has two very different modes

- **ZAP baseline scan** — passive, spiders and inspects real traffic
  without sending attack payloads. Closer in risk profile to
  `passive_checks.py` than to SQLMap/Nmap.
- **ZAP active scan** — genuinely attacks the target. Same risk tier as
  SQLMap, Dalfox, and Nuclei's CVE/exploit templates.

### Phased execution plan

- **Always available, no verification needed:** Lighthouse, Vision AI,
  `passive_checks.py`.
- **Phase 1 (verification required):** ZAP baseline, Nuclei restricted to
  `exposure,misconfig,default-login` tags, `testssl.sh` deep TLS analysis.
- **Phase 2 (verification + a SPECIFIC surface from Phase 1, never blind
  site-wide):** SQLMap against one named form/param URL, Dalfox against
  one named reflected-input URL.
- **Phase 3 (verification AND a SEPARATE explicit confirmation per run):**
  ZAP active scan, Nmap, k6 load/stress testing.

### `secuirty/verification.py`

- `start_verification(url) -> dict` — generates a random hex token, saves
  it as a pending challenge (`.site-doctor-cache/verified_domains.json`),
  returns instructions for the exact DNS TXT record to create. Pending
  tokens expire after 1 hour if unconfirmed.
- `check_verification(url) -> bool` — real DNS TXT lookup via `dnspython`.
  Returns `False` (not an error) if not found yet. On match, writes a
  permanent verified record.
- `is_domain_verified(url) -> bool` — cheap local-store-only check.
- `require_verified(url) -> None` — **the hard gate.** Raises
  `PermissionError` rather than returning a bool.
- Verified permanently per domain, not per session/run.
- New dependency: `pip install dnspython --break-system-packages`.

**Testing constraint:** can only be meaningfully tested against a domain
the user actually controls DNS for. Not yet tested end-to-end.

### `secuirty/active_engine.py` — verification-gate status (important)

The file's docstring claims every function gates on `require_verified()`
— **not currently true.** Confirmed status:

| Function | `require_verified()` called? |
|---|---|
| `run_zap_baseline` | Commented out |
| `run_nuclei_info_disclosure` | Commented out |
| `run_tls_deep_analysis` | Commented out |
| `run_sqlmap` | Commented out |
| `run_dalfox` | Commented out |
| `run_zap_active_scan` | Commented out (both the verify AND phase-3-confirm calls) |
| `run_nmap` | **Live** |
| `run_k6_load_test` | **Live** |

Commented out deliberately by the user to test subprocess-wrapping logic
in isolation — must be restored before real use.

Two smaller findings, not yet fixed:
- `active_engine.py` extracts domains via bare `urlparse(url).hostname`,
  while `verification.py` lowercases and handles scheme-less input —
  potential mismatch on edge-case URLs.
- `testssl.sh` is a bash script, won't run natively on Windows — needs
  WSL. Every other tool has a native Windows path (see §9).

---

## 13. Triage module (`triage/engine.py`)

### Purpose

Bridges "a wall of raw, developer-worded Lighthouse/security/UX output
across three separate node outputs" into "one ranked, human-readable,
fix-loop-ready list" (`state.triaged_issues`). Only `Issue`-typed findings
enter the fix pipeline — `Fix` only ever attaches to an `Issue.id`, per
the schema's original architectural rule, upheld not broken by this
design.

### The three-way merge

1. **Lighthouse (`audit_before`) -> `triage_lighthouse_issues()`** — the
   only path with a real LLM call. Flattens every page's issues, ONE
   batched `gpt-4o-mini` call (`response_format={"type":"json_object"}`)
   returns `severity`, `plain_language_summary`, `fix_confidence` per
   issue.
2. **Security findings -> `triage_security_findings()`** — already typed
   as `Issue`, no LLM call needed, stamps `source`/`source_url`, forces
   `fix_confidence=0.0` since headers/TLS are server-level config, not
   HTML-patchable.
3. **UX suggestions -> `promote_high_severity_ux_suggestions()`** — only
   `Severity.HIGH` suggestions (user's explicit choice) get promoted into
   synthetic pseudo-`Issue`s with `fix_confidence=0.1`. Everything below
   stays a plain `UXSuggestion`, report-only, never enters the fix
   pipeline. Promoted issues are stamped `Category.UX` (this used to be an
   inaccurate `Category.ACCESSIBILITY` placeholder — now resolved).

### Two real bugs found this module, one confirmed fixed, one status still open

1. **Composite-key collision** (found in code review) — bare `issue.id`
   recurs across pages sharing the same Lighthouse audit id, silently
   dropping/merging distinct per-page issues. Fixed by keying on
   `f"{page_url}::{issue.id}"` instead, leaving the real `Issue.id`
   untouched. **Still not confirmed working against a live run** — see
   next bug.
2. **`str.format()` KeyError** (found on an actual live run this
   session) — `TRIAGE_PROMPT`'s literal JSON example block has unescaped
   `{`/`}` that `.format()` tried to interpret as placeholders, crashing
   before the LLM call was even made. Fixed by doubling every literal
   brace. This crash happened BEFORE the composite-key fix's logic would
   even run, so bug #1's fix remains unverified live — both need
   confirming together in the next real run. See §10.

---

## 14. Detailed security + triage next-step priorities

(Superseded in ordering by the consolidated §10 list above, kept here for
the detailed per-item context.)

1. Test `secuirty/verification.py` end-to-end — real domain or mocked-DNS
   unit test.
2. Re-enable commented-out `require_verified()`/`_require_phase3_confirmation()`
   calls across `active_engine.py`.
3. Run a real multi-page test of `triage_node` now that BOTH known bugs
   (composite-key collision, `.format()` KeyError) are fixed in code —
   confirm they actually hold together live.
4. Reuse `verification`'s domain-normalization logic inside
   `active_engine.py` instead of the current duplicated
   `urlparse(...).hostname`.
5. Decide the `fix_confidence` threshold for whatever eventually consumes
   `triaged_issues` post-`fix_node` to decide real-`Fix` generation.
6. Migrate `run_passive_tests`/`security_audit_node` to loop over
   `crawl_result.pages`.

---

## 15. Fix module (`fix/suggest.py`) — PROPOSE-only fix suggestions

### Purpose and scope, confirmed explicitly with the user this session

`fix_node` is **not** the mechanical fix/apply/verify/retry loop. It's a
suggestion-generation step that sits between `triage_node` and a human
decision point (`approve_node`, still a stub):

```
triage_node -> fix_node (THIS MODULE) -> report shown to human
                                           -> human decides whether to
                                              let the agent continue into
                                              an actual apply loop (separate,
                                              later, still-unbuilt work)
```

No HTML is read or edited here, and no `Fix` (before/after) object is
created — only `Issue.suggested_solution` (descriptive text) and
`Issue.solution_sources` are populated. This runs UNIFORMLY across every
triaged issue regardless of `source` (SEO/security/UX) — no special-casing
by source, unlike `triage_node` which does treat the three sources
differently. A real mechanically-applicable patch generator
(`fix/mechanical.py`-style, not yet built) is a separate, later concern
for whatever node runs after a human explicitly approves proceeding.

### How confidence differs from triage's confidence

Triage's `fix_confidence` was a coarse, source-based placeholder signal
(LLM-estimated for Lighthouse issues, hardcoded 0.0/0.1 for
security/promoted-UX). `fix_node` REPLACES that with a real
per-suggestion judgment: "how confident is the model that following THIS
specific suggested_solution would actually resolve the issue" — generated
together with the suggestion text itself in the same LLM call, not
inherited from triage's coarser estimate.

### Two-tier suggestion strategy

- **HIGH/MEDIUM severity issues** (`_SEARCH_ELIGIBLE`) get a
  web-search-augmented suggestion via the OpenAI Responses API
  (`client.responses.create(..., tools=[{"type": "web_search"}])`) — lets
  the model ground its suggestion in current best-practice sources rather
  than relying purely on training data, and captures cited source URLs
  into `Issue.solution_sources`.
- **LOW severity issues** get a plain Chat Completions call — cheaper,
  since web search is a separately-metered capability (Responses API) not
  bundled free with plain chat calls, and low-severity issues don't
  justify the extra cost/latency.
- `suggest_fix(issue)` mutates and returns the SAME `Issue` object (fits
  the same in-place-list-mutation pattern `fix_node` uses on
  `triaged_issues` as a whole) and NEVER fails the pipeline — any
  exception falls back to reusing `plain_language_summary`/`description`
  as the suggestion text, so one bad LLM response can't crash the whole
  batch.

### Two bugs found in code review, fixed before first live use

1. **Legacy Responses API tool name.** Code used
   `{"type": "web_search_preview"}`. Confirmed via live web search that
   OpenAI's current guidance is `{"type": "web_search"}` for new
   integrations — `web_search_preview` still works but is kept only for
   legacy code and lacks newer controls (filters, `external_web_access`,
   `return_token_budget`). Switched to `"web_search"`.
2. **Unsafe direct dict indexing on LLM JSON output**
   (`parsed["suggested_solution"]`, `parsed["confidence"]`) in both the
   search and non-search suggestion paths — a malformed/incomplete
   response would raise a raw `KeyError` instead of hitting the intended
   `except Exception` fallback in `suggest_fix()`. Changed to
   `.get(...)`-based access with an explicit `None`-check that raises a
   clearer `ValueError` (still caught upstream) instead.

### Known open question, not yet resolved

The Responses API doesn't take `response_format` the way Chat Completions
does — Structured Outputs there is `text.format` + a `json_schema`, and
it's unconfirmed whether that's usable together with a hosted tool like
`web_search` in the same call. The search-eligible path currently relies
purely on the prompt's "Respond with ONLY valid JSON" instruction (no
enforced schema), unlike the non-search path which does have
`response_format={"type": "json_object"}`. The `.get()`-based parsing
fix above makes a malformed response degrade safely rather than crash,
but doesn't close this gap — worth researching further if malformed
search-path responses turn out to be common in practice once this is
actually run live.

### Required schema additions (confirmed applied to a full `schemas.py` paste this session)

```python
suggested_solution: str | None = None
solution_sources: list[str] = Field(default_factory=list)
```

Both added to `Issue`. Without these, `suggest_fix()` would crash the
first time it tried `issue.suggested_solution = solution`, since Pydantic
models reject assignment to undeclared fields.

---

## 16. Tests and CI (`tests/`, `.github/workflows/ci.yml`)

Added during the DevOps pass. 61 tests, all covering **pure functions
only** — no network, browser, Node, LLM call or API key. `pytest -q` from
`site-doctor/` runs in about two seconds.

### What is covered

| Module | What is tested |
|---|---|
| `crawler/utils.py` | `normalize_url`, `is_internal_link`, `slugify`, `extract_links` |
| `audit/lighthouse.py` | `parse_report()` against a hand-written fake report dict |
| `models/schemas.py` | required fields, enum rejection, defaults, mutable-default isolation |
| `crawler/storage.py` | cache layout, `save_manifest`/`load_manifest` round trip |
| `triage/engine.py` | prompt formatting, `aggregate_for_llm`, security + UX triage |

### What is NOT covered — do not assume green tests mean safe

`agent/graph.py` (every node), `crawler/website_crawler.py`'s BFS,
`secuirty/*`, `fix/suggest.py`, `ux_review/*`, `report/*`, and
`run_lighthouse()` itself. All of those need a browser, a subprocess, an
API key, or a human at a keyboard.

### Regression tests worth knowing about

Several tests exist specifically to stop a previously-fixed bug from §7
coming back. Each was verified to actually fail when the bug is
reintroduced, so none of them are vacuous:

- the spoofable `startswith()` hostname check in `is_internal_link`
- `TRIAGE_PROMPT.format()`'s `KeyError` from unescaped literal JSON braces
- `default_factory` being given a *called* `datetime.utcnow()`
- `save_manifest()` on a zero-page crawl
- `aggregate_for_llm`'s per-page issue-ID collision (see §10 item 1)

**If you change behaviour deliberately, a red test is the expected
outcome — update the test, don't work around it.** Two tests document
current behaviour rather than desired behaviour and say so in their
docstrings: `test_normalize_url_requires_a_scheme` (it raises `IndexError`
on scheme-less input) and
`test_is_internal_link_treats_a_different_port_as_external`.

### CI

`.github/workflows/ci.yml` runs the suite on Ubuntu + Python 3.14, on
pushes to `devops/**` and on PRs into `main`. It installs
`requirements-dev.txt` only (5 packages), not the full runtime set.

`OPENAI_API_KEY` is set to a **literal dummy string, not a GitHub
Secret** — no real key ever enters CI. It exists only because
`fix/suggest.py:36` constructs an `OpenAI` client at module import time,
so importing `agent.graph` at all requires *some* value to be present.