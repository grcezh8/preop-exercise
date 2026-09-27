"""the cleaned-up case the rules read, every value is parsed or None, never raw
each item keeps its list position (index) so evidence can point back at it
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict

Risk = Literal["LOW", "MODERATE", "HIGH"]
RequiredTest = Literal["CBC", "CMP"]
DocKind = Literal["HP", "VAGUE_HP", "CONSENT", "ANTICOAG_NOTE", "OTHER", "UNKNOWN"]
# how a document's kind was decided, kept for the audit trace
KindSource = Literal["rules", "fuzzy", "llm", "none"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class NormProcedure(_Frozen):
    date: dt.date | None
    risk: Risk | None
    # raw values, quoted in evidence when they're missing or invalid
    date_raw: object = None
    risk_raw: object = None


class NormBloodPressure(_Frozen):
    index: int
    taken_at: dt.datetime
    systolic: float | None
    diastolic: float | None
    systolic_raw: object = None
    diastolic_raw: object = None
    date_raw: object = None


class NormTemperature(_Frozen):
    index: int
    taken_at: dt.datetime
    temp_f: float | None
    # the field and value as received, e.g. ("value_f", 101.0), quoted in evidence
    field: str
    raw: object = None
    date_raw: object = None


class NormLab(_Frozen):
    index: int
    test: RequiredTest
    taken_at: dt.datetime
    status: str | None
    effective_raw: str


class LabEntry(_Frozen):
    # every lab on file as received, listed in evidence when a required test is missing
    index: int
    code_raw: object = None
    effective_raw: object = None


class NormMed(_Frozen):
    index: int
    name_raw: str
    # generic name when this is an anticoagulant, None for anything else
    anticoagulant: str | None
    # None when active is missing or not a true/false value
    active: bool | None
    active_raw: object = None


class NormDoc(_Frozen):
    index: int
    title_raw: str
    title_clean: str
    kind: DocKind
    kind_source: KindSource
    date: dt.date | None
    date_raw: object = None
    text_raw: str
    # cleaned lowercase text used for all matching, cut at max_doc_chars
    text_clean: str
    truncated: bool = False


class NormalizedCase(_Frozen):
    procedure: NormProcedure
    blood_pressures: list[NormBloodPressure]
    temperatures: list[NormTemperature]
    labs: list[NormLab]
    lab_entries: list[LabEntry]
    meds: list[NormMed]
    docs: list[NormDoc]
