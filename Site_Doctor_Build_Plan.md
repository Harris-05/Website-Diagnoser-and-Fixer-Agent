# Site Doctor — Build Plan
### An agent that crawls a site, audits SEO/accessibility/performance, and fixes issues on approval

---

## 1. Scope for v1

**In scope:**
- Single-site crawl (start with single-page, extend to a few pages deep)
- Audit via Lighthouse (SEO + Accessibility + Performance categories)
- Plain-language issue report, ranked by severity
- Auto-generated fixes for a defined set of safe, high-confidence issue types
- Diff-based human approval step before any fix is applied
- Re-audit after applying, to prove the fix actually worked
- Operates on a **local copy** of the site (cloned/rendered HTML) — not live edits to someone else's production site

**Out of scope for v1:**
- CMS/live-site write-back (WordPress plugin, etc.) — that's a real v2 if this works
- Multi-page-deep full-site crawls (start with 1 page, extend later)
- JS-heavy SPA rendering edge cases — target standard server-rendered/static sites first

## 2. Architecture

```
        ┌──────────────┐
        │ Crawl         │  Playwright: fetch page, render DOM, save local copy
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │ Audit         │  Lighthouse CI: SEO + A11y + Performance scores + issue list
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │ Triage        │  agent ranks issues: severity × fix-confidence,
        │               │  writes plain-language explanations
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │ Report        │  shown to user: ranked issues, in plain language
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │ Fix           │  for approved issues: generate concrete patch (HTML/meta/etc.)
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │ Human Approve │  show diff, wait for yes/no per fix (or batch approve)
        └──────┬───────┘
          yes  │  no → discard, log as skipped
               ▼
        ┌──────────────┐
        │ Apply         │  write patch to local copy
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │ Re-audit      │  re-run Lighthouse, confirm the specific issue cleared
        └──────┬───────┘
         cleared│ not cleared → loop back to Fix (max retries)
               ▼
        ┌──────────────┐
        │ Final Report  │  before/after scores, what was fixed, what wasn't
        └──────────────┘
```

## 3. Fix types for v1, easiest → hardest to verify

| Issue | Fix | Verification |
|---|---|---|
| Missing/duplicate `<title>` or meta description | Generate unique, on-topic title/description | Lighthouse SEO audit item clears |
| Missing image `alt` text | Generate descriptive alt text from image context | Lighthouse A11y audit item clears |
| Missing heading hierarchy (no H1, skipped levels) | Restructure heading tags | Lighthouse A11y/SEO item clears |
| Missing `canonical` tag | Add canonical link | Lighthouse SEO item clears |
| Missing structured data (schema.org) | Generate JSON-LD block for page type | Structured data validator passes |
| Unoptimized images (large file size) | Convert to WebP / compress | Lighthouse Performance score delta |
| Low color contrast | Adjust CSS colors to meet WCAG AA | Lighthouse A11y item clears |

Start with the top 2-3 rows only — get the full loop working end-to-end before adding more fix types.

## 4. Tech stack

| Layer | Tool |
|---|---|
| Orchestration | LangGraph |
| LLM | ChatGPT (OpenAI API) — diagnosis, fix generation, plain-language explanations |
| Crawling/rendering | Playwright (Python) |
| Audit engine | Lighthouse CI (Node, called via subprocess) — gives you Google's own standardized 0-100 scores |
| Structured state | Pydantic models for Issue, Fix, AuditResult |
| Backend | FastAPI |
| Frontend (v1) | Simple Streamlit — upload/enter URL, see report, approve fixes with checkboxes, see diffs |
| Image optimization | `Pillow` / `cwebp` |

## 5. Week-by-week plan (~8 weeks)

**Week 1 — Crawl + Audit only**
- Playwright fetches a page, saves local HTML copy
- Run Lighthouse CI against the local copy, parse the JSON report
- Confirm you reliably get SEO/A11y/Performance scores + itemized issues on 3-5 real test sites (pick sites with known, visible problems)

**Week 2 — Triage + Report**
- Agent node that takes the raw Lighthouse issue list and produces: severity ranking + plain-language explanation per issue
- Basic Streamlit report view — this alone is already a usable, demoable tool

**Week 3-4 — Fix generation (title/meta, alt text, headings)**
- Fix node: given an issue, generate the concrete patch (new meta tag, alt text, etc.)
- Diff view — show exact before/after HTML for each proposed fix

**Week 5 — Human approval + Apply**
- Approval step (per-fix checkboxes or approve-all)
- Apply node writes approved patches to the local copy

**Week 6 — Re-audit loop**
- Re-run Lighthouse on the patched copy
- Confirm the specific issue actually cleared (not just "score went up")
- Add retry loop for fixes that didn't take, capped at N attempts

**Week 7 — Expand fix types**
- Add structured data generation and image optimization (these have the most visually obvious before/after)

**Week 8 — Polish + benchmark**
- Run against a set of 10-15 real public sites with known issues
- Report a clean before/after number: "average Lighthouse score improvement: +X points across N sites, Y issues auto-fixed and verified"
- This benchmark number is your strongest portfolio artifact — a plain "I built an agent" claim is forgettable, a real measured score jump on real sites is not

## 6. First concrete step

Get Lighthouse CI running standalone against one real site *before* writing any agent code — confirm you can parse its JSON output cleanly and understand what a real issue list looks like. This determines your entire Issue schema downstream.

```bash
npm install -g @lhci/cli lighthouse
lighthouse https://example.com --output=json --output-path=./report.json
```

---

I've also scaffolded a starter repo below — take a look and let me know if you want to start on Week 1 together.
