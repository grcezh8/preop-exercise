"""what the free-text checks concluded, the rules read these instead of the note text
decided_by says whether the answer came from patterns only, the llm, or a cautious default after a failure
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

ConsentStatus = Literal["SIGNED", "NOT_SIGNED", "UNCLEAR"]
Taking = Literal["YES", "NO", "UNCLEAR"]
DecidedBy = Literal["patterns", "llm", "default"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class ConsentFinding(_Frozen):
    doc_index: int
    status: ConsentStatus
    pattern_status: ConsentStatus
    llm_status: ConsentStatus | None = None
    # the wording that decided it, quoted in evidence
    cue: str | None = None
    decided_by: DecidedBy = "patterns"
    # why the llm answer wasn't used, or why pattern and llm disagreed
    note: str | None = None


class NoteMention(_Frozen):
    # a blood thinner named in a note but not marked active in the medication list
    drug: str
    doc_index: int
    # the matched word as written, e.g. "coumadin"
    word: str
    taking: Taking
    decided_by: DecidedBy
    quote: str | None = None


class PlanFinding(_Frozen):
    drug: str
    # where we know the patient takes it from, a medication entry or a note mention
    med_index: int | None = None
    mention_doc: int | None = None
    passes: bool
    # the note the evidence points at, None when no note talks about blood thinners
    checked_doc: int | None = None
    # what's missing, e.g. "no after-surgery timing"
    gaps: tuple[str, ...] = ()
    # pending wording found by python, e.g. "to be finalized"
    veto: str | None = None
    decided_by: DecidedBy = "default"


class Findings(_Frozen):
    consent: ConsentFinding | None
    note_mentions: tuple[NoteMention, ...] = ()
    plans: tuple[PlanFinding, ...] = ()
