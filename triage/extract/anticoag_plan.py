"""llm step d: does each blood thinner the patient takes have a plan for before and after surgery
python picks the drugs, the notes, the passages and the pending veto, the llm extracts actions, timing and quotes,
then code decides: a plan passes only when every part is stated, quoted from the notes, names the drug, and nothing blocks it
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from triage.config import Settings
from triage.extract.reader import Reader, has_cue, quote_found
from triage.normalize.case import find_anticoagulants
from triage.normalize.text import clean, find_first, keyword_windows
from triage.schemas.findings import NoteMention, PlanFinding
from triage.schemas.llm import DrugPlan, Passage, PlanAnswer, PlanPrompt
from triage.schemas.normalized import NormalizedCase, NormDoc
from triage.vocab.anticoagulants import ANTICOAGULANTS, GENERIC_TERMS
from triage.vocab.phrases import (
    AFTER_ACTION_CUES,
    AFTER_CONTEXT_CUES,
    BEFORE_ACTION_CUES,
    BEFORE_CONTEXT_CUES,
    INJECTION,
    PLAN_PENDING,
    TIMING_CUES,
)

# words the passages sent to the llm are cut around, plus the drug names
PLAN_WORDS = (
    "hold", "held", "stop", "discontinu", "last dose", "resume", "restart", "bridg", "continu",
    "pre-op", "preop", "post-op", "postop", "before surgery", "after surgery", "perioperative", "peri-op",
)


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
    # pending wording, or a note giving instructions, blocks the plan whatever the llm says
    for doc in candidates:
        match = find_first(INJECTION, doc.text_clean) or find_first(PLAN_PENDING, doc.text_clean)
        if match:
            return match.group(0)
    return None


def assess_plans(
    case: NormalizedCase, mentions: list[NoteMention], reader: Reader | None = None
) -> list[PlanFinding]:
    taken = drugs_needing_plan(case, mentions)
    if not taken:
        return []
    candidates = {t.drug: candidate_docs(case, t.drug) for t in taken}
    read, answered = _read_plans(case, taken, candidates, reader) if reader else ({}, False)
    findings: list[PlanFinding] = []
    for t in taken:
        docs = candidates[t.drug]
        doc = pointed_doc(docs)
        veto = pending_veto(docs)
        if not docs:
            gaps: tuple[str, ...] = ("no note describes a plan",)
        elif reader is None:
            gaps = ()
        else:
            gaps = read.get(t.drug, ("plan could not be read",))
        findings.append(
            PlanFinding(
                drug=t.drug,
                med_index=t.med_index,
                mention_doc=t.mention_doc,
                passes=reader is not None and bool(docs) and not gaps and veto is None,
                checked_doc=doc.index if doc else None,
                gaps=gaps,
                veto=veto,
                decided_by="llm" if answered else "default",
            )
        )
    return findings


def _read_plans(
    case: NormalizedCase, taken: list[TakenDrug], candidates: dict[str, list[NormDoc]], reader: Reader
) -> tuple[dict[str, tuple[str, ...]], bool]:
    # one llm call for all drugs, returns (drug -> gaps, whether the llm answered)
    # empty gaps means the llm's answer fully backs a plan
    docs = sorted({d.index: d for ds in candidates.values() for d in ds}.values(), key=lambda d: d.index)
    if not docs:
        return {}, False
    drugs = [t.drug for t in taken]
    passages, truncated = _passages(docs, drugs, reader.settings, reader)
    prompt = PlanPrompt(drugs=drugs, passages=passages)
    sent_text = "\n".join(p.text for p in passages)

    def check(answer: PlanAnswer) -> str | None:
        named = [p.drug.strip().casefold() for p in answer.plans]
        if set(named) - set(drugs):
            return "answer includes a drug that wasn't asked about"
        if set(drugs) - set(named):
            return "answer is missing a drug that was asked about"
        for plan in answer.plans:
            for quote in (plan.before_quote, plan.after_quote, plan.pending_quote):
                if quote and not quote_found(quote, sent_text):
                    return "a quote is not in the passages"
        return None

    asked = reader.ask("anticoag_plan", prompt, PlanAnswer, check)
    if asked.value is None:
        return {drug: (f"plan could not be read ({_short(asked.reason)})",) for drug in drugs}, False
    by_drug = {p.drug.strip().casefold(): p for p in asked.value.plans}
    return {drug: _gaps(by_drug[drug], drug, truncated, passages) for drug in drugs}, True


def _gaps(plan: DrugPlan, drug: str, truncated: bool, passages: list[Passage]) -> tuple[str, ...]:
    # what's missing from the llm's answer, checked in code against the quotes it gave
    gaps: list[str] = []
    if plan.says_pending:
        gaps.append("plan is marked pending or deferred")
    if plan.before_action == "NOT_STATED":
        gaps.append("no before-surgery action")
    elif not plan.before_timing:
        gaps.append("no before-surgery timing")
    elif not _shows(plan.before_quote, BEFORE_ACTION_CUES, BEFORE_CONTEXT_CUES):
        gaps.append("before-surgery quote doesn't show the action and timing")
    if plan.after_action == "NOT_STATED":
        gaps.append("no after-surgery action")
    elif not plan.after_timing:
        gaps.append("no after-surgery timing")
    elif not _shows(plan.after_quote, AFTER_ACTION_CUES, AFTER_CONTEXT_CUES):
        gaps.append("after-surgery quote doesn't show the action and timing")
    if not any(_about_drug(q, drug, passages) for q in (plan.before_quote, plan.after_quote)):
        gaps.append(f"plan quotes don't name {drug}")
    if truncated:
        gaps.append("notes too long to read in full")
    return tuple(gaps)


def _about_drug(quote: str | None, drug: str, passages: list[Passage]) -> bool:
    # the quote names the drug, or comes from a passage that names this drug and no other blood thinner,
    # e.g. "Enoxaparin: last dose 24 h before surgery" quoted as "last dose 24 h before surgery"
    if not quote:
        return False
    if any(generic == drug for generic, _ in find_anticoagulants(clean(quote))):
        return True
    source = next((p.text for p in passages if quote_found(quote, p.text)), "")
    return {generic for generic, _ in find_anticoagulants(clean(source))} == {drug}


def _shows(quote: str | None, action: tuple[str, ...], context: tuple[str, ...]) -> bool:
    # the quote itself must state the action, the time, and which side of surgery it's about
    return has_cue(quote, action) and has_cue(quote, TIMING_CUES) and has_cue(quote, context)


def _passages(docs: list[NormDoc], drugs: list[str], settings: Settings, reader: Reader) -> tuple[list[Passage], bool]:
    keywords = [*PLAN_WORDS, *GENERIC_TERMS, *(n for d in drugs for n in ANTICOAGULANTS.get(d, (d,)))]
    passages: list[Passage] = []
    budget = settings.max_prompt_chars
    truncated = False
    for doc in docs:
        pieces, cut = keyword_windows(doc.text_raw, keywords, settings.snippet_radius, budget)
        truncated = truncated or cut
        for piece in pieces:
            passages.append(Passage(id=f"p{len(passages) + 1}", text=reader.redact(piece)))
            budget -= len(piece)
        if budget <= 0:
            truncated = True
            break
    return passages, truncated


def _short(reason: str | None) -> str:
    return "automated reading unavailable" if not reason else reason.split(":")[0][:60]
