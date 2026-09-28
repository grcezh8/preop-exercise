from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.conftest import ROOT
from tests.factories import days_before_procedure, ready
from triage.config import Settings
from triage.ingest import InvalidSubmission
from triage.llm.fake import FakeLLMClient
from triage.pipeline import run_triage, triage_submission
from triage.render import OutputCheckError, build_output, check_output
from triage.rules.common import issue
from triage.schemas.output import TriageOutput

SETTINGS = Settings(audit_enabled=False, pattern_only=True)
DEFAULT = Settings(audit_enabled=False)
DISAGREEMENTS = json.loads((ROOT / "evals" / "known_oracle_disagreements.json").read_text())["cases"]
SEVERITY = {"READY": 0, "NEEDS_FOLLOW_UP": 1, "NOT_CLEARED": 2}


def test_seed_cases_match_expected_outputs(seed_cases: list[dict[str, Any]]) -> None:
    for case in seed_cases:
        out = run_triage(case["submission"], SETTINGS).output
        expected = case["expected_output"]
        assert out.decision == expected["decision"], case["case_id"]
        ours = sorted(i.category for i in out.issues)
        known = DISAGREEMENTS.get(case["case_id"], {})
        if known.get("field") == "issue categories":
            assert ours == sorted(known["ours"]), case["case_id"]
        else:
            assert ours == sorted(i["category"] for i in expected["issues"]), case["case_id"]


def test_seed_evidence_passes_harness_grounding_check(seed_cases: list[dict[str, Any]]) -> None:
    # the harness's own check that every issue cites a real value or excerpt from the submission
    import run_evals

    for case in seed_cases:
        out = triage_submission(case["submission"], settings=SETTINGS)
        assert run_evals._check_issues_value_grounding(case["submission"], out), case["case_id"]


def test_default_mode_never_approves_consent_from_wording_alone() -> None:
    # without an llm confirming it, "signed" wording can't pass the consent check
    out = triage_submission(ready(), settings=DEFAULT, llm=FakeLLMClient())
    assert out.decision == "NEEDS_FOLLOW_UP"
    assert [i.description for i in out.issues] == ["Surgical consent not clearly signed"]
    assert "could not be confirmed" in out.issues[0].evidence.details


def test_default_mode_never_reaches_ready_on_seed_cases(seed_cases: list[dict[str, Any]]) -> None:
    for case in seed_cases:
        assert triage_submission(case["submission"], settings=DEFAULT, llm=FakeLLMClient()).decision != "READY", case["case_id"]


def test_default_mode_still_finds_every_safety_issue(seed_cases: list[dict[str, Any]]) -> None:
    for case in seed_cases:
        if case["expected_output"]["decision"] == "NOT_CLEARED":
            assert triage_submission(case["submission"], settings=DEFAULT, llm=FakeLLMClient()).decision == "NOT_CLEARED"


def test_same_input_gives_identical_output(seed_cases: list[dict[str, Any]]) -> None:
    for case in seed_cases[:10]:
        first = run_triage(case["submission"], SETTINGS).output.model_dump_json()
        assert all(run_triage(case["submission"], SETTINGS).output.model_dump_json() == first for _ in range(3))


def test_audit_record_has_no_patient_details_or_note_text(tmp_path: Path) -> None:
    sub = ready()
    sub["documents"][1]["text"] = "Consent documented but unsigned; awaiting patient signature."
    run_triage(sub, Settings(audit_dir=tmp_path, pattern_only=True))
    written = (tmp_path / "case_test.json").read_text()
    record = json.loads(written)
    assert record["decision"] == "NEEDS_FOLLOW_UP"
    assert record["rules"][1]["issues"] == [["REQUIRED_DOCUMENTATION", "Surgical consent not clearly signed", "documents[1]"]]
    for secret in ("Rosalind", "Okonkwo", "MRN-4455667", "1950-05-05", "Ada Quill", "awaiting patient signature"):
        assert secret not in written


def test_audit_file_name_without_case_id_is_a_hash(tmp_path: Path) -> None:
    sub = ready()
    sub["procedure"]["case_id"] = None
    assert run_triage(sub, Settings(audit_dir=tmp_path)).audit.case_ref.startswith("sha256-")


