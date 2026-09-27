"""llm step b (pattern half): is the most recent consent signed
step 4 adds the llm half, the consent only counts as signed when both say SIGNED
"""

from __future__ import annotations

import datetime as dt

from triage.normalize.text import find_first
from triage.schemas.findings import ConsentFinding, ConsentStatus
from triage.schemas.normalized import NormalizedCase, NormDoc
from triage.vocab.phrases import CONSENT_NOT_SIGNED, CONSENT_SIGNED


def latest_consent(case: NormalizedCase) -> NormDoc | None:
    # undated consents sort oldest, ties go to the later list position
    consents = [d for d in case.docs if d.kind == "CONSENT"]
    return max(consents, key=lambda d: (d.date or dt.date.min, d.index), default=None)


def pattern_consent(text_clean: str) -> tuple[ConsentStatus, str | None]:
    # not-signed wording always wins, "unsigned" contains "signed"
    negative = find_first(CONSENT_NOT_SIGNED, text_clean)
    if negative:
        return "NOT_SIGNED", negative.group(0)
    positive = find_first(CONSENT_SIGNED, text_clean)
    if positive:
        return "SIGNED", positive.group(0)
    return "UNCLEAR", None


def assess_consent(case: NormalizedCase) -> ConsentFinding | None:
    doc = latest_consent(case)
    if doc is None:
        return None
    status, cue = pattern_consent(doc.text_clean)
    return ConsentFinding(doc_index=doc.index, status=status, pattern_status=status, cue=cue)
