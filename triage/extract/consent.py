"""llm step b: is the most recent consent signed
python wording can only block (unsigned, missing, instructions in the note), the llm has to approve
a SIGNED answer only counts with a quote found in the note that contains signature wording
"""

from __future__ import annotations

import datetime as dt

from triage.extract.reader import Reader, has_cue, quote_found
from triage.normalize.text import clean, find_first, keyword_windows
from triage.schemas.findings import ConsentFinding, ConsentStatus
from triage.schemas.llm import ConsentAnswer, ConsentPrompt
from triage.schemas.normalized import NormalizedCase, NormDoc
from triage.vocab.phrases import CONSENT_NOT_SIGNED, CONSENT_SIGNED, INJECTION, SIGNATURE_CUES

# words the passages sent to the llm are cut around when a consent is long
CONSENT_KEYWORDS = ("sign", "e-sign", "esign", "docusign", "executed", "consent", "witness", "unsigned")


def latest_consent(case: NormalizedCase) -> NormDoc | None:
    # undated consents sort oldest, ties go to the later list position
    consents = [d for d in case.docs if d.kind == "CONSENT"]
    return max(consents, key=lambda d: (d.date or dt.date.min, d.index), default=None)


def pattern_consent(text_clean: str) -> tuple[ConsentStatus, str | None]:
    # a note that gives instructions is never trusted, then not-signed wording always wins ("unsigned" contains "signed")
    injected = find_first(INJECTION, text_clean)
    if injected:
        return "UNCLEAR", injected.group(0)
    negative = find_first(CONSENT_NOT_SIGNED, text_clean)
    if negative:
        return "NOT_SIGNED", negative.group(0)
    positive = find_first(CONSENT_SIGNED, text_clean)
    if positive:
        return "SIGNED", positive.group(0)
    return "UNCLEAR", None


def assess_consent(case: NormalizedCase, *, pattern_only: bool, reader: Reader | None = None) -> ConsentFinding | None:
    doc = latest_consent(case)
    if doc is None:
        return None
    status, cue = pattern_consent(doc.text_clean)
    found = ConsentFinding(doc_index=doc.index, status=status, pattern_status=status, cue=cue)
    if pattern_only:
        return found
    blocked = status == "NOT_SIGNED" or (status == "UNCLEAR" and cue is not None)
    if blocked:
        return found  # python already says no, the llm isn't asked
    if reader is None:
        return _unconfirmed(found, "signature wording not confirmed by a second check")
    return _ask(doc, found, reader)


def _ask(doc: NormDoc, found: ConsentFinding, reader: Reader) -> ConsentFinding:
    settings = reader.settings
    pieces, truncated = keyword_windows(doc.text_raw, CONSENT_KEYWORDS, settings.snippet_radius, settings.max_prompt_chars)
    text = reader.redact("\n...\n".join(pieces))

    def check(answer: ConsentAnswer) -> str | None:
        if answer.status == "UNCLEAR":
            return None
        if not quote_found(answer.quote, text):
            return "quote is not in the text"
        if answer.status == "SIGNED" and not has_cue(answer.quote, SIGNATURE_CUES):
            return "quote doesn't mention a signature"
        if answer.status == "SIGNED" and find_first(CONSENT_NOT_SIGNED, clean(answer.quote)):
            return "quote says it isn't signed"
        return None

    asked = reader.ask("consent", ConsentPrompt(text=text), ConsentAnswer, check)
    if asked.value is None:
        return _unconfirmed(found, "signature could not be confirmed (automated reading unavailable)")
    llm_status = asked.value.status
    if llm_status == "SIGNED" and truncated:
        return _unconfirmed(found, "consent too long to read in full", llm_status)
    note = "wording check and automated reading disagree" if found.pattern_status == "SIGNED" and llm_status != "SIGNED" else None
    return found.model_copy(update={"status": llm_status, "llm_status": llm_status, "decided_by": "llm", "note": note})


def _unconfirmed(found: ConsentFinding, note: str, llm_status: ConsentStatus | None = None) -> ConsentFinding:
    return found.model_copy(update={"status": "UNCLEAR", "llm_status": llm_status, "decided_by": "default", "note": note})
