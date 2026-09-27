"""rule 4: acute safety exclusions from the most recent bp and temperature, pure numbers, never the llm"""

from __future__ import annotations

from triage.normalize.values import show
from triage.rules.common import issue
from triage.schemas.normalized import NormalizedCase
from triage.schemas.output import TriageIssue

SYSTOLIC_LIMIT = 180.0  # at or above
DIASTOLIC_LIMIT = 110.0  # at or above
TEMP_LIMIT_F = 100.4  # strictly above


def check_safety(case: NormalizedCase) -> list[TriageIssue]:
    return _check_blood_pressure(case) + _check_temperature(case)


def _check_blood_pressure(case: NormalizedCase) -> list[TriageIssue]:
    if not case.blood_pressures:
        return [
            issue(
                "MISSING_REQUIRED_DATA",
                "Missing latest blood pressure",
                "vitals",
                "No blood_pressure vital with valid date found",
            )
        ]
    bp = max(case.blood_pressures, key=lambda v: (v.taken_at, v.index))
    # the reading's date is included so the evidence points at one exact reading
    values = f"systolic={show(bp.systolic_raw)}, diastolic={show(bp.diastolic_raw)} on {bp.date_raw}"
    # a single number over its limit is enough, even if the other one is missing
    too_high = (bp.systolic is not None and bp.systolic >= SYSTOLIC_LIMIT) or (
        bp.diastolic is not None and bp.diastolic >= DIASTOLIC_LIMIT
    )
    if too_high:
        return [
            issue(
                "ACUTE_SAFETY_EXCLUSION",
                "Blood pressure meets exclusion threshold",
                f"vitals[{bp.index}]",
                f"latest BP {values}; threshold systolic>=180 or diastolic>=110",
            )
        ]
    if bp.systolic is None or bp.diastolic is None:
        return [
            issue(
                "MISSING_REQUIRED_DATA",
                "Missing latest blood pressure",
                f"vitals[{bp.index}]",
                f"latest BP {values}; both numbers are needed to rule out the threshold",
            )
        ]
    return []


def _check_temperature(case: NormalizedCase) -> list[TriageIssue]:
    if not case.temperatures:
        return [
            issue(
                "MISSING_REQUIRED_DATA",
                "Missing latest temperature",
                "vitals",
                "No temperature vital with valid date found",
            )
        ]
    temp = max(case.temperatures, key=lambda v: (v.taken_at, v.index))
    reading = f"{temp.field}={show(temp.raw)} on {temp.date_raw}"
    if temp.temp_f is None:
        return [
            issue(
                "MISSING_REQUIRED_DATA",
                "Missing latest temperature",
                f"vitals[{temp.index}]",
                f"latest temperature {reading} is not a usable temperature",
            )
        ]
    if temp.temp_f > TEMP_LIMIT_F:
        converted = f" ({temp.temp_f}°F)" if temp.field != "value_f" else ""
        return [
            issue(
                "ACUTE_SAFETY_EXCLUSION",
                "Temperature exceeds exclusion threshold",
                f"vitals[{temp.index}]",
                f"latest temperature {reading}{converted}; threshold is > 100.4",
            )
        ]
    return []
