from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import BaseModel

from triage.config import Settings
from triage.ingest import InvalidSubmission, ingest
from triage.llm.base import LLMFailed, LLMOk, LLMRequest
from triage.llm.fake import FakeLLMClient
from triage.schemas import PatientSubmission, TriageOutput


def _strip_nones(value: Any) -> Any:
    """Drop keys whose value is None; model_dump adds those for absent optional fields."""
    if isinstance(value, dict):
        return {k: _strip_nones(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_strip_nones(v) for v in value]
    return value


def test_all_seed_submissions_round_trip(seed_cases: list[dict[str, Any]]) -> None:
    assert len(seed_cases) == 50
    for case in seed_cases:
        result = ingest(case["submission"])
        assert _strip_nones(result.data) == _strip_nones(case["submission"]), case["case_id"]
        assert result.warnings == [], case["case_id"]


def test_all_seed_expected_outputs_parse(seed_cases: list[dict[str, Any]]) -> None:
    for case in seed_cases:
        TriageOutput.model_validate(case["expected_output"])


def test_leaf_values_are_not_coerced() -> None:
    sub = PatientSubmission.model_validate(
        {
            "procedure": {"procedure_risk": "VERY_HIGH", "procedure_date": 20260301},
            "vitals": [{"type": "blood_pressure", "systolic": "185", "diastolic": 111}],
            "medications": [{"name": "warfarin", "active": None}],
        }
    )
    assert sub.procedure is not None
    assert sub.procedure.procedure_risk == "VERY_HIGH"
    assert sub.procedure.procedure_date == 20260301
    assert sub.vitals[0].systolic == "185"
    assert sub.vitals[0].diastolic == 111
    assert sub.medications[0].active is None


def test_wrong_shapes_become_missing_with_warnings() -> None:
    result = ingest(
        {
            "procedure": "knee",
            "vitals": None,
            "labs": {"code": "CBC"},
            "documents": [{"type": "H&P"}, "stray text", 7],
            "surprise": 1,
        }
    )
    sub = result.submission
    assert sub.procedure is None
    assert sub.vitals == []
    assert sub.labs == []
    # Positions are kept so `documents[0]` still means the H&P.
    assert len(sub.documents) == 3
    assert sub.documents[0].type == "H&P"
    assert sub.documents[1].type is None
    assert any(w.startswith("procedure:") for w in result.warnings)
    assert any(w.startswith("labs:") for w in result.warnings)
    assert any(w.startswith("documents[1]") for w in result.warnings)
    assert any(w.startswith("documents[2]") for w in result.warnings)
    assert "surprise: unknown field (kept, not used)" in result.warnings


def test_unknown_nested_fields_are_kept_and_reported() -> None:
    result = ingest({"labs": [{"code": "CBC", "units": "x10^9/L"}]})
    assert result.data["labs"][0]["units"] == "x10^9/L"
    assert "labs[0].units: unknown field (kept, not used)" in result.warnings


@pytest.mark.parametrize("raw", [[], "not json", "[1, 2]", 5, None])
def test_non_object_packages_are_rejected(raw: object) -> None:
    with pytest.raises(InvalidSubmission):
        ingest(raw)


def test_json_string_and_model_inputs_are_accepted() -> None:
    payload = {"procedure": {"procedure_risk": "LOW"}}
    assert ingest(json.dumps(payload)).submission.procedure.procedure_risk == "LOW"  # type: ignore[union-attr]
    model = PatientSubmission.model_validate(payload)
    assert ingest(model).submission is model


def test_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRIAGE_MODEL_SMALL", "small-x")
    monkeypatch.setenv("TRIAGE_TEMPERATURE", "none")
    monkeypatch.setenv("TRIAGE_MAX_CONCURRENCY", "2")
    settings = Settings.from_env(model_medium="medium-y")
    assert settings.model_small == "small-x"
    assert settings.model_medium == "medium-y"
    assert settings.temperature is None
    assert settings.max_concurrency == 2


class _Answer(BaseModel):
    status: str


def _request(step: str = "consent") -> LLMRequest[_Answer]:
    return LLMRequest(step, "m", "v1", "instructions", "text", _Answer)


def test_fake_client_parses_and_records() -> None:
    client = FakeLLMClient({"consent": lambda req: {"status": "SIGNED"}})
    result = client.parse(_request())
    assert isinstance(result, LLMOk)
    assert result.value.status == "SIGNED"
    assert len(client.calls_for("consent")) == 1


@pytest.mark.parametrize(
    "handler",
    [
        lambda req: (_ for _ in ()).throw(TimeoutError("slow")),
        lambda req: "{not json",
        lambda req: {"wrong": "shape"},
    ],
)
def test_fake_client_failures_are_values_not_exceptions(handler: Any) -> None:
    result = FakeLLMClient({"consent": handler}).parse(_request())
    assert isinstance(result, LLMFailed)


def test_fake_client_without_handler_fails() -> None:
    assert isinstance(FakeLLMClient().parse(_request("other")), LLMFailed)
