"""Core data models shared across the LangGraph state."""

from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


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
    """A single mechanically-verifiable problem found by the rule-based
    audit engine (Lighthouse) or the passive security checks. Has a real
    pass/fail check, so it's the only type that goes through the
    fix -> apply -> reaudit -> retry loop."""
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
    """A judgment-call finding from the vision-based UX review. No ground
    truth to mechanically re-check, so these are surfaced to the human as
    suggestions rather than run through the auto-fix/verify loop."""
    id: str
    category: str = Field(
        ..., description="e.g. clutter, cta-overload, hierarchy, trust-signal"
    )
    severity: Severity
    observation: str = Field(..., description="What the model saw")
    recommendation: str = Field(..., description="What to change")


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


class PageResult(BaseModel):
    """One crawled page's artifacts and where they live on disk."""
    url: str
    slug: str
    html_path: str
    screenshot_paths: list[str] = Field(default_factory=list)
    depth: int = 0


class CrawlResult(BaseModel):
    """The full result of a multi-page crawl run."""
    crawl_id: str
    start_url: str
    pages: list[PageResult] = Field(default_factory=list)
    crawled_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class SiteDoctorState(BaseModel):
    """The full LangGraph state passed between nodes."""
    url: str
    selected_checks: list[str] = Field(default_factory=lambda: ["seo", "ux"])
    crawl_result: Optional[CrawlResult] = None
    local_copy_path: Optional[str] = None
    screenshot_paths: list[str] = Field(default_factory=list)
    audit_before: Optional[AuditResult] = None
    audit_after: Optional[AuditResult] = None
    ux_suggestions: list[UXSuggestion] = Field(default_factory=list)
    security_findings: list[Issue] = Field(default_factory=list)
    fixes: list[Fix] = Field(default_factory=list)
    max_retries_per_fix: int = 2