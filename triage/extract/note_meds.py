"""llm step c (python half): blood thinners named in notes but not active in the medication list
until the llm reads the passage every mention is UNCLEAR, which means a plan is required
"""

from __future__ import annotations

from triage.normalize.case import find_anticoagulants
from triage.schemas.findings import NoteMention
from triage.schemas.normalized import NormalizedCase


def find_note_mentions(case: NormalizedCase) -> list[NoteMention]:
    # drugs listed as active already need a plan, drugs listed with active=null already get
    # "unknown anticoagulant active status", so only drugs missing from the list or listed inactive are checked
    active = {m.anticoagulant for m in case.meds if m.anticoagulant and m.active is True}
    unknown = {m.anticoagulant for m in case.meds if m.anticoagulant and m.active is None}
    mentions: list[NoteMention] = []
    seen: set[tuple[str, int]] = set()
    for doc in case.docs:
        for drug, word in find_anticoagulants(doc.text_clean):
            if drug in active or drug in unknown or (drug, doc.index) in seen:
                continue
            seen.add((drug, doc.index))
            mentions.append(
                NoteMention(drug=drug, doc_index=doc.index, word=word, taking="UNCLEAR", decided_by="default")
            )
    return mentions
