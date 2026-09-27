"""step 2: turns the raw submission into the cleaned-up case the rules read"""

from __future__ import annotations

import re
from difflib import get_close_matches

from triage.normalize.doc_titles import classify_document
from triage.normalize.text import clean
from triage.normalize.values import (
    parse_bool,
    parse_date,
    parse_datetime,
    parse_number,
    parse_risk,
)
from triage.schemas.input import Document, LabResult, PatientSubmission, Vital
from triage.schemas.normalized import (
    LabEntry,
    NormalizedCase,
    NormBloodPressure,
    NormDoc,
    NormLab,
    NormMed,
    NormProcedure,
    NormTemperature,
    RequiredTest,
)
from triage.vocab.anticoagulants import NAME_TO_GENERIC
from triage.vocab.labs import LAB_CODES, LAB_DISPLAY_PHRASES

BP_TYPES = {"blood_pressure", "blood pressure", "bp"}
TEMP_TYPES = {"temperature", "temp", "body_temperature", "body temperature"}
# a value_f below this is almost certainly celsius typed into the wrong field, treated as unknown
MIN_PLAUSIBLE_F = 80.0
# typos allowed when matching medication names, e.g. "apixiban"
MED_FUZZY_MIN_RATIO = 0.85
MED_FUZZY_MIN_LENGTH = 6


def normalize(submission: PatientSubmission, *, max_doc_chars: int) -> NormalizedCase:
    procedure = submission.procedure
    return NormalizedCase(
        procedure=NormProcedure(
            date=parse_date(procedure.procedure_date) if procedure else None,
            risk=parse_risk(procedure.procedure_risk) if procedure else None,
            date_raw=procedure.procedure_date if procedure else None,
            risk_raw=procedure.procedure_risk if procedure else None,
        ),
        blood_pressures=[
            bp for i, v in enumerate(submission.vitals) if (bp := _blood_pressure(i, v))
        ],
        temperatures=[
            t for i, v in enumerate(submission.vitals) if (t := _temperature(i, v))
        ],
        labs=[lab for i, raw in enumerate(submission.labs) if (lab := _lab(i, raw))],
        lab_entries=[
            LabEntry(index=i, code_raw=raw.code, effective_raw=raw.effective_at)
            for i, raw in enumerate(submission.labs)
        ],
        meds=[
            NormMed(
                index=i,
                name_raw=med.name if isinstance(med.name, str) else "",
                anticoagulant=match_anticoagulant(med.name),
                active=parse_bool(med.active),
                active_raw=med.active,
            )
            for i, med in enumerate(submission.medications)
        ],
        docs=[_document(i, doc, max_doc_chars) for i, doc in enumerate(submission.documents)],
    )


def match_anticoagulant(name: object) -> str | None:
    # generic name if any word of the medication name is a known anticoagulant, e.g. "Eliquis 5 mg tablet"
    found = find_anticoagulants(clean(name))
    return found[0][0] if found else None


def find_anticoagulants(text_clean: str) -> list[tuple[str, str]]:
    # every (generic name, word as written) in already-cleaned text, exact matches before typo matches
    words = re.findall(r"[a-z]+", text_clean)
    exact = [(NAME_TO_GENERIC[w], w) for w in words if w in NAME_TO_GENERIC]
    fuzzy = [
        (NAME_TO_GENERIC[close[0]], w)
        for w in dict.fromkeys(words)
        if len(w) >= MED_FUZZY_MIN_LENGTH
        and w not in NAME_TO_GENERIC
        and (close := get_close_matches(w, NAME_TO_GENERIC, n=1, cutoff=MED_FUZZY_MIN_RATIO))
    ]
    return exact + fuzzy


def _blood_pressure(index: int, vital: Vital) -> NormBloodPressure | None:
    # readings without a valid date are dropped, "most recent" can't be judged for them
    taken_at = parse_datetime(vital.date)
    if clean(vital.type) not in BP_TYPES or taken_at is None:
        return None
    return NormBloodPressure(
        index=index,
        taken_at=taken_at,
        systolic=_positive(parse_number(vital.systolic)),
        diastolic=_positive(parse_number(vital.diastolic)),
        systolic_raw=vital.systolic,
        diastolic_raw=vital.diastolic,
        date_raw=vital.date,
    )


def _temperature(index: int, vital: Vital) -> NormTemperature | None:
    taken_at = parse_datetime(vital.date)
    if clean(vital.type) not in TEMP_TYPES or taken_at is None:
        return None
    if vital.value_f is not None:
        value = parse_number(vital.value_f)
        temp_f = value if value is not None and value >= MIN_PLAUSIBLE_F else None
        return NormTemperature(index=index, taken_at=taken_at, temp_f=temp_f, field="value_f", raw=vital.value_f, date_raw=vital.date)
    celsius = parse_number(vital.value_c)
    return NormTemperature(
        index=index,
        taken_at=taken_at,
        temp_f=round(celsius * 9 / 5 + 32, 2) if celsius is not None else None,
        field="value_c",
        raw=vital.value_c,
        date_raw=vital.date,
    )


def _lab(index: int, lab: LabResult) -> NormLab | None:
    # only cbc and cmp results with a valid date are kept, nothing else is needed by the policy
    test = _required_test(lab)
    taken_at = parse_datetime(lab.effective_at)
    if test is None or taken_at is None:
        return None
    return NormLab(
        index=index,
        test=test,
        taken_at=taken_at,
        status=clean(lab.status) or None,
        effective_raw=str(lab.effective_at),
    )


def _required_test(lab: LabResult) -> RequiredTest | None:
    code = re.sub(r"\s+", "", clean(lab.code)).upper()
    if code in LAB_CODES:
        return LAB_CODES[code]  # type: ignore[return-value]
    display = clean(lab.display)
    for phrase, test in LAB_DISPLAY_PHRASES.items():
        if phrase in display:
            return test  # type: ignore[return-value]
    return None


def _document(index: int, doc: Document, max_doc_chars: int) -> NormDoc:
    text_raw = doc.text if isinstance(doc.text, str) else ""
    text_clean = clean(text_raw)
    kind, source = classify_document(doc.type, text_clean[:max_doc_chars])
    return NormDoc(
        index=index,
        title_raw=doc.type if isinstance(doc.type, str) else "",
        title_clean=clean(doc.type),
        kind=kind,
        kind_source=source,
        date=parse_date(doc.date),
        date_raw=doc.date,
        text_raw=text_raw,
        text_clean=text_clean[:max_doc_chars],
        truncated=len(text_clean) > max_doc_chars,
    )


def _positive(value: float | None) -> float | None:
    return value if value is not None and value > 0 else None
