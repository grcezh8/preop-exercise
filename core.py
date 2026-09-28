"""what the evaluation scripts import, everything lives in the triage package"""

from __future__ import annotations

from pydantic import BaseModel

from triage.pipeline import triage_submission
from triage.schemas.input import PatientSubmission
from triage.schemas.output import (
    Decision,
    IssueCategory,
    TriageIssue,
    TriageIssueEvidence,
    TriageOutput,
)


class PreparedPatientCase(BaseModel):
    # one eval case: the submission and the expected output
    case_id: str
    submission: PatientSubmission
    expected_output: TriageOutput


__all__ = [
    "Decision",
    "IssueCategory",
    "PatientSubmission",
    "PreparedPatientCase",
    "TriageIssue",
    "TriageIssueEvidence",
    "TriageOutput",
    "triage_submission",
]
