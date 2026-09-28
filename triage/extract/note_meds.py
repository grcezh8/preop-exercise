"""llm step c: blood thinners named in notes but not active in the medication list
python finds the mentions, the llm reads the passage around each one
only a NO with a quote showing stopped, never, past or future use rules the drug out, anything else needs a plan
"""

from __future__ import annotations

from triage.extract.reader import Reader, has_cue, quote_found
from triage.normalize.case import find_anticoagulants
from triage.normalize.text import keyword_windows
from triage.schemas.findings import NoteMention
from triage.schemas.llm import NoteMedAnswer, NoteMedPrompt
from triage.schemas.normalized import NormalizedCase
from triage.vocab.phrases import STOPPED_CUES


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


def assess_note_mentions(case: NormalizedCase, reader: Reader | None) -> list[NoteMention]:
    mentions = find_note_mentions(case)
    if reader is None or not mentions:
        return mentions  # every mention stays UNCLEAR, a plan is required
    return reader.run_all(lambda m: _ask(case, m, reader), mentions)


def _ask(case: NormalizedCase, mention: NoteMention, reader: Reader) -> NoteMention:
    doc = case.docs[mention.doc_index]
    pieces, _ = keyword_windows(doc.text_raw, [mention.word], reader.settings.snippet_radius, reader.settings.max_prompt_chars)
    passage = reader.redact("\n...\n".join(pieces))
    if not passage:
        return mention  # the word came from look-alike letters and isn't in the original, stays UNCLEAR

    def check(answer: NoteMedAnswer) -> str | None:
        if answer.currently_taking == "UNCLEAR":
            return None
        if not quote_found(answer.quote, passage):
            return "quote is not in the passage"
        if answer.currently_taking == "NO" and not has_cue(answer.quote, STOPPED_CUES):
            return "quote doesn't say the drug was stopped, never taken, or only planned"
        return None

    asked = reader.ask("note_meds", NoteMedPrompt(drug=mention.drug, passage=passage), NoteMedAnswer, check)
    if asked.value is None:
        return mention
    return mention.model_copy(update={"taking": asked.value.currently_taking, "decided_by": "llm"})
