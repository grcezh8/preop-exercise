"""each llm step end to end with a scripted llm: good answers are used, wrong or unbacked answers are not"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import pytest

from tests.conftest import load_seed_cases
from tests.factories import ready
from triage.config import Settings
from triage.llm.base import LLMRequest
from triage.llm.fake import FakeLLMClient
from triage.llm.fake_personalities import PERSONALITIES, yes_man
from triage.pipeline import run_triage
from triage.schemas.output import TriageOutput

SETTINGS = Settings(audit_enabled=False)
FULL_PLAN = "Hold apixaban 48 hours before surgery. Resume apixaban 24 hours after surgery if hemostasis is adequate."


def data(request: LLMRequest[Any]) -> dict[str, Any]:
    return json.JSONDecoder().raw_decode(request.input_text)[0]


def signed_consent(request: LLMRequest[Any]) -> dict[str, Any]:
    text = data(request)["text"]
    return {"status": "SIGNED", "quote": text}


def plan_answer(before: str | None, after: str | None, drug: str = "apixaban", **extra: Any) -> Callable[[Any], dict]:
    def answer(request: LLMRequest[Any]) -> dict[str, Any]:
        entry = {
            "drug": drug, "before_action": "HOLD", "before_timing": "48 hours before", "before_quote": before,
            "after_action": "RESUME", "after_timing": "24 hours after", "after_quote": after,
            "says_pending": False, "pending_quote": None,
        }
        entry.update(extra)
        return {"plans": [entry]}

    return answer


def triage(sub: dict[str, Any], **handlers: Any) -> tuple[TriageOutput, FakeLLMClient]:
    client = FakeLLMClient({"consent": signed_consent, **handlers})
    return run_triage(sub, SETTINGS, client).output, client


def with_plan(text: str = FULL_PLAN, med: str = "apixaban") -> dict[str, Any]:
    sub = ready()
    sub["medications"].append({"name": med, "active": True})
    sub["documents"].append({"type": "Perioperative Medication Plan", "date": "2026-03-03", "text": text})
    return sub


# step b: consent


def test_llm_confirmed_consent_makes_ready() -> None:
    out, client = triage(ready())
    assert out.decision == "READY"
    assert len(client.calls_for("consent")) == 1


def test_consent_without_signature_keyword_can_be_confirmed() -> None:
    sub = ready()
    sub["documents"][1]["text"] = "Patient completed the surgical consent via DocuSign on 2026-03-06."
    out, _ = triage(sub, consent=lambda r: {"status": "SIGNED", "quote": "completed the surgical consent via DocuSign"})
    assert out.decision == "READY"


def test_signed_answer_without_signature_wording_is_rejected() -> None:
    sub = ready()
    sub["documents"][1]["text"] = "Consent discussed with patient; questions answered."
    out, client = triage(sub, consent=lambda r: {"status": "SIGNED", "quote": "questions answered"})
    assert out.decision == "NEEDS_FOLLOW_UP"
    assert len(client.calls_for("consent")) == 2  # retried once, then not used


def test_python_block_means_llm_is_not_asked() -> None:
    sub = ready()
    sub["documents"][1]["text"] = "Consent documented but unsigned; awaiting patient signature."
    out, client = triage(sub)
    assert out.decision == "NEEDS_FOLLOW_UP"
    assert client.calls_for("consent") == []


def test_llm_saying_not_signed_is_believed_and_flagged() -> None:
    out, _ = triage(ready(), consent=lambda r: {"status": "NOT_SIGNED", "quote": "Consent obtained"})
    assert out.decision == "NEEDS_FOLLOW_UP"
    assert "disagree" in out.issues[0].evidence.details


# step a: document type


@pytest.mark.parametrize("title", ["PAT Note", "HP", "Hx & Px", "History and Physcal"])
def test_llm_confirms_unusual_hp_titles(title: str) -> None:
    sub = ready()
    sub["documents"][0].update(type=title, text="History and physical examination completed for planned surgery.")
    out, _ = triage(sub, doc_type=lambda r: {"kind": "HP", "quote": "History and physical examination completed"})
    assert out.decision == "READY"


def test_hp_answer_needs_a_real_quote_about_history_and_exam() -> None:
    sub = ready()
    sub["documents"][0].update(type="PAT Note", text="Gait training session; tolerated well.")
    out, _ = triage(sub, doc_type=lambda r: {"kind": "HP", "quote": "Gait training session"})
    assert [i.description for i in out.issues] == ["History and Physical document missing"]


def test_hp_answer_with_made_up_quote_is_rejected() -> None:
    sub = ready()
    sub["documents"][0].update(type="PAT Note", text="Seen in clinic.")
    out, _ = triage(sub, doc_type=lambda r: {"kind": "HP", "quote": "History and physical completed"})
    assert [i.description for i in out.issues] == ["History and Physical document missing"]


# step c: blood thinner only in notes


def test_stopped_blood_thinner_needs_no_plan() -> None:
    sub = ready()
    sub["documents"].append({"type": "Pre-op Nursing Intake", "date": "2026-03-03", "text": "Warfarin was stopped in 2023 and not restarted."})
    out, _ = triage(sub, note_meds=lambda r: {"currently_taking": "NO", "quote": "Warfarin was stopped in 2023"})
    assert out.decision == "READY"


def test_not_taking_answer_needs_stopped_wording() -> None:
    sub = ready()
    sub["documents"].append({"type": "Pre-op Nursing Intake", "date": "2026-03-03", "text": "Patient continues Coumadin 5 mg daily."})
    out, _ = triage(sub, note_meds=lambda r: {"currently_taking": "NO", "quote": "Patient continues Coumadin 5 mg daily."})
    assert [i.description for i in out.issues] == ["Missing perioperative anticoagulation plan"]


# step d: anticoag plan


def test_complete_plan_passes() -> None:
    out, _ = triage(with_plan(), anticoag_plan=plan_answer("Hold apixaban 48 hours before surgery.", "Resume apixaban 24 hours after surgery"))
    assert out.decision == "READY"


@pytest.mark.parametrize(
    ("answer", "gap"),
    [
        (plan_answer("Hold apixaban 48 hours before surgery.", None, after_action="NOT_STATED", after_timing=None), "no after-surgery action"),
        (plan_answer("Hold apixaban 48 hours before surgery.", "Resume apixaban 24 hours after surgery", after_timing=None), "no after-surgery timing"),
        (plan_answer("Hold apixaban 48 hours before surgery.", "Hold apixaban 48 hours before surgery."), "after-surgery quote doesn't show"),
        (plan_answer("Hold apixaban 48 hours before surgery.", "Resume apixaban 24 hours after surgery", says_pending=True), "pending"),
    ],
)
def test_incomplete_plan_answers_fail_with_the_reason(answer: Any, gap: str) -> None:
    out, _ = triage(with_plan(), anticoag_plan=answer)
    assert out.decision == "NEEDS_FOLLOW_UP"
    assert gap in out.issues[0].evidence.details


def test_plan_quotes_must_name_the_drug() -> None:
    # the note is a warfarin plan, warfarin isn't on the med list so it needs a plan too, and gets one
    text = "Hold warfarin 5 days before surgery. Resume warfarin 24 hours after surgery."

    def answer(request: LLMRequest[Any]) -> dict[str, Any]:
        both = [plan_answer("Hold warfarin 5 days before surgery.", "Resume warfarin 24 hours after surgery", drug=d)(request)["plans"][0] for d in data(request)["drugs"]]
        return {"plans": both}

    out, _ = triage(with_plan(text), anticoag_plan=answer)
    assert [i.description for i in out.issues] == ["Missing perioperative anticoagulation plan"]
    assert "don't name apixaban" in out.issues[0].evidence.details


def test_made_up_plan_quote_is_rejected() -> None:
    out, client = triage(with_plan("Apixaban noted."), anticoag_plan=plan_answer("Hold apixaban 48 hours before surgery.", "Resume apixaban 24 hours after surgery"))
    assert out.decision == "NEEDS_FOLLOW_UP"
    assert len(client.calls_for("anticoag_plan")) == 2


def test_answer_about_a_drug_we_did_not_ask_about_is_rejected() -> None:
    out, _ = triage(with_plan(), anticoag_plan=plan_answer("Hold apixaban 48 hours before surgery.", "Resume apixaban 24 hours after surgery", drug="warfarin"))
    assert "plan could not be read" in out.issues[0].evidence.details


def test_python_pending_veto_beats_the_llm() -> None:
    text = FULL_PLAN + " Final plan pending cardiology input."
    out, _ = triage(with_plan(text), anticoag_plan=plan_answer("Hold apixaban 48 hours before surgery.", "Resume apixaban 24 hours after surgery"))
    assert out.decision == "NEEDS_FOLLOW_UP"
    assert "pending" in out.issues[0].evidence.details


# failures and bad llms


@pytest.mark.parametrize("personality", sorted(PERSONALITIES))
def test_bad_llms_never_make_seed_or_scenario_cases_less_safe(personality: str) -> None:
    rows = load_seed_cases() + [json.loads(line) for line in _scenario_lines()]
    for row in rows:
        out = run_triage(row["submission"], SETTINGS, PERSONALITIES[personality]()).output
        expected = row["expected_output"]["decision"]
        if expected != "READY":
            assert out.decision != "READY", (personality, row["case_id"])
        if expected == "NOT_CLEARED":
            assert out.decision == "NOT_CLEARED", (personality, row["case_id"])


def test_audit_records_each_llm_call() -> None:
    run = run_triage(with_plan(), SETTINGS, FakeLLMClient())
    steps = [c.step for c in run.audit.llm_calls]
    assert steps == ["consent", "anticoag_plan"]
    assert all(not c.ok for c in run.audit.llm_calls)


# patient details


def identifiers(row: dict[str, Any]) -> list[str]:
    sub = row["submission"]
    patient = sub.get("patient") or {}
    name = patient.get("name") or {}
    found = [name.get("given"), name.get("family"), patient.get("mrn"), patient.get("dob"), patient.get("id"), (sub.get("procedure") or {}).get("case_id")]
    for doc in sub.get("documents") or []:
        found.append(doc.get("doc_id"))
        author = (doc.get("author") or "").split(",")[0]
        found += [p for p in author.split() if len(p.strip(".")) >= 3]
    return [f for f in found if isinstance(f, str) and len(f) >= 3]


def test_no_patient_details_reach_any_prompt() -> None:
    rows = load_seed_cases() + [json.loads(line) for line in _scenario_lines()]
    checked = 0
    for row in rows:
        client = yes_man()
        run_triage(row["submission"], SETTINGS, client)
        secrets = identifiers(row)
        for call in client.calls:
            # the fixed instructions hold no patient data, only the input is checked
            sent = call.input_text
            for secret in secrets:
                assert not re.search(rf"(?<!\w){re.escape(secret)}(?!\w)", sent, re.IGNORECASE), (row["case_id"], call.step, secret)
            checked += 1
    assert checked > 50


def _scenario_lines() -> list[str]:
    from evals.build_cases import OUT_PATH, main

    main()
    return [line for line in OUT_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_plan_quote_without_drug_name_counts_when_its_passage_names_only_that_drug() -> None:
    text = "Enoxaparin: last dose 24 h before surgery; resume 12 h post-op."
    out, _ = triage(with_plan(text, med="enoxaparin"), anticoag_plan=plan_answer("last dose 24 h before surgery", "resume 12 h post-op", drug="enoxaparin"))
    assert out.decision == "READY"


def test_plan_quote_without_drug_name_fails_when_its_passage_names_two_drugs() -> None:
    sub = with_plan("Apixaban and enoxaparin noted. Last dose 24 h before surgery; resume 12 h post-op.")
    sub["medications"].append({"name": "enoxaparin", "active": True})

    def answer(request: LLMRequest[Any]) -> dict[str, Any]:
        return {"plans": [plan_answer("Last dose 24 h before surgery", "resume 12 h post-op", drug=d)(request)["plans"][0] for d in data(request)["drugs"]]}

    out, _ = triage(sub, anticoag_plan=answer)
    assert [i.description for i in out.issues] == ["Missing perioperative anticoagulation plan"] * 2
    assert all("don't name" in i.evidence.details for i in out.issues)
