from __future__ import annotations

import pytest

from evals.build_cases import build_row, check_label, load_seeds
from evals.labeled import CONSENT, DOC_TYPE, NOTE_MEDS, PLAN
from evals.mutate import append, apply_edits, delete, set_
from evals.scenarios import SCENARIOS, Scenario


def test_every_scenario_builds_and_its_label_is_consistent() -> None:
    seeds = load_seeds()
    ids = [s.id for s in SCENARIOS]
    assert len(ids) == len(set(ids))
    for scenario in SCENARIOS:
        row = build_row(scenario, seeds)
        assert row["submission"] != seeds[scenario.seed]["submission"], f"{scenario.id} changes nothing"


def test_bad_label_is_rejected() -> None:
    with pytest.raises(ValueError):
        check_label(Scenario("x", "g", "case_00012", [], "READY", [("REQUIRED_TESTING", "CBC missing")], "why"))


def test_edits() -> None:
    base = {"a": [{"b": 1}, {"b": 2}], "c": {"d": None}}
    out = apply_edits(base, [set_("a[1].b", 5), delete("a[0]"), append("a", {"b": 9}), set_("c.d", "x")])
    assert out == {"a": [{"b": 5}, {"b": 9}], "c": {"d": "x"}}
    assert base["a"][0] == {"b": 1}  # the seed is never changed
    with pytest.raises(IndexError):
        apply_edits(base, [set_("a[7].b", 1)])


def test_labeled_sets_use_known_answers() -> None:
    assert {kind for _, _, kind in DOC_TYPE} <= {"HP", "CONSENT", "ANTICOAG_NOTE", "OTHER"}
    assert {status for _, status in CONSENT} <= {"SIGNED", "NOT_SIGNED", "UNCLEAR"}
    assert {taking for _, _, taking in NOTE_MEDS} <= {"YES", "NO", "UNCLEAR"}
    assert any(complete for _, _, complete, _ in PLAN) and not all(complete for _, _, complete, _ in PLAN)
