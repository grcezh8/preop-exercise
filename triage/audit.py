"""per-case record of what each step decided, for debugging a wrong answer without re-running
stores list positions, kinds and statuses, never note text or patient details
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from triage.llm.base import CallMeta
from triage.schemas.findings import Findings
from triage.schemas.normalized import DocKind, KindSource, NormalizedCase
from triage.schemas.output import Decision


class DocTrace(BaseModel):
    index: int
    kind: DocKind
    kind_source: KindSource
    truncated: bool


class RuleTrace(BaseModel):
    rule: str
    # (category, description, source) per issue, details are left out because they quote note text
    issues: list[tuple[str, str, str]]


class LLMCallTrace(BaseModel):
    step: str
    model: str
    prompt_version: str
    ok: bool
    reason: str | None = None
    cache_hit: bool = False
    attempts: int = 0
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


class AuditRecord(BaseModel):
    case_ref: str
    decision: Decision
    input_warnings: list[str]
    documents: list[DocTrace]
    consent: dict[str, Any] | None
    note_mentions: list[dict[str, Any]]
    plans: list[dict[str, Any]]
    rules: list[RuleTrace]
    llm_calls: list[LLMCallTrace]


def case_ref(data: dict[str, Any]) -> str:
    # the case id when there is one, otherwise a short hash of the package
    procedure = data.get("procedure") or {}
    case_id = procedure.get("case_id") if isinstance(procedure, dict) else None
    if isinstance(case_id, str) and case_id.strip():
        return re.sub(r"[^A-Za-z0-9_.-]", "_", case_id.strip())
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    return f"sha256-{digest[:16]}"


def build_record(
    *,
    data: dict[str, Any],
    decision: Decision,
    warnings: list[str],
    case: NormalizedCase,
    findings: Findings,
    rules: list[RuleTrace],
    llm_calls: list[tuple[CallMeta, bool, str | None]],
) -> AuditRecord:
    return AuditRecord(
        case_ref=case_ref(data),
        decision=decision,
        input_warnings=warnings,
        documents=[DocTrace(index=d.index, kind=d.kind, kind_source=d.kind_source, truncated=d.truncated) for d in case.docs],
        consent=findings.consent.model_dump(exclude={"cue"}) if findings.consent else None,
        note_mentions=[m.model_dump(exclude={"quote"}) for m in findings.note_mentions],
        plans=[p.model_dump() for p in findings.plans],
        rules=rules,
        llm_calls=[
            LLMCallTrace(
                step=meta.step,
                model=meta.model,
                prompt_version=meta.prompt_version,
                ok=ok,
                reason=reason,
                cache_hit=meta.cache_hit,
                attempts=meta.attempts,
                latency_ms=meta.latency_ms,
                input_tokens=meta.input_tokens,
                output_tokens=meta.output_tokens,
            )
            for meta, ok, reason in llm_calls
        ],
    )


def write_record(record: AuditRecord, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record.case_ref}.json"
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return path
