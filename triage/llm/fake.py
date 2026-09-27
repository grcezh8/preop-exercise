"""Scripted stand-in for the OpenAI client, used by tests and offline evals.

Each step gets a handler that receives the request and returns one of:
- a model instance, dict, or JSON string: parsed into the step's output type
  (so a handler can return invalid data and exercise the schema check);
- an `LLMFailed`, or an exception: reported as a failed call.

Every request is recorded in `calls`, which the patient-detail test inspects.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from triage.llm.base import CallMeta, LLMFailed, LLMOk, LLMRequest, LLMResult, T

Handler = Callable[[LLMRequest[Any]], Any]


class FakeLLMClient:
    def __init__(self, handlers: dict[str, Handler] | None = None) -> None:
        self.handlers: dict[str, Handler] = dict(handlers or {})
        self.calls: list[LLMRequest[Any]] = []

    def parse(self, request: LLMRequest[T]) -> LLMResult[T]:
        self.calls.append(request)
        meta = CallMeta(
            step=request.step,
            model=request.model,
            prompt_version=request.prompt_version,
            attempts=1,
        )
        handler = self.handlers.get(request.step)
        if handler is None:
            return LLMFailed(f"no fake handler for step {request.step!r}", meta)
        try:
            raw = handler(request)
        except Exception as exc:  # scripted transport failure
            return LLMFailed(f"{type(exc).__name__}: {exc}", meta)
        if isinstance(raw, LLMFailed):
            return raw
        try:
            if isinstance(raw, BaseModel):
                raw = raw.model_dump()
            if isinstance(raw, str):
                value = request.output_type.model_validate_json(raw)
            else:
                value = request.output_type.model_validate(raw)
        except (ValidationError, json.JSONDecodeError) as exc:
            return LLMFailed(f"schema: {exc.__class__.__name__}", meta)
        return LLMOk(value, meta)

    def calls_for(self, step: str) -> list[LLMRequest[Any]]:
        return [call for call in self.calls if call.step == step]
