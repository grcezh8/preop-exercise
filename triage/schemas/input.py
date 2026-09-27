"""the input json as it comes in, and the defined shape of that data. 
doesn't check for misaligned/incorrect values yet so that
normalizing can do its job, and the errors can waterfall to ingestion. 
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

# a JSON leaf value, kept as-is so that pydantic's smart union keeps the exact input
# type ("185" stays a string, 185 stays an int), so nothing slips through
Scalar = str | int | float | bool | None

# declare which top level fields of json are objects vs lists
LIST_FIELDS = ("vitals", "labs", "medications", "conditions", "documents")
OBJECT_FIELDS = ("patient", "procedure", "metadata")


class _InputModel(BaseModel):
    # unknown fields are kept and reported as warnings by ingest 
    model_config = ConfigDict(extra="allow")


def _object_or_none(value: Any) -> Any:
    return value if isinstance(value, dict) else None


def _list_of_objects(value: Any) -> Any:
    # a non-list becomes an empty list and a non-object item becomes an empty
    # object, which keeps list positions stable
    if not isinstance(value, list):
        return []
    return [item if isinstance(item, dict) else {} for item in value]

class PatientName(_InputModel):
    given: Scalar = None
    family: Scalar = None


class PatientInfo(_InputModel):
    id: Scalar = None
    mrn: Scalar = None
    name: PatientName | None = None
    dob: Scalar = None
    sex: Scalar = None

    _name_object = field_validator("name", mode="before")(_object_or_none)


class ProcedureInfo(_InputModel):
    case_id: Scalar = None
    procedure_type: Scalar = None
    procedure_risk: Scalar = None
    procedure_date: Scalar = None
    is_elective: Scalar = None
    location: Scalar = None


class Vital(_InputModel):
    #one vital sign reading, blood pressure uses systolic/diastolic,
    # temperature uses value_f (or value_c, if a source sends celsius)

    type: Scalar = None
    systolic: Scalar = None
    diastolic: Scalar = None
    value_f: Scalar = None
    value_c: Scalar = None
    date: Scalar = None
    source: Scalar = None


class LabResult(_InputModel):
    id: Scalar = None
    code: Scalar = None
    display: Scalar = None
    effective_at: Scalar = None
    status: Scalar = None
    source: Scalar = None


class Medication(_InputModel):
    name: Scalar = None
    active: Scalar = None


class Condition(_InputModel):
    name: Scalar = None
    active: Scalar = None


class Document(_InputModel):
    doc_id: Scalar = None
    type: Scalar = None
    date: Scalar = None
    author: Scalar = None
    text: Scalar = None


class SubmissionMetadata(_InputModel):
    submission_received_at: Scalar = None
    source_system: Scalar = None


class PatientSubmission(_InputModel):
    # a single pre-op submission package

    patient: PatientInfo | None = None
    procedure: ProcedureInfo | None = None
    vitals: list[Vital] = []
    labs: list[LabResult] = []
    medications: list[Medication] = []
    conditions: list[Condition] = []
    documents: list[Document] = []
    metadata: SubmissionMetadata | None = None

    _objects = field_validator(*OBJECT_FIELDS, mode="before")(_object_or_none)
    _lists = field_validator(*LIST_FIELDS, mode="before")(_list_of_objects)
