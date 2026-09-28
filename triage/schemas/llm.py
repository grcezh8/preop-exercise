"""what each llm step may receive and must return
prompt models only have the fields a step needs and reject extras, so a whole submission can't be sent by mistake
answer models are sent to openai as strict json schemas, the llm can only answer with these fields and values
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# step a: document type


class DocTypePrompt(_Strict):
    title: str
    # first ~300 characters of the note, patient details removed
    text_start: str


class DocTypeAnswer(_Strict):
    kind: Literal["HP", "CONSENT", "ANTICOAG_NOTE", "OTHER"]
    # exact words from text_start that show the kind, null for OTHER
    quote: str | None


# step b: consent signed


class ConsentPrompt(_Strict):
    text: str


class ConsentAnswer(_Strict):
    status: Literal["SIGNED", "NOT_SIGNED", "UNCLEAR"]
    quote: str | None


# step c: blood thinner mentioned only in a note


class NoteMedPrompt(_Strict):
    drug: str
    passage: str


class NoteMedAnswer(_Strict):
    currently_taking: Literal["YES", "NO", "UNCLEAR"]
    quote: str | None


# step d: anticoagulation plan


class Passage(_Strict):
    id: str
    text: str


class PlanPrompt(_Strict):
    drugs: list[str] = Field(min_length=1)
    passages: list[Passage]


class DrugPlan(_Strict):
    drug: str
    before_action: Literal["HOLD", "CONTINUE", "BRIDGE", "NOT_STATED"]
    before_timing: str | None
    before_quote: str | None
    after_action: Literal["RESUME", "CONTINUE", "HOLD", "NOT_STATED"]
    after_timing: str | None
    after_quote: str | None
    says_pending: bool
    pending_quote: str | None


class PlanAnswer(_Strict):
    plans: list[DrugPlan]
