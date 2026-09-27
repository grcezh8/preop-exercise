"""llm step d (python half): which blood thinners need a plan, which note to point at, and the pending-wording veto
without the llm reading the plan nothing can pass, step 4 adds the llm half
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from triage.normalize.case import find_anticoagulants
from triage.normalize.text import find_first
from triage.schemas.findings import NoteMention, PlanFinding
from triage.schemas.normalized import NormalizedCase, NormDoc
from triage.vocab.anticoagulants import GENERIC_TERMS
from triage.vocab.phrases import PLAN_PENDING


@dataclass(frozen=True)
class TakenDrug:
    drug: str
    med_index: int | None
    mention_doc: int | None


def drugs_needing_plan(case: NormalizedCase, mentions: list[NoteMention]) -> list[TakenDrug]:
    # one entry per drug: active in the medication list, or mentioned in a note and not ruled out
    taken: dict[str, TakenDrug] = {}
    for med in case.meds:
        if med.anticoagulant and med.active is True and med.anticoagulant not in taken:
            taken[med.anticoagulant] = TakenDrug(med.anticoagulant, med.index, None)
    for mention in mentions:
        if mention.taking != "NO" and mention.drug not in taken:
            taken[mention.drug] = TakenDrug(mention.drug, None, mention.doc_index)
    return list(taken.values())


def candidate_docs(case: NormalizedCase, drug: str) -> list[NormDoc]:
    # notes that could hold a plan for this drug: titled as one, naming the drug, or talking about blood thinners
    def relevant(doc: NormDoc) -> bool:
        if doc.kind == "ANTICOAG_NOTE":
            return True
        if any(generic == drug for generic, _ in find_anticoagulants(doc.text_clean)):
            return True
        return any(term in doc.text_clean for term in GENERIC_TERMS)

    return [doc for doc in case.docs if relevant(doc)]


def pointed_doc(candidates: list[NormDoc]) -> NormDoc | None:
    # the note evidence points at: the most recent one titled as a plan, else the most recent candidate
    def recency(doc: NormDoc) -> tuple[dt.date, int]:
        return (doc.date or dt.date.min, doc.index)

    titled = [d for d in candidates if d.kind == "ANTICOAG_NOTE"]
    return max(titled or candidates, key=recency, default=None)


def pending_veto(candidates: list[NormDoc]) -> str | None:
    for doc in candidates:
        match = find_first(PLAN_PENDING, doc.text_clean)
        if match:
            return match.group(0)
    return None


def assess_plans(case: NormalizedCase, mentions: list[NoteMention]) -> list[PlanFinding]:
    findings: list[PlanFinding] = []
    for taken in drugs_needing_plan(case, mentions):
        candidates = candidate_docs(case, taken.drug)
        doc = pointed_doc(candidates)
        findings.append(
            PlanFinding(
                drug=taken.drug,
                med_index=taken.med_index,
                mention_doc=taken.mention_doc,
                passes=False,
                checked_doc=doc.index if doc else None,
                gaps=() if candidates else ("no note describes a plan",),
                veto=pending_veto(candidates),
                decided_by="default",
            )
        )
    return findings
