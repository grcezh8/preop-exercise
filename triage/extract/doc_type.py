"""llm step a: reads documents the title rules couldn't sort (UNKNOWN) or couldn't confirm (VAGUE_HP)
sends the title and the first ~300 characters, patient details removed
an HP or CONSENT answer only counts with a quote from the text that shows it, otherwise the kind stays unresolved
"""

from __future__ import annotations

from triage.extract.reader import Reader, has_cue, quote_found
from triage.schemas.llm import DocTypeAnswer, DocTypePrompt
from triage.schemas.normalized import NormalizedCase, NormDoc
from triage.vocab.phrases import CONSENT_CUES, HP_CUES

TEXT_START_CHARS = 300


def resolve_doc_types(case: NormalizedCase, reader: Reader) -> NormalizedCase:
    todo = [doc for doc in case.docs if doc.kind in ("UNKNOWN", "VAGUE_HP")]
    if not todo:
        return case
    resolved = {doc.index: doc for doc in reader.run_all(lambda d: _ask(d, reader), todo)}
    return case.model_copy(update={"docs": [resolved.get(doc.index, doc) for doc in case.docs]})


def _ask(doc: NormDoc, reader: Reader) -> NormDoc:
    text_start = reader.redact(doc.text_raw[:TEXT_START_CHARS])
    prompt = DocTypePrompt(title=reader.redact(doc.title_raw), text_start=text_start)

    def check(answer: DocTypeAnswer) -> str | None:
        if answer.kind in ("OTHER", "ANTICOAG_NOTE"):
            return None  # these can't move a case toward READY
        if not quote_found(answer.quote, text_start):
            return "quote is not in text_start"
        if answer.kind == "HP" and not has_cue(answer.quote, HP_CUES):
            return "quote doesn't mention a history or an exam"
        if answer.kind == "CONSENT" and not has_cue(answer.quote, CONSENT_CUES):
            return "quote doesn't mention consent"
        return None

    asked = reader.ask("doc_type", prompt, DocTypeAnswer, check)
    if asked.value is None:
        return doc  # stays UNKNOWN or VAGUE_HP, which doesn't count as an h&p or consent
    return doc.model_copy(update={"kind": asked.value.kind, "kind_source": "llm"})
