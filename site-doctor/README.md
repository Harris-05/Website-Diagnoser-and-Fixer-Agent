# Site Doctor

An agent that crawls a website, audits it for SEO/accessibility/performance
issues via Lighthouse, explains findings in plain language, and — with your
approval — generates and applies verified fixes.

See `Site_Doctor_Build_Plan.md` (in the parent chat) for the full week-by-week
plan and architecture rationale.

## Setup

```bash
# Python deps
pip install -r requirements.txt --break-system-packages
playwright install chromium

# Lighthouse CLI (Node)
npm install -g lighthouse

# Anthropic API key
export ANTHROPIC_API_KEY=your-key-here
```

## Week 1 goal

Get this working end to end:

```bash
python -m audit.lighthouse https://example.com
```

Confirm you get a clean parsed report with real scores and issues before
touching any agent/LangGraph code — this is the foundation everything else
sits on.

Then wire it into the graph:

```bash
python -m agent.graph https://example.com
```

## Project structure

```
agent/       LangGraph state machine (graph.py)
audit/       Lighthouse integration + report parsing
crawler/     Playwright page fetching
models/      Pydantic schemas shared across the graph state
tests/       (empty — add tests as you build each node)
```

## Status

- [x] Repo scaffold
- [ ] Week 1: crawl_node + audit_node working end to end
- [ ] Week 2: triage_node (severity ranking + plain-language explanations)
- [ ] Week 3-4: fix_node (title/meta, alt text, headings)
- [ ] Week 5: approve_node + apply_node
- [ ] Week 6: reaudit_node + retry loop
- [ ] Week 7: structured data + image optimization fixes
- [ ] Week 8: benchmark against 10-15 real sites
