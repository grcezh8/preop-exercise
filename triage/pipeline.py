"""runs one case through every step in a fixed order
ingest -> normalize -> text checks -> rules -> decision and output -> output check -> audit
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from triage.audit import AuditRecord, RuleTrace, build_record, write_record
from triage.config import Settings
from triage.extract.anticoag_plan import assess_plans
from triage.extract.consent import assess_consent
from triage.extract.note_meds import find_note_mentions
from triage.ingest import ingest
from triage.normalize.case import normalize
from triage.render import build_output, check_output
from triage.rules.anticoag import check_anticoagulation
from triage.rules.documents import check_documents
from triage.rules.labs import check_labs
from triage.rules.required_fields import check_required_fields
from triage.rules.safety import check_safety
from triage.schemas.findings import Findings
from triage.schemas.input import PatientSubmission
from triage.schemas.normalized import NormalizedCase
from triage.schemas.output import TriageIssue, TriageOutput

Rule = Callable[[NormalizedCase, Findings], list[TriageIssue]]

# issues come out in this order, which is also the order the expected outputs use
RULES: tuple[tuple[str, Rule], ...] = (
    ("required_fields", lambda case, findings: check_required_fields(case)),
    ("documents", check_documents),
    ("labs", lambda case, findings: check_labs(case)),
    ("anticoagulation", check_anticoagulation),
    ("safety", lambda case, findings: check_safety(case)),
)


@dataclass
class TriageRun:
    output: TriageOutput
    audit: AuditRecord


def run_triage(raw: object, settings: Settings) -> TriageRun:
    ingested = ingest(raw)
    case = normalize(ingested.submission, max_doc_chars=settings.max_doc_chars)

    mentions = find_note_mentions(case)
    findings = Findings(
        consent=assess_consent(case),
        note_mentions=tuple(mentions),
        plans=tuple(assess_plans(case, mentions)),
    )

    issues: list[TriageIssue] = []
    traces: list[RuleTrace] = []
    for name, rule in RULES:
        found = rule(case, findings)
        issues.extend(found)
        traces.append(RuleTrace(rule=name, issues=[(i.category, i.description, i.evidence.source) for i in found]))

    output = build_output(issues)
    check_output(output, ingested.data)

    audit = build_record(
        data=ingested.data,
        decision=output.decision,
        warnings=ingested.warnings,
        case=case,
        findings=findings,
        rules=traces,
        llm_calls=[],
    )
    if settings.audit_enabled:
        write_record(audit, settings.audit_dir)
    return TriageRun(output, audit)


def triage_submission(
    submission: dict[str, object] | PatientSubmission | str,
    *,
    model: str | None = None,
    settings: Settings | None = None,
) -> TriageOutput:
    # entry point used by the harness, model sets the medium llm tier
    settings = settings or Settings.from_env(model_medium=model)
    return run_triage(submission, settings).output
