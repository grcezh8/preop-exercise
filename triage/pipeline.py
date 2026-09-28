"""runs one case through every step in a fixed order
ingest -> normalize -> llm reads (document types, then consent + note meds, then plans) -> rules
-> decision and output -> output check -> audit
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from triage.audit import AuditRecord, RuleTrace, build_record, write_record
from triage.config import Settings
from triage.extract.anticoag_plan import assess_plans
from triage.extract.consent import assess_consent
from triage.extract.doc_type import resolve_doc_types
from triage.extract.note_meds import assess_note_mentions
from triage.extract.reader import Reader
from triage.ingest import ingest
from triage.llm.base import LLMClient
from triage.llm.openai_client import default_client
from triage.llm.redact import Redactor
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


def run_triage(raw: object, settings: Settings, llm: LLMClient | None = None) -> TriageRun:
    ingested = ingest(raw)
    case = normalize(ingested.submission, max_doc_chars=settings.max_doc_chars, pattern_only=settings.pattern_only)

    # pattern_only runs never call an llm, otherwise every free-text approval goes through one
    reader = None
    if not settings.pattern_only:
        reader = Reader(llm or default_client(settings), settings, Redactor(ingested.data))
        case = resolve_doc_types(case, reader)

    # consent and note mentions don't depend on each other, the plan needs the mentions
    with ThreadPoolExecutor(max_workers=2) as pool:
        consent = pool.submit(assess_consent, case, pattern_only=settings.pattern_only, reader=reader)
        mentions = pool.submit(assess_note_mentions, case, reader)
        findings = Findings(consent=consent.result(), note_mentions=tuple(mentions.result()))
    findings = findings.model_copy(update={"plans": tuple(assess_plans(case, list(findings.note_mentions), reader))})

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
        llm_calls=list(reader.calls) if reader else [],
    )
    if settings.audit_enabled:
        write_record(audit, settings.audit_dir)
    return TriageRun(output, audit)


def triage_submission(
    submission: dict[str, object] | PatientSubmission | str,
    *,
    model: str | None = None,
    settings: Settings | None = None,
    llm: LLMClient | None = None,
) -> TriageOutput:
    # entry point used by the harness, model sets the medium llm tier, openai is used unless llm is given
    settings = settings or Settings.from_env(model_medium=model)
    return run_triage(submission, settings, llm).output
