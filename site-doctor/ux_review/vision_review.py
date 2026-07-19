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


VISION_REVIEW_PROMPT = """Review these screenshots of the same website in scroll order.

They are sequential slices of one page from top to bottom, so treat them as one
continuous experience rather than judging each image in isolation. For example,
if a CTA is visible in an earlier screenshot, do not flag a later screenshot as
lacking a CTA just because it is below the fold.

Focus on what a first-time visitor can see before scrolling:
- visual clutter
- too many competing CTAs
- whether the primary action is obvious
- trust signal placement
- unclear hierarchy or attention conflicts

Return JSON only in this shape:
{
  "suggestions": [
    {
      "id": "ux-1",
      "category": "clutter",
      "severity": "high",
      "observation": "...",
      "recommendation": "..."
    }
  ]
}

If the page looks fine, return {"suggestions": []}.
Use only the severity values high, medium, or low.
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
    return f"data:image/png;base64,{encoded_image}"


def review_screenshots(screenshot_paths: list[str]) -> list[UXSuggestion]:
    content: list[dict[str, object]] = [{"type": "text", "text": VISION_REVIEW_PROMPT}]
    for screenshot_path in screenshot_paths:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": _encode_image(screenshot_path)},
            }
        )

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": content,
            }
        ],
        temperature=0.2,
    )

    content = response.choices[0].message.content or "{\"suggestions\": []}"
    return _parse_suggestions(content)