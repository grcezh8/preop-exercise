"""accepts the raw package, checks data to see if anything looks odd
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from triage.schemas.input import LIST_FIELDS, OBJECT_FIELDS, PatientSubmission

class InvalidSubmission(ValueError):
    """the package can't be read as a submission at all"""

@dataclass
class IngestResult:
    submission: PatientSubmission
    # the package as plain JSON data
    data: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


def ingest(raw: object) -> IngestResult:
    if isinstance(raw, PatientSubmission):
        submission = raw
    else:
        if isinstance(raw, (str, bytes)):
            try:
                raw = json.loads(raw) 
            except json.JSONDecodeError as exc:
                raise InvalidSubmission(f"not valid JSON: {exc.msg}") from exc # checks if parsable json
        if not isinstance(raw, dict):
            raise InvalidSubmission(f"expected a JSON object, got {type(raw).__name__}") # checks if json object
        warnings = _shape_warnings(raw) 
        submission = PatientSubmission.model_validate(raw) # builds patientsubmission object
        return IngestResult(
            submission, submission.model_dump(), warnings + _unknown_field_warnings(submission)
        )
    return IngestResult(submission, submission.model_dump(), _unknown_field_warnings(submission))


# walks through raw dict before pydantic parsing checking with isinstance to check datatypes
def _shape_warnings(raw: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for name in OBJECT_FIELDS:
        value = raw.get(name)
        if value is not None and not isinstance(value, dict):
            warnings.append(f"{name}: expected an object, got {type(value).__name__}; treated as missing")
    for name in LIST_FIELDS:
        value = raw.get(name)
        if value is None:
            continue
        if not isinstance(value, list):
            warnings.append(f"{name}: expected a list, got {type(value).__name__}; treated as empty")
            continue
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                warnings.append(f"{name}[{index}]: expected an object, got {type(item).__name__}; treated as empty")
    return warnings


# walks through patientsubmission (by input) looking at fields pydantic didn't recognize
def _unknown_field_warnings(submission: PatientSubmission) -> list[str]:
    warnings: list[str] = []

    def visit(model: BaseModel | None, path: str) -> None:
        if model is None:
            return
        for key in model.model_extra or {}:
            warnings.append(f"{path}{key}: unknown field (kept, not used)")
        for name in type(model).model_fields:
            value = getattr(model, name)
            if isinstance(value, BaseModel):
                visit(value, f"{path}{name}.")
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    if isinstance(item, BaseModel):
                        visit(item, f"{path}{name}[{index}].")

    visit(submission, "")
    return warnings
