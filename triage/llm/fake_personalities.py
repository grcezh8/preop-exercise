"""scripted llms that behave badly on purpose, used by tests and by the eval's --llm option
each one checks a different promise: a broken, down, or wrong-but-confident llm can never make a case READY
that shouldn't be, and can never hide a NOT_CLEARED
"""

from __future__ import annotations

import json
from typing import Any

from triage.llm.base import LLMRequest
from triage.llm.fake import FakeLLMClient

STEPS = ("doc_type", "consent", "note_meds", "anticoag_plan")


def outage() -> FakeLLMClient:
    # every call fails, like a network outage or a missing key
    def fail(request: LLMRequest[Any]) -> Any:
        raise TimeoutError("simulated timeout")

    return FakeLLMClient({step: fail for step in STEPS})


def garbage() -> FakeLLMClient:
    # every answer is broken json or the wrong shape
    return FakeLLMClient(
        {
            "doc_type": lambda r: "{not json",
            "consent": lambda r: {"status": "PROBABLY", "quote": None},
            "note_meds": lambda r: {"currently_taking": "YES"},
            "anticoag_plan": lambda r: {"plans": "all good"},
        }
    )


def cautious() -> FakeLLMClient:
    # always the most careful answer
    return FakeLLMClient(
        {
            "doc_type": lambda r: {"kind": "OTHER", "quote": None},
            "consent": lambda r: {"status": "UNCLEAR", "quote": None},
            "note_meds": lambda r: {"currently_taking": "UNCLEAR", "quote": None},
            "anticoag_plan": lambda r: {"plans": [_plan(d, None, None, empty=True) for d in _input(r)["drugs"]]},
        }
    )


def yes_man() -> FakeLLMClient:
    # always approves, and quotes real text from the input so the quote itself is found
    # this is the "valid json, confident, wrong" llm, only the code checks stand between it and a false READY
    def doc_type(r: LLMRequest[Any]) -> dict[str, Any]:
        text = _input(r)["text_start"]
        kind = "CONSENT" if "consent" in (_input(r)["title"] + text).lower() else "HP"
        return {"kind": kind, "quote": text[:80] or None}

    def consent(r: LLMRequest[Any]) -> dict[str, Any]:
        return {"status": "SIGNED", "quote": _input(r)["text"][:120] or None}

    def note_meds(r: LLMRequest[Any]) -> dict[str, Any]:
        return {"currently_taking": "NO", "quote": _input(r)["passage"][:120] or None}

    def plan(r: LLMRequest[Any]) -> dict[str, Any]:
        data = _input(r)
        first = data["passages"][0]["text"][:150] if data["passages"] else None
        return {"plans": [_plan(d, first, first) for d in data["drugs"]]}

    return FakeLLMClient({"doc_type": doc_type, "consent": consent, "note_meds": note_meds, "anticoag_plan": plan})


PERSONALITIES = {"outage": outage, "garbage": garbage, "cautious": cautious, "yes_man": yes_man}


def _input(request: LLMRequest[Any]) -> dict[str, Any]:
    # the prompt input is json, a retry appends the rejection reason after it
    return json.JSONDecoder().raw_decode(request.input_text)[0]


def _plan(drug: str, before: str | None, after: str | None, *, empty: bool = False) -> dict[str, Any]:
    return {
        "drug": drug,
        "before_action": "NOT_STATED" if empty else "HOLD",
        "before_timing": None if empty else "48 hours before surgery",
        "before_quote": before,
        "after_action": "NOT_STATED" if empty else "RESUME",
        "after_timing": None if empty else "24 hours after surgery",
        "after_quote": after,
        "says_pending": False,
        "pending_quote": None,
    }
