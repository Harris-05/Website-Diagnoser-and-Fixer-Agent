"""fix/engine.py

Generates a plain-language suggested fix + confidence score for EVERY
triaged issue -- SEO, UX, and security alike, no special-casing by
source. This is the PROPOSE step only:

    triage_node -> fix_node (this file) -> report shown to human
                                             -> human decides whether to
                                                let the agent continue
                                                into an actual apply loop

No HTML is read or edited here, and no Fix (before/after) object is
created. Real, mechanically-applicable patches (fix/mechanical.py) are a
LATER concern for whatever apply/approve/reaudit node runs after the
human reviews this report and explicitly says to proceed -- that's a
different, still-unbuilt step, not this one.

Confidence here means "how confident is the model that THIS suggested
fix would actually resolve the issue" -- generated together with the
suggestion itself, not inherited from triage's coarser per-source
placeholder (triage's fix_confidence was a rough source-based signal;
this replaces it with a real per-suggestion judgment).
"""

import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

from models.schemas import Issue, Severity

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# web search only for higher-severity issues -- it's a separately-metered
# capability (Responses API), not free alongside the plain chat calls
_SEARCH_ELIGIBLE = {Severity.HIGH, Severity.MEDIUM}


def _strip_code_fences(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text.strip()


def _prompt(issue: Issue) -> str:
    return (
        f"A website has this issue:\n"
        f"Title: {issue.title}\n"
        f"Description: {issue.description}\n"
        f"Category: {issue.category.value}\n\n"
        f"Respond with ONLY valid JSON:\n"
        f'{{"suggested_solution": "2-3 sentences, concrete and actionable, '
        f'not generic advice", "confidence": 0.0-1.0}}\n\n'
        f'"confidence" means: how confident are you that following this '
        f"exact suggestion would resolve the issue -- 0.9+ for simple, "
        f"unambiguous fixes (missing tag, missing header), 0.2-0.4 for "
        f"anything requiring design/visual judgment a human should really "
        f"make."
    )


def _suggest_with_search(issue: Issue) -> tuple[str, float, list[str]]:
    """HIGH/MEDIUM severity issues only. Uses the current "web_search"
    tool type (not the legacy "web_search_preview" -- OpenAI's own
    guidance: use web_search for new integrations, web_search_preview is
    kept around only for existing/legacy code).

    NOTE: the Responses API does not take response_format the way Chat
    Completions does -- structured JSON there is Structured Outputs via
    text.format + a json_schema, and it's not confirmed that's usable
    together with a hosted tool like web_search in the same call. So this
    path still relies on the prompt instruction alone for JSON shape,
    same as _suggest_without_search did before response_format was added
    there. To compensate, parsing below uses .get(...) with safe
    defaults instead of direct dict indexing, so a slightly malformed
    response degrades into suggest_fix()'s except-block fallback instead
    of raising a raw KeyError mid-parse.
    """
    response = client.responses.create(
        model="gpt-4o-mini",
        tools=[{"type": "web_search"}],
        input=_prompt(issue),
    )
    parsed = json.loads(_strip_code_fences(response.output_text))

    solution = parsed.get("suggested_solution")
    confidence = parsed.get("confidence")
    if solution is None or confidence is None:
        raise ValueError(f"Malformed web-search JSON response: {parsed!r}")

    sources = []
    for item in getattr(response, "output", []):
        for content in getattr(item, "content", []):
            for annotation in getattr(content, "annotations", []):
                url = getattr(annotation, "url", None)
                if url:
                    sources.append(url)

    return solution, float(confidence), sources


def _suggest_without_search(issue: Issue) -> tuple[str, float]:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": _prompt(issue)}],
        max_tokens=150,
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    parsed = json.loads(response.choices[0].message.content)

    solution = parsed.get("suggested_solution")
    confidence = parsed.get("confidence")
    if solution is None or confidence is None:
        raise ValueError(f"Malformed JSON response: {parsed!r}")

    return solution, float(confidence)


def suggest_fix(issue: Issue) -> Issue:
    """Mutates and returns the issue with suggested_solution,
    solution_sources, and a refined fix_confidence -- for every issue,
    no source-based branching. Never fails the pipeline: falls back to
    the existing plain_language_summary on any error."""
    try:
        if issue.severity in _SEARCH_ELIGIBLE:
            solution, confidence, sources = _suggest_with_search(issue)
            issue.suggested_solution = solution
            issue.fix_confidence = confidence
            issue.solution_sources = sources
        else:
            solution, confidence = _suggest_without_search(issue)
            issue.suggested_solution = solution
            issue.fix_confidence = confidence
    except Exception as exc:
        print(f"Fix suggestion failed for issue {issue.id}: {exc}")
        issue.suggested_solution = issue.plain_language_summary or issue.description

    return issue