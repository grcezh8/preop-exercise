"""rule 1: most recent h&p within 30 days of the procedure and completed, most recent consent signed"""

from __future__ import annotations

import re

from triage.normalize.text import find_first
from triage.rules.common import doc_label, excerpt, issue, on_file, window_details
from triage.schemas.findings import Findings
from triage.schemas.normalized import NormalizedCase
from triage.schemas.output import TriageIssue
from triage.vocab.doc_titles import HP_VARIANTS
from triage.vocab.phrases import HP_UNFINISHED

HP_WINDOW_DAYS = 30


def check_documents(case: NormalizedCase, findings: Findings) -> list[TriageIssue]:
    return _check_hp(case) + _check_consent(case, findings)


def _check_hp(case: NormalizedCase) -> list[TriageIssue]:
    dated = [d for d in case.docs if d.kind == "HP" and d.date is not None]
    if not dated:
        return [
            issue(
                "REQUIRED_DOCUMENTATION",
                "History and Physical document missing",
                "documents",
                "No History and Physical document with valid date found" + on_file([doc_label(d) for d in case.docs]),
            )
        ]
    hp = max(dated, key=lambda d: (d.date, d.index))
    source = f"documents[{hp.index}]"
    procedure_date = case.procedure.date
    if procedure_date is not None:
        days = (procedure_date - hp.date).days  # type: ignore[operator]
        if not 0 <= days <= HP_WINDOW_DAYS:
            return [
                issue(
                    "REQUIRED_DOCUMENTATION",
                    "H&P outside 30-day window",
                    source,
                    window_details("H&P date", str(hp.date_raw), case.procedure.date_raw, days, HP_WINDOW_DAYS),
                )
            ]
    text = hp.text_clean
    for pattern in HP_VARIANTS:
        text = re.sub(pattern, "h&p", text)
    unfinished = find_first(HP_UNFINISHED, text)
    if unfinished:
        return [
            issue(
                "REQUIRED_DOCUMENTATION",
                "H&P not completed",
                source,
                f"Most recent H&P {doc_label(hp)} is not complete: \"{excerpt(hp, unfinished.group(0))}\"",
            )
        ]
    return []


def _check_consent(case: NormalizedCase, findings: Findings) -> list[TriageIssue]:
    consent = findings.consent
    if consent is None:
        return [
            issue(
                "REQUIRED_DOCUMENTATION",
                "Signed surgical consent missing",
                "documents",
                "No Surgical Consent document found" + on_file([doc_label(d) for d in case.docs]),
            )
        ]
    if consent.status == "SIGNED":
        return []
    doc = case.docs[consent.doc_index]
    reason = f"; {consent.note}" if consent.note else ""
    return [
        issue(
            "REQUIRED_DOCUMENTATION",
            "Surgical consent not clearly signed",
            f"documents[{doc.index}]",
            f"Consent document {doc_label(doc)} text does not clearly indicate signed consent: "
            f"\"{excerpt(doc, consent.cue)}\"{reason}",
        )
    ]
