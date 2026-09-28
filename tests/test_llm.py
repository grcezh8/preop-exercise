from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from pydantic import BaseModel

from triage.config import Settings
from triage.extract.reader import Reader, quote_found
from triage.llm.base import LLMFailed, LLMOk, LLMRequest
from triage.llm.cache import CachingClient
from triage.llm.fake import FakeLLMClient
from triage.llm.openai_client import OpenAIClient, UnavailableClient, default_client
from triage.llm.redact import Redactor
from triage.schemas.llm import ConsentAnswer, ConsentPrompt, DocTypePrompt


class Answer(BaseModel):
    status: str


def request(step: str = "consent", version: str = "v1") -> LLMRequest[Answer]:
    return LLMRequest(step, "m", version, "instructions", "input", Answer)


# openai adapter


def sdk_returning(response: Any) -> Mock:
    sdk = Mock()
    sdk.responses.parse.return_value = response
    return sdk


def test_openai_call_uses_strict_schema_and_store_false() -> None:
    sdk = sdk_returning(SimpleNamespace(status="completed", output=[], output_parsed=Answer(status="SIGNED"), usage=SimpleNamespace(input_tokens=12, output_tokens=3)))
    result = OpenAIClient(Settings(temperature=0.0), sdk).parse(request())
    assert isinstance(result, LLMOk)
    assert result.value.status == "SIGNED"
    assert (result.meta.input_tokens, result.meta.output_tokens) == (12, 3)
    kwargs = sdk.responses.parse.call_args.kwargs
    assert kwargs["text_format"] is Answer
    assert kwargs["store"] is False
    assert kwargs["instructions"] == "instructions"
    assert kwargs["input"] == "input"
    assert kwargs["temperature"] == 0.0


def test_temperature_left_out_when_unset() -> None:
    sdk = sdk_returning(SimpleNamespace(status="completed", output=[], output_parsed=Answer(status="x"), usage=None))
    OpenAIClient(Settings(temperature=None), sdk).parse(request())
    assert "temperature" not in sdk.responses.parse.call_args.kwargs


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (SimpleNamespace(status="incomplete", incomplete_details=SimpleNamespace(reason="max_output_tokens"), output=[], output_parsed=None, usage=None), "incomplete"),
        (SimpleNamespace(status="completed", output=[SimpleNamespace(content=[SimpleNamespace(type="refusal", refusal="can't help")])], output_parsed=None, usage=None), "refused"),
        (SimpleNamespace(status="completed", output=[], output_parsed=None, usage=None), "no parsed answer"),
    ],
)
def test_openai_bad_responses_become_failures(response: Any, reason: str) -> None:
    result = OpenAIClient(Settings(), sdk_returning(response)).parse(request())
    assert isinstance(result, LLMFailed)
    assert reason in result.reason


def test_openai_exceptions_become_failures() -> None:
    sdk = Mock()
    sdk.responses.parse.side_effect = TimeoutError("slow")
    result = OpenAIClient(Settings(), sdk).parse(request())
    assert isinstance(result, LLMFailed)
    assert result.reason.startswith("TimeoutError")


def test_no_key_means_every_call_fails() -> None:
    client = default_client(Settings())
    assert isinstance(client, UnavailableClient)
    assert isinstance(client.parse(request()), LLMFailed)


# cache


def test_cache_reuses_answers_and_never_caches_failures(tmp_path: Path) -> None:
    inner = FakeLLMClient({"consent": lambda r: {"status": "SIGNED"}})
    cached = CachingClient(inner, tmp_path)
    first, second = cached.parse(request()), cached.parse(request())
    assert isinstance(second, LLMOk) and second.meta.cache_hit and not first.meta.cache_hit
    assert len(inner.calls) == 1
    # a new prompt version is a new question
    cached.parse(request(version="v2"))
    assert len(inner.calls) == 2
    failing = CachingClient(FakeLLMClient(), tmp_path / "f")
    failing.parse(request())
    assert not any((tmp_path / "f").rglob("*.json"))


# reader


def reader(handlers: dict[str, Any]) -> tuple[Reader, FakeLLMClient]:
    client = FakeLLMClient(handlers)
    return Reader(client, Settings(), Redactor({})), client


def test_rejected_answer_is_retried_once_with_the_reason() -> None:
    answers = iter([{"status": "SIGNED", "quote": "made up"}, {"status": "SIGNED", "quote": "signed today"}])
    r, client = reader({"consent": lambda req: next(answers)})
    check = lambda a: None if quote_found(a.quote, "Consent signed today.") else "quote is not in the text"  # noqa: E731
    asked = r.ask("consent", ConsentPrompt(text="Consent signed today."), ConsentAnswer, check)
    assert asked.value is not None and asked.value.quote == "signed today"
    assert "rejected: quote is not in the text" in client.calls[1].input_text
    assert [ok for _, ok, _ in r.calls] == [False, True]


def test_answer_rejected_twice_is_not_used() -> None:
    r, _ = reader({"consent": lambda req: {"status": "SIGNED", "quote": "made up"}})
    asked = r.ask("consent", ConsentPrompt(text="x"), ConsentAnswer, lambda a: "quote is not in the text")
    assert asked.value is None
    assert "rejected twice" in (asked.reason or "")


def test_small_and_medium_models_are_routed_by_step() -> None:
    r, client = reader({})
    r.ask("consent", ConsentPrompt(text="x"), ConsentAnswer, lambda a: None)
    r.ask("anticoag_plan", ConsentPrompt(text="x"), ConsentAnswer, lambda a: None)
    assert [c.model for c in client.calls] == [Settings().model_small, Settings().model_medium]


def test_prompt_models_reject_extra_fields() -> None:
    with pytest.raises(ValueError):
        DocTypePrompt(title="t", text_start="s", mrn="MRN-1")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("quote", "found"),
    [("Consent signed today", True), ("consent  SIGNED today", True), ("signed yesterday", False), ("ok", False), (None, False), ("", False)],
)
def test_quote_found(quote: str | None, found: bool) -> None:
    assert quote_found(quote, "Consent signed today.") is found


# redaction


def test_redaction_removes_identifiers_and_keeps_clinical_text() -> None:
    data = {
        "patient": {"id": "p-77", "mrn": "MRN-3000012", "name": {"given": "Sophia", "family": "Simmons"}, "dob": "1948-01-02"},
        "procedure": {"case_id": "case_00012"},
        "documents": [{"doc_id": "d-1", "author": "Danielle Rivera, APRN"}],
    }
    redact = Redactor(data)
    text = (
        "Called Sophia Simmons (MRN-3000012, DOB 01/02/1948) at 555-201-3344 or s.simmons@mail.com. "
        "Seen by Rivera. SIMMONS agrees. Hold apixaban 48 hours before surgery (last dose 2026-03-10)."
    )
    out = redact(text)
    for secret in ("Sophia", "Simmons", "SIMMONS", "3000012", "01/02/1948", "555-201-3344", "s.simmons@mail.com", "Rivera"):
        assert secret not in out
    assert "Hold apixaban 48 hours before surgery (last dose 2026-03-10)." in out
