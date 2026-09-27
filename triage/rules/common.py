"""helpers shared by the rules"""

from __future__ import annotations

from triage.normalize.text import sentence_around
from triage.schemas.normalized import NormDoc
from triage.schemas.output import IssueCategory, TriageIssue, TriageIssueEvidence


def issue(category: IssueCategory, description: str, source: str, details: str) -> TriageIssue:
    return TriageIssue(
        category=category,
        description=description,
        evidence=TriageIssueEvidence(source=source, details=details),
    )


def doc_label(doc: NormDoc) -> str:
    # e.g. 'Surgery Consent (scanned)' dated 2026-02-25, the title and date make evidence traceable
    title = doc.title_raw or "untitled document"
    return f"'{title}' dated {doc.date_raw}" if doc.date_raw else f"'{title}' (no date)"


def on_file(items: list[str]) -> str:
    # e.g. " (on file: 'Consent Packet' dated 2026-03-08)", what was checked when something is missing
    return f" (on file: {'; '.join(items)})" if items else " (none on file)"


def excerpt(doc: NormDoc, near: str | None = None) -> str:
    # an exact piece of the original note text, the whole note when it's short
    return sentence_around(doc.text_raw, near or "")


def window_details(label: str, when_raw: str, procedure_raw: object, days: int, limit: int) -> str:
    # e.g. CBC effective_at 2026-02-19T09:10:00Z vs procedure_date 2026-03-11 (20 days prior; must be within 14)
    if days < 0:
        gap = f"{-days} days after the procedure; must be within {limit} days before"
    else:
        gap = f"{days} days prior; must be within {limit}"
    return f"{label} {when_raw} vs procedure_date {procedure_raw} ({gap})"
