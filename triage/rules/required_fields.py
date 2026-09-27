"""rule 0: procedure fields other rules depend on
missing date skips the h&p and lab window checks, missing risk skips the lab checks, each reported once here
"""

from __future__ import annotations

from triage.normalize.values import show
from triage.rules.common import issue
from triage.schemas.normalized import NormalizedCase
from triage.schemas.output import TriageIssue


def check_required_fields(case: NormalizedCase) -> list[TriageIssue]:
    issues: list[TriageIssue] = []
    procedure = case.procedure
    if procedure.date is None:
        issues.append(
            issue(
                "MISSING_REQUIRED_DATA",
                "Missing procedure date",
                "procedure.procedure_date",
                _missing_details("procedure.procedure_date", procedure.date_raw, "a valid date"),
            )
        )
    if procedure.risk is None:
        issues.append(
            issue(
                "MISSING_REQUIRED_DATA",
                "Missing procedure risk",
                "procedure.procedure_risk",
                _missing_details("procedure.procedure_risk", procedure.risk_raw, "LOW, MODERATE or HIGH"),
            )
        )
    return issues


def _missing_details(path: str, raw: object, expected: str) -> str:
    # null reads like the expected outputs, anything else says what was there and what was expected
    if raw is None:
        return f"{path} is null"
    return f"{path} is {show(raw)}, which is not {expected}"
