"""steps 5 and 6: picks the decision, writes the explanation, and checks the finished output"""

from __future__ import annotations

import re
from typing import Any

from triage.schemas.output import Decision, TriageIssue, TriageOutput

READY_EXPLANATION = (
    "All required documentation, testing, anticoagulation planning, and safety checks are satisfied."
)

_SOURCE = re.compile(r"^(?P<base>[a-z_]+)(?:\[(?P<index>\d+)\])?(?:\.(?P<field>[a-z_]\w*))?$")
_LIST_BASES = {"vitals", "labs", "medications", "conditions", "documents"}
_OBJECT_BASES = {"patient", "procedure", "metadata"}


class OutputCheckError(AssertionError):
    """the output contradicts itself or the submission, this is a bug in our code"""


def decide(issues: list[TriageIssue]) -> Decision:
    # a safety issue beats everything, any other issue means follow-up, no issues means ready
    if any(i.category == "ACUTE_SAFETY_EXCLUSION" for i in issues):
        return "NOT_CLEARED"
    return "NEEDS_FOLLOW_UP" if issues else "READY"


def build_output(issues: list[TriageIssue]) -> TriageOutput:
    explanation = (
        " | ".join(f"{i.category}: {i.description}" for i in issues) if issues else READY_EXPLANATION
    )
    return TriageOutput(decision=decide(issues), issues=issues, explanation=explanation)


def check_output(output: TriageOutput, data: dict[str, Any]) -> None:
    # raises instead of letting an inconsistent answer out
    has_safety = any(i.category == "ACUTE_SAFETY_EXCLUSION" for i in output.issues)
    if output.decision == "READY" and output.issues:
        raise OutputCheckError("READY with issues")
    if output.decision == "NOT_CLEARED" and not has_safety:
        raise OutputCheckError("NOT_CLEARED without a safety issue")
    if output.decision == "NEEDS_FOLLOW_UP" and (not output.issues or has_safety):
        raise OutputCheckError("NEEDS_FOLLOW_UP needs issues and no safety issue")
    for issue in output.issues:
        if not source_exists(data, issue.evidence.source):
            raise OutputCheckError(f"evidence source {issue.evidence.source!r} not in submission")
        if not issue.evidence.details.strip():
            raise OutputCheckError(f"empty evidence details for {issue.description!r}")
    if output.explanation != build_output(output.issues).explanation:
        raise OutputCheckError("explanation doesn't match the issues")


def source_exists(data: dict[str, Any], source: str) -> bool:
    # a path like documents[2], labs, or procedure.procedure_date must point at something in the submission
    match = _SOURCE.match(source)
    if not match:
        return False
    base, index, field = match.group("base"), match.group("index"), match.group("field")
    if base in _LIST_BASES:
        items = data.get(base)
        if not isinstance(items, list):
            return False
        if index is None:
            return field is None
        if int(index) >= len(items):
            return False
        return field is None or (isinstance(items[int(index)], dict) and field in items[int(index)])
    if base in _OBJECT_BASES and index is None:
        obj = data.get(base)
        if field is None:
            return obj is not None
        # a missing object still counts, "procedure.procedure_date is null" is valid evidence
        return obj is None or isinstance(obj, dict)
    return False
