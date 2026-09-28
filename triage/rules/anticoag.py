"""rule 3: every blood thinner the patient takes needs a plan for before and after surgery
an anticoagulant with active=null can't be judged, so it's reported as missing data instead
"""

from __future__ import annotations

from triage.normalize.values import show
from triage.rules.common import doc_label, excerpt, issue
from triage.schemas.findings import Findings, PlanFinding
from triage.schemas.normalized import NormalizedCase
from triage.schemas.output import TriageIssue

#checks if missing anticoagulant active, then appends all of the issues in a human readable way with plan_issue()
def check_anticoagulation(case: NormalizedCase, findings: Findings) -> list[TriageIssue]:
    issues: list[TriageIssue] = []
    for med in case.meds:
        if med.anticoagulant and med.active is None:
            issues.append(
                issue(
                    "MISSING_REQUIRED_DATA",
                    "Unknown anticoagulant active status",
                    f"medications[{med.index}]",
                    f"Medication {med.name_raw} has active={show(med.active_raw)}; cannot determine if currently taking",
                )
            )
    for plan in findings.plans:
        if not plan.passes:
            issues.append(_plan_issue(case, findings, plan))
    return issues

#explains an issue that was found in findings about anticoag
def _plan_issue(case: NormalizedCase, findings: Findings, plan: PlanFinding) -> TriageIssue:
    if plan.med_index is not None:
        # the name as written, plus the generic name when they differ, e.g. Xarelto (rivaroxaban, medications[1])
        written = case.meds[plan.med_index].name_raw
        same = written.strip().casefold() == plan.drug
        where = f"medications[{plan.med_index}]" if same else f"{plan.drug}, medications[{plan.med_index}]"
        taking = f"Active anticoagulant {written.strip() if written else plan.drug} ({where})"
    else:
        mention = next(m for m in findings.note_mentions if m.drug == plan.drug and m.doc_index == plan.mention_doc)
        doc = case.docs[mention.doc_index]
        # quoted from the original note, not the llm's (redacted) quote, so evidence matches the submission
        taking = (
            f"Anticoagulant {plan.drug} mentioned in documents[{doc.index}] (\"{excerpt(doc, mention.word)}\") "
            f"but not active in medications"
        )
    if plan.checked_doc is None:
        return issue(
            "ANTICOAGULATION_MANAGEMENT",
            "Missing perioperative anticoagulation plan",
            "documents",
            f"{taking} but no perioperative plan document found",
        )
    doc = case.docs[plan.checked_doc]
    reasons = list(plan.gaps)
    if plan.veto:
        reasons.insert(0, f"plan is not final (\"{plan.veto}\")")
    why = "; ".join(reasons) if reasons else "no clear before- and after-surgery management with timing"
    return issue(
        "ANTICOAGULATION_MANAGEMENT",
        "Missing perioperative anticoagulation plan",
        f"documents[{doc.index}]",
        f"{taking} but no clear perioperative plan: {why}. Checked {doc_label(doc)}: \"{excerpt(doc, plan.veto)}\"",
    )
