"""Core data models shared across the LangGraph state."""

from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Category(str, Enum):
    SEO = "seo"
    ACCESSIBILITY = "accessibility"
    PERFORMANCE = "performance"


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Issue(BaseModel):
    """A single problem found by the audit engine."""
    id: str = Field(..., description="Stable ID, e.g. lighthouse audit key")
    category: Category
    title: str
    description: str
    plain_language_summary: Optional[str] = Field(
        None, description="Filled in by the Triage agent node"
    )
    severity: Optional[Severity] = None
    fix_confidence: Optional[float] = Field(
        None, description="0-1, how confident the agent is it can safely auto-fix this"
    )
    affected_selector: Optional[str] = Field(
        None, description="CSS selector or element reference, if applicable"
    )


class UXSuggestion(BaseModel):
    """A human judgment about the page's usability or conversion quality."""
    id: str = Field(..., description="Stable ID for the suggestion")
    category: str = Field(..., description="UX theme, e.g. clutter or cta-overload")
    severity: Severity
    observation: str = Field(..., description="What the model observed on the page")
    recommendation: str = Field(..., description="What should change")


class Fix(BaseModel):
    """A proposed concrete patch for a given issue."""
    issue_id: str
    description: str
    before: str = Field(..., description="Original HTML/attribute snippet")
    after: str = Field(..., description="Proposed replacement snippet")
    approved: Optional[bool] = None
    applied: bool = False
    verified_cleared: Optional[bool] = None
    attempts: int = 0


class AuditResult(BaseModel):
    url: str
    scores: dict[Category, float] = Field(default_factory=dict)
    issues: list[Issue] = Field(default_factory=list)


class SiteDoctorState(BaseModel):
    """The full LangGraph state passed between nodes."""
    selected_checks: list[str] = Field(default_factory=lambda: ["seo", "ux"])
    url: str
    local_copy_path: Optional[str] = None
    screenshot_paths: list[str] = Field(default_factory=list)
    audit_before: Optional[AuditResult] = None
    audit_after: Optional[AuditResult] = None
    ux_suggestions: list[UXSuggestion] = Field(default_factory=list)
    fixes: list[Fix] = Field(default_factory=list)
    max_retries_per_fix: int = 2
