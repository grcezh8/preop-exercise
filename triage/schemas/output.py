"""triage result format required by the task and the eval harness, only describes the shape - no rules yet
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Decision = Literal["READY", "NEEDS_FOLLOW_UP", "NOT_CLEARED"]

IssueCategory = Literal[
    "REQUIRED_DOCUMENTATION",
    "REQUIRED_TESTING",
    "ANTICOAGULATION_MANAGEMENT",
    "ACUTE_SAFETY_EXCLUSION",
    "MISSING_REQUIRED_DATA",
]


class TriageIssueEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    details: str


class TriageIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: IssueCategory
    description: str
    evidence: TriageIssueEvidence


class TriageOutput(BaseModel):
    decision: Decision
    issues: list[TriageIssue]
    explanation: str
