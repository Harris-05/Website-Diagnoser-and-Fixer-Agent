
from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from agent.graph import build_graph
from models.schemas import (
    AuditResult,
    Issue,
    SiteDoctorState,
    UXSuggestion,
)

app = FastAPI(
    title="Site Doctor API",
    description="Runs the Site Doctor crawl/audit/triage/fix LangGraph pipeline over HTTP.",
    version="1.0.0",
)

_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",  # `vite preview`
    "http://127.0.0.1:4173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEV_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

_graph = build_graph()

CheckName = Literal["seo", "ux", "security"]


class AuditRequest(BaseModel):
    url: str = Field(..., description="The URL to crawl and audit, e.g. https://example.com")
    checks: list[CheckName] = Field(
        default_factory=lambda: ["seo", "ux"],
        description="Which audit branches to run. Defaults to SEO + UX if empty/omitted.",
    )
    max_depth: int = Field(2, ge=0, le=10, description="Max crawl depth (BFS hops from the start URL).")
    max_pages: int = Field(10, ge=1, le=200, description="Max number of pages to crawl.")
    security_confirmed: bool = Field(
        False,
        description=(
            "Must be true to actually run the 'security' check. This only "
            "unlocks PASSIVE checks (HTTP security headers, TLS cert "
            "validity) -- equivalent to the old CLI's y/N prompt. It does "
            "NOT unlock active/attacking security tooling, which this API "
            "never exposes."
        ),
    )
    generate_report: bool = Field(True, description="Whether to generate the PDF report.")

    @field_validator("url")
    @classmethod
    def _must_be_http_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("url must start with http:// or https://")
        return v


class AuditResponse(BaseModel):
    url: str
    selected_checks: list[str]
    pages_crawled: int
    audit_before: list[AuditResult]
    ux_suggestions: list[UXSuggestion]
    security_findings: list[Issue]
    triaged_issues: list[Issue]
    report_available: bool
    report_download_url: str | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/audit", response_model=AuditResponse)
def run_audit(payload: AuditRequest) -> AuditResponse:
    """Runs the full graph loop synchronously for one URL and returns the
    triaged issues + report path.

    Defined as a plain `def` (not `async def`) on purpose: FastAPI/
    Starlette run sync route handlers in a worker thread, which is
    required here since several downstream nodes use Playwright's *sync*
    API (crawler/crawl.py) -- calling that from inside the main asyncio
    event loop raises at runtime.
    """
    initial_state = SiteDoctorState(
        url=payload.url,
        selected_checks=list(payload.checks),
        max_depth=payload.max_depth,
        max_pages=payload.max_pages,
        security_confirmed=payload.security_confirmed,
        generate_report=payload.generate_report,
    )

    try:
        result = _graph.invoke(initial_state)
    except Exception as exc:  # surface pipeline failures as a clean 500 instead of a stack trace to the caller
        raise HTTPException(status_code=500, detail=f"Audit pipeline failed: {exc}") from exc

    # langgraph's .invoke() returns a plain dict of the accumulated state
    final = SiteDoctorState.model_validate(result)

    report_download_url = None
    if final.report_path:
        report_download_url = f"/reports/{Path(final.report_path).name}"

    return AuditResponse(
        url=final.url,
        selected_checks=final.selected_checks,
        pages_crawled=len(final.crawl_result.pages) if final.crawl_result else 0,
        audit_before=final.audit_before,
        ux_suggestions=final.ux_suggestions,
        security_findings=final.security_findings,
        triaged_issues=final.triaged_issues,
        report_available=final.report_path is not None,
        report_download_url=report_download_url,
    )


@app.get("/reports/{filename}")
def download_report(filename: str) -> FileResponse:
    """Serves a previously generated PDF report by filename.

    Filenames are always of the form site_doctor_report_<crawl_id>.pdf,
    written by report/generate_pdf.py into .site-doctor-cache/. Path
    traversal is blocked by only ever looking inside that directory and
    rejecting any name containing a path separator.
    """
    if "/" in filename or "\\" in filename or not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid report filename.")

    report_path = Path(".site-doctor-cache") / filename
    if not report_path.is_file():
        raise HTTPException(status_code=404, detail="Report not found.")

    return FileResponse(report_path, media_type="application/pdf", filename=filename)