def test_harness_entry_point_accepts_dict_and_json() -> None:
    assert triage_submission(ready(), model="any-model", settings=SETTINGS).decision == "READY"
    assert triage_submission(json.dumps(ready()), settings=SETTINGS).decision == "READY"


@pytest.mark.parametrize("raw", ["", "[]", 42])
def test_unreadable_package_raises(raw: object) -> None:
    with pytest.raises(InvalidSubmission):
        triage_submission(raw, settings=SETTINGS)  # type: ignore[arg-type]


def test_junk_everywhere_still_answers() -> None:
    out = triage_submission(
        {"procedure": 5, "vitals": "x", "labs": [None], "medications": [{"name": 3, "active": "yes"}], "documents": [7]},
        settings=SETTINGS,
    )
    assert out.decision == "NEEDS_FOLLOW_UP"


@pytest.mark.parametrize(
    "output",
    [
        TriageOutput(decision="READY", issues=[issue("REQUIRED_TESTING", "CBC missing", "labs", "x")], explanation=""),
        TriageOutput(decision="NOT_CLEARED", issues=[issue("REQUIRED_TESTING", "CBC missing", "labs", "x")], explanation=""),
        TriageOutput(decision="NEEDS_FOLLOW_UP", issues=[], explanation=""),
    ],
)
def test_output_check_catches_contradictions(output: TriageOutput) -> None:
    with pytest.raises(OutputCheckError):
        check_output(output, ready())


@pytest.mark.parametrize("source", ["documents[9]", "labs[0].nonexistent", "notes", "documents.text", ""])
def test_output_check_catches_bad_sources(source: str) -> None:
    out = build_output([issue("REQUIRED_TESTING", "CBC missing", source, "x")])
    with pytest.raises(OutputCheckError):
        check_output(out, ready())


# random-input checks


PROBLEMS = {
    "no_consent": lambda s: s["documents"].pop(1),
    "stale_hp": lambda s: s["documents"][0].update(date=days_before_procedure(40)),
    "no_cbc": lambda s: s["labs"].clear(),
    "fever": lambda s: s["vitals"][1].update(value_f=102.0),
    "high_bp": lambda s: s["vitals"][0].update(systolic=200),
    "anticoagulant": lambda s: s["medications"].append({"name": "warfarin", "active": True}),
    "no_date": lambda s: s["procedure"].update(procedure_date=None),
}


@settings(max_examples=150, deadline=None)
@given(
    base=st.sets(st.sampled_from(sorted(PROBLEMS))),
    extra=st.sampled_from(sorted(PROBLEMS)),
)
def test_adding_a_problem_never_makes_the_decision_less_severe(base: set[str], extra: str) -> None:
    sub = ready()
    for name in sorted(base):
        PROBLEMS[name](sub)
    before = triage_submission(sub, settings=SETTINGS).decision
    if extra not in base:
        PROBLEMS[extra](sub)
    after = triage_submission(sub, settings=SETTINGS).decision
    assert SEVERITY[after] >= SEVERITY[before]


@settings(max_examples=300, deadline=None)
@given(
    systolic=st.integers(60, 260),
    diastolic=st.integers(30, 160),
    temp=st.floats(95.0, 106.0, allow_nan=False).map(lambda t: round(t, 1)),
)
def test_safety_decision_follows_the_limits_exactly(systolic: int, diastolic: int, temp: float) -> None:
    sub = ready()
    sub["vitals"][0].update(systolic=systolic, diastolic=diastolic)
    sub["vitals"][1]["value_f"] = temp
    unsafe = systolic >= 180 or diastolic >= 110 or temp > 100.4
    assert (triage_submission(sub, settings=SETTINGS).decision == "NOT_CLEARED") is unsafe


@settings(max_examples=100, deadline=None)
@given(hp_days=st.integers(-10, 60), cbc_days=st.integers(-10, 60))
def test_ready_only_inside_both_windows(hp_days: int, cbc_days: int) -> None:
    sub = ready()
    sub["documents"][0]["date"] = days_before_procedure(hp_days)
    sub["labs"][0]["effective_at"] = days_before_procedure(cbc_days) + "T08:00:00Z"
    ready_expected = 0 <= hp_days <= 30 and 0 <= cbc_days <= 30
    assert (triage_submission(sub, settings=SETTINGS).decision == "READY") is ready_expected
