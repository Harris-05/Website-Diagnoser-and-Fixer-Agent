# Findings from the DevOps pass

Written by Abdul Raffay while setting up tests and CI. **Nothing in this
list has been changed by me** — every item is in code that belongs to the
feature work, so it's yours to decide on. I've only added tests, CI config,
`.gitignore` entries, and three missing lines in `requirements.txt`.

Ordered by how much it matters.

---

## 1. `security_audit_node` calls the active security tooling

**`agent/graph.py:150`**

```python
findings = run_passive_tests(state.url)
findings.append(run_active_security_tests(state.url))
```

The node's own docstring immediately above says:

> Passive security posture checks ONLY … No active scanning, no exploitation
> attempts, no load/stress testing under any configuration (SRS FR-15, FR-16).

But `run_active_security_tests()` (`secuirty/active_engine.py:296`) runs ZAP
baseline, Nuclei, deep TLS analysis, **ZAP active scan, Nmap, and a k6 load
test**. Three separate problems:

1. **It crashes the run today.** `run_active_security_tests` starts with
   `require_verified(url)`, which raises `PermissionError` for any domain
   without a DNS TXT verification record. There's no `try/except` around the
   call in `graph.py`, so **selecting Security currently kills the whole
   pipeline** rather than degrading.
2. **Type mismatch even if verification passed.** It returns a `dict`, which
   gets `.append()`-ed to a `list[Issue]` → Pydantic validation error on the
   state update.
3. **A blocking `input()` inside it** (`secuirty/active_engine.py:303`), which
   makes it impossible to run unattended.

Also worth knowing: most `require_verified()` calls inside `active_engine.py`
are still commented out from isolated testing (per your own `CLAUDE.md` §12),
so if verification did pass for a domain, the individual tools would run
ungated.

This is an architectural call, not a typo — your `CLAUDE.md` §6 describes
active tooling as a deliberately separate mode, so this line looks like a
leftover from testing rather than an intended wiring. **I have deliberately
kept this unreachable from CI.**

## 2. `run_lighthouse()` is defined twice

**`audit/lighthouse.py:29` and `:68`**

The first definition (lines 29–66) has no `categories` parameter and no
`return` statement. Python silently keeps only the second, so the first is
dead code that a reader will waste time on. Already noted in your
`CLAUDE.md`; flagging it because it's a 30-second deletion.

## 3. `normalize_url()` raises `IndexError` on a scheme-less URL

**`crawler/utils.py:25`**

```python
url = url.split("//")[1]
```

`normalize_url("site.com/about")` raises `IndexError: list index out of range`
rather than handling it. Fine as long as every caller passes an absolute URL —
and today they do — but it's a sharp edge for anything that later accepts user
input (a form field, a CLI argument, an API request body).

`tests/test_utils.py::test_normalize_url_requires_a_scheme` documents the
current behaviour with `pytest.raises(IndexError)`. If you change it, that
test is *supposed* to fail — update it then.

## 4. `extract_links()` returns scheme-less strings, but its docstring says "absolute"

**`crawler/utils.py:84`**

The docstring promises "a de-duplicated list of normalized, absolute, internal
URLs", but the return value is `normalize_url(...)` output, which strips the
scheme (`site.com/about`, not `https://site.com/about`). The behaviour is
right for de-duplication keys — the docstring is just misleading. Related: this
is why `WebsiteCrawler._with_scheme()` has to exist.

## 5. Unused `import site`

**`crawler/utils.py:4`** — imports the stdlib `site` module, unused, and shadows
the name locally. Harmless, but confusing in a project literally about sites.

## 6. `requirements.txt` was missing three packages it imports

**Fixed in this branch** (the only change I made to a file of yours), because a
clean clone couldn't start:

| Package | Imported by |
|---|---|
| `beautifulsoup4` | `crawler/utils.py:7` |
| `reportlab` | `report/generate_pdf.py`, which `agent/graph.py:36` imports at module load — so `python -m agent.graph` failed on import |
| `openai` | used directly in `triage/`, `fix/`, `ux_review/`; was only arriving transitively via `langchain-openai` |

**Still outstanding, deliberately left alone:** no version is pinned anywhere,
and these look unused by any import in the repo — `jupyterlab`, `ipywidgets`,
`sounddevice`, `scipy`, `langchain-google-vertexai`, `langchain-google-genai`,
`anthropic`, `langchain-anthropic` (listed twice), `langchain-tavily`,
`tavily-python`, `tavily`, `pypdf`, `mcp`. That's a large install and a large
future Docker image. I'd like to trim and pin these in a separate PR now that
CI exists to catch a wrong removal — say the word and I'll do it.

## 7. `site-doctor/CLAUDE.md` has drifted from the code

Minor, but it's the handoff doc, so worth keeping accurate:

- says `fix/engine.py` — the file is `fix/suggest.py`
- lists a `tests/` directory as existing — it didn't until this branch
- says `Category` has no `UX` value and that promoted UX issues use
  `Category.ACCESSIBILITY` as a placeholder — `schemas.py:15` now has
  `UX = "ux"` and `triage/engine.py:155` uses it

**Good news on that file:** the composite-key fix in `aggregate_for_llm()`,
which your notes list as *"fixed in code review, still not confirmed working
against a live run"* — it's now confirmed, by
`tests/test_triage.py::test_aggregate_for_llm_keeps_same_audit_id_on_different_pages_distinct`.
Two pages both reporting `heading-order` produce two distinct entries. No API
key, no tokens, runs in CI on every push.

## 8. Things I'll need from you for the containerisation step

Not bugs — just flagging early so nothing surprises either of us:

- **16 blocking `input()` calls**, including inside `check_selection_node`,
  which is the graph's entry node. That means even `app.invoke(...)` blocks on
  stdin, so nothing can run in Docker, CI, or on a schedule yet. I plan to add
  a **separate** non-interactive entry point that reuses your nodes and never
  edits `graph.py`. Shout if you'd rather do it differently.
- **Cache paths are relative to the working directory**
  (`crawler/storage.py:19`, `audit/lighthouse.py:74`), so behaviour depends on
  where the process was launched from. Matters for container volumes.
- **`fix/suggest.py:36` builds the `OpenAI` client at module import time**, so
  importing `agent.graph` at all requires a key to be present. CI works around
  it with a dummy value.
