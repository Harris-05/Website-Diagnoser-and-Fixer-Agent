"""Generates a human-readable PDF report from a completed pipeline run --
this is the deliverable a human reviews to decide whether to let the
agent proceed into an actual apply loop later.

Groups everything by page (source_url), shows severity, plain-language
summary, the suggested fix, its confidence score, and any web-search
sources -- pulling directly from SiteDoctorState.triaged_issues (already
fully populated by triage_node + fix_node).
"""

from collections import defaultdict

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
)

from models.schemas import SiteDoctorState, Issue, Severity

_SEVERITY_COLOR = {
    Severity.HIGH: colors.HexColor("#c0392b"),
    Severity.MEDIUM: colors.HexColor("#d68910"),
    Severity.LOW: colors.HexColor("#7f8c8d"),
}


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="PageHeading", parent=styles["Heading2"],
        spaceBefore=18, spaceAfter=8, textColor=colors.HexColor("#1a1a2e"),
    ))
    styles.add(ParagraphStyle(
        name="IssueTitle", parent=styles["Heading4"],
        spaceBefore=10, spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="Body", parent=styles["Normal"],
        fontSize=9.5, leading=13, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="Meta", parent=styles["Normal"],
        fontSize=8.5, textColor=colors.HexColor("#555555"), spaceAfter=6,
    ))
    return styles


def _severity_badge(severity, styles) -> Paragraph:
    if severity is None:
        return Paragraph("SEVERITY: UNKNOWN", styles["Meta"])
    color = _SEVERITY_COLOR.get(severity, colors.black)
    return Paragraph(
        f'<font color="{color.hexval()}"><b>{severity.value.upper()}</b></font>',
        styles["Meta"],
    )


def _confidence_label(confidence) -> str:
    if confidence is None:
        return "unknown"
    if confidence >= 0.7:
        return f"{confidence:.0%} -- likely auto-fixable"
    if confidence >= 0.4:
        return f"{confidence:.0%} -- may need review"
    return f"{confidence:.0%} -- needs human/design judgment"


def _score_summary_table(audit_before, styles):
    """Small per-page score table at the top of the report, if audit
    results are available."""
    if not audit_before:
        return None

    header = ["Page", "SEO", "Accessibility", "Performance"]
    rows = [header]
    for result in audit_before:
        scores = result.scores or {}
        rows.append([
            Paragraph(result.url, styles["Body"]),
            str(scores.get("seo", "-")),
            str(scores.get("accessibility", "-")),
            str(scores.get("performance", "N/A")),
        ])

    table = Table(rows, colWidths=[3.2 * inch, 0.9 * inch, 1.1 * inch, 1.1 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7f9")]),
    ]))
    return table


def _issue_block(issue: Issue, styles) -> list:
    block = [
        Paragraph(issue.title, styles["IssueTitle"]),
        _severity_badge(issue.severity, styles),
        Paragraph(
            f"<b>What's wrong:</b> {issue.plain_language_summary or issue.description}",
            styles["Body"],
        ),
    ]

    if issue.suggested_solution:
        block.append(
            Paragraph(f"<b>Suggested fix:</b> {issue.suggested_solution}", styles["Body"])
        )

    block.append(
        Paragraph(
            f"<i>Auto-fix confidence: {_confidence_label(issue.fix_confidence)}</i>",
            styles["Meta"],
        )
    )

    if getattr(issue, "solution_sources", None):
        links = "; ".join(
            f'<link href="{url}" color="blue">{url}</link>'
            for url in issue.solution_sources[:3]
        )
        block.append(Paragraph(f"Sources: {links}", styles["Meta"]))

    block.append(Spacer(1, 6))
    return block


def generate_report_pdf(state: SiteDoctorState, output_path: str) -> str:
    styles = _build_styles()
    story = []

    story.append(Paragraph("Site Doctor Report", styles["Title"]))
    story.append(Paragraph(state.url, styles["Normal"]))
    story.append(Spacer(1, 12))

    score_table = _score_summary_table(state.audit_before, styles)
    if score_table:
        story.append(Paragraph("Score Overview", styles["Heading2"]))
        story.append(score_table)
        story.append(Spacer(1, 12))

    # group triaged_issues by source_url so the report reads page-by-page,
    # not as one undifferentiated flat list
    by_page = defaultdict(list)
    for issue in state.triaged_issues:
        by_page[getattr(issue, "source_url", None) or "(unknown page)"].append(issue)

    severity_order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2, None: 3}

    for page_url, issues in by_page.items():
        issues.sort(key=lambda i: severity_order.get(i.severity, 3))
        story.append(Paragraph(page_url, styles["PageHeading"]))
        for issue in issues:
            story.extend(_issue_block(issue, styles))
        story.append(Spacer(1, 8))

    if not state.triaged_issues:
        story.append(Paragraph("No issues found.", styles["Body"]))

    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )
    doc.build(story)
    return output_path