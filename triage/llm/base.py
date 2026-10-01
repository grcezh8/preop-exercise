"""the interface every LLM call goes through, should never raise into rules, 
returns LLMOk with parsed value or LLMFailed with a reason
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel) # generic type variable T constrained to be some subclass of pydantic's BaseModel

@dataclass(frozen=True)
class LLMRequest(Generic[T]):
    step: str  # e.g. "consent", used for routing, caching and the audit trace
    model: str
    prompt_version: str
    instructions: str  # system prompt: fixed per step and version
    input_text: str  # the (already redacted) data for this call
    output_type: type[T]


@dataclass
class CallMeta:
    step: str
    model: str
    prompt_version: str
    cache_hit: bool = False
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class LLMOk(Generic[T]):
    value: T
    meta: CallMeta


@dataclass(frozen=True)
class LLMFailed:
    reason: str
    meta: CallMeta


LLMResult = LLMOk[T] | LLMFailed


class LLMClient(Protocol):
    def parse(self, request: LLMRequest[T]) -> LLMResult[T]: ...
