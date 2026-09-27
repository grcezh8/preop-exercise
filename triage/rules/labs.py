"""rule 2: required tests by procedure risk, only the most recent result of each test is judged"""

from __future__ import annotations

from triage.normalize.values import show
from triage.rules.common import issue, on_file, window_details
from triage.schemas.normalized import NormalizedCase, RequiredTest, Risk
from triage.schemas.output import TriageIssue

# risk -> (test, window in days)
REQUIRED_TESTS: dict[Risk, tuple[tuple[RequiredTest, int], ...]] = {
    "LOW": (("CBC", 30),),
    "MODERATE": (("CBC", 30),),
    "HIGH": (("CBC", 14), ("CMP", 14)),
}


def check_labs(case: NormalizedCase) -> list[TriageIssue]:
    risk = case.procedure.risk
    if risk is None:
        return []  # reported once by rule 0
    issues: list[TriageIssue] = []
    for test, window in REQUIRED_TESTS[risk]:
        results = [lab for lab in case.labs if lab.test == test]
        if not results:
            issues.append(
                issue(
                    "REQUIRED_TESTING",
                    f"{test} missing",
                    "labs",
                    f"No {test} result with valid effective_at found for procedure_risk {risk}"
                    + on_file([f"{show(e.code_raw)} {e.effective_raw}" for e in case.lab_entries]),
                )
            )
            continue
        latest = max(results, key=lambda lab: (lab.taken_at, lab.index))
        source = f"labs[{latest.index}]"
        procedure_date = case.procedure.date
        if procedure_date is not None:
            days = (procedure_date - latest.taken_at.date()).days
            if not 0 <= days <= window:
                issues.append(
                    issue(
                        "REQUIRED_TESTING",
                        f"{test} outside {window}-day window for {risk} risk procedure",
                        source,
                        window_details(f"{test} effective_at", latest.effective_raw, case.procedure.date_raw, days, window),
                    )
                )
                continue
        if latest.status != "final":
            issues.append(
                issue(
                    "REQUIRED_TESTING",
                    f"{test} result not final",
                    source,
                    f"Most recent {test} (effective_at {latest.effective_raw}) has status {show(latest.status)}; only final results count",
                )
            )
    return issues
