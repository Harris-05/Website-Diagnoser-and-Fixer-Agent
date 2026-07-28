"""Vision-based UX review for screenshots.

The model returns structured suggestions that are intentionally separate from
the rule-based Lighthouse issues.
"""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

from models.schemas import UXSuggestion


load_dotenv()


VISION_REVIEW_PROMPT = """
You are an expert Senior UX Designer, CRO (Conversion Rate Optimization)
Consultant, and UI Accessibility reviewer.

You are reviewing screenshots of the SAME webpage captured from top to bottom
while scrolling.

IMPORTANT:
- These screenshots are sequential sections of ONE continuous page.
- Treat them as a single experience, not separate pages.
- If an element (navigation, CTA, trust badge, footer, etc.) appears in one
  screenshot, assume it exists on the page and do NOT incorrectly flag later
  screenshots for "missing" that element.
- Only report issues that are clearly visible.
- Do NOT guess or invent problems.
- If evidence is insufficient, do not mention it.

Evaluate the page against established UX standards including:

1. Visual Hierarchy
- Clear primary heading
- Proper heading hierarchy
- Logical reading flow
- Clear focal points
- Appropriate emphasis

2. Call-to-Action Effectiveness
- Primary CTA is immediately obvious
- CTA stands out visually
- No competing primary CTAs
- CTA wording is clear and action-oriented

3. Navigation
- Navigation appears organized
- Important links are easy to identify
- Navigation is not cluttered
- Logo/branding is easy to locate

4. Visual Clutter
- No excessive text
- No excessive buttons
- No unnecessary visual noise
- Appropriate use of whitespace

5. Typography & Readability
- Readable font sizes
- Good line spacing
- Clear text hierarchy
- Good paragraph length
- Easy to scan

6. Color & Contrast
- Strong visual contrast
- CTA contrast is sufficient
- Color palette appears consistent
- Important elements are visually distinguishable

7. Consistency
- Consistent buttons
- Consistent spacing
- Consistent typography
- Consistent iconography
- Consistent component styling

8. Trust & Credibility
- Trust signals visible where appropriate
- Testimonials/reviews if applicable
- Contact information easy to find
- Professional appearance

9. Accessibility (Visual Only)
Evaluate only what is visually observable.
Examples:
- Tiny text
- Low contrast
- Tiny clickable targets
- Poor spacing
- Difficult readability

Do NOT speculate about:
- missing alt text
- keyboard accessibility
- ARIA
- HTML semantics
- Lighthouse findings
- page speed

10. Information Architecture
- Sections are logically organized
- Information is easy to follow
- Users can quickly understand what the business offers

11. Conversion Optimization
- Value proposition is immediately clear
- Primary action is obvious
- Content supports conversion
- No major distractions

12. Mobile Friendliness (only if screenshots are mobile)
- Touch-friendly controls
- Comfortable spacing
- Readable typography
- No obvious layout problems

13. Overall Professionalism
- Modern appearance
- Cohesive branding
- High-quality imagery
- Polished interface

For every issue:

- Report ONLY actionable UX issues.
- Do NOT repeat the same issue in multiple categories.
- Ignore minor personal design preferences.
- Base every observation on visible evidence.

Severity Guidelines

High:
- Likely to confuse users
- Blocks conversion
- Major usability issue
- Strong accessibility concern

Medium:
- Noticeably harms usability
- Could reduce conversions
- Causes unnecessary friction

Low:
- Minor polish issue
- Cosmetic inconsistency
- Small UX improvement

Return ONLY valid JSON.

{
  "suggestions": [
    {
      "id": "ux-1",
      "category": "visual_hierarchy",
      "severity": "high",
      "observation": "Describe exactly what is visible.",
      "recommendation": "Provide a specific, actionable improvement."
    }
  ]
}

Valid categories:

- visual_hierarchy
- cta
- navigation
- clutter
- readability
- typography
- contrast
- consistency
- trust
- accessibility
- information_architecture
- conversion
- mobile
- professionalism

If no significant UX issues are visible, return exactly:

{
  "suggestions": []
}
"""


def _strip_code_fences(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()


def _parse_suggestions(raw_text: str) -> list[UXSuggestion]:
    payload = json.loads(_strip_code_fences(raw_text))
    if isinstance(payload, dict):
        items = payload.get("suggestions", [])
    else:
        items = payload
    return [UXSuggestion.model_validate(item) for item in items]


def _encode_image(screenshot_path: str) -> str:
    image_bytes = Path(screenshot_path).read_bytes()
    encoded_image = base64.b64encode(image_bytes).decode("ascii")
    print(f"Encoded {screenshot_path} to base64, length {len(encoded_image)}")
    return f"data:image/png;base64,{encoded_image}"


def review_screenshots(url: str, screenshot_paths: list[str]) -> list[UXSuggestion]:
    content: list[dict[str, object]] = [{"type": "text", "text": VISION_REVIEW_PROMPT}]
    for screenshot_path in screenshot_paths:
        content.append(
            {"type": "image_url", "image_url": {"url": _encode_image(screenshot_path)}}
        )

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": content}],
        temperature=0.2,
    )

    raw_text = response.choices[0].message.content or '{"suggestions": []}'
    suggestions = _parse_suggestions(raw_text)
    for s in suggestions:
        s.page_url = url
    return suggestions

# ux_review/vision_review.py
from crawler.storage import ux_report_path

def save_ux_report(crawl_id: str, suggestions: list[UXSuggestion]) -> str:
    grouped: dict[str, list[UXSuggestion]] = {}
    for s in suggestions:
        grouped.setdefault(s.page_url or "unknown page", []).append(s)

    lines = ["# UX Review Report", ""]
    for url, items in grouped.items():
        lines.append(f"## {url}")
        if not items:
            lines.append("No issues found.\n")
            continue
        for item in items:
            lines.append(f"- **[{item.severity.value}] {item.category}** — {item.observation}")
            lines.append(f"  - *Recommendation:* {item.recommendation}")
        lines.append("")

    path = ux_report_path(crawl_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)