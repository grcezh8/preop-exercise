"""how every llm step asks its question: send, check the answer in code, retry once with the reason, log
an answer that fails its check is never used, the step falls back to its cautious answer
"""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from pydantic import BaseModel

from triage.config import Settings
from triage.llm import prompts
from triage.llm.base import CallMeta, LLMClient, LLMFailed, LLMRequest, T
from triage.llm.redact import Redactor
from triage.normalize.text import clean, find_first
from triage.vocab.doc_titles import HP_VARIANTS

# the anticoag plan is the one real judgment call, it gets the medium model, the rest get the small one
MEDIUM_STEPS = {"anticoag_plan"}
# shorter quotes can't show anything, e.g. "ok"
MIN_QUOTE_CHARS = 4

Check = Callable[[T], str | None]
I = TypeVar("I")
O = TypeVar("O")


@dataclass
class Asked(Generic[T]):
    value: T | None
    # why there's no usable answer: the call failed, or the answer failed its check twice
    reason: str | None = None


@dataclass
class Reader:
    client: LLMClient
    settings: Settings
    redact: Redactor
    calls: list[tuple[CallMeta, bool, str | None]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def ask(self, step: str, prompt: BaseModel, answer_type: type[T], check: Check[T]) -> Asked[T]:
        version, instructions = prompts.load(step)
        model = self.settings.model_medium if step in MEDIUM_STEPS else self.settings.model_small
        input_text = prompt.model_dump_json()
        problem: str | None = None
        for attempt in (1, 2):
            text = input_text if attempt == 1 else (
                f"{input_text}\n\nYour previous answer was rejected: {problem}. "
                "Answer again using only the text above, copying quotes exactly."
            )
            result = self.client.parse(LLMRequest(step, model, version, instructions, text, answer_type))
            if isinstance(result, LLMFailed):
                self._log(result.meta, False, result.reason)
                return Asked(None, result.reason)
            problem = check(result.value)
            self._log(result.meta, problem is None, problem)
            if problem is None:
                return Asked(result.value)
        return Asked(None, f"answer rejected twice: {problem}")

    def run_all(self, fn: Callable[[I], O], items: list[I]) -> list[O]:
        # runs independent llm calls at the same time, results keep the input order
        if len(items) <= 1:
            return [fn(item) for item in items]
        with ThreadPoolExecutor(max_workers=min(self.settings.max_concurrency, len(items))) as pool:
            return list(pool.map(fn, items))

    def _log(self, meta: CallMeta, ok: bool, reason: str | None) -> None:
        with self._lock:
            self.calls.append((meta, ok, reason))


# checks shared by the steps


def quote_found(quote: str | None, source: str) -> bool:
    # the quote must be copied from the exact text we sent, compared after the same cleanup on both sides
    if not quote:
        return False
    piece = clean(quote)
    return len(piece) >= MIN_QUOTE_CHARS and piece in clean(source)


def has_cue(text: str | None, cues: Iterable[str]) -> bool:
    if not text:
        return False
    cleaned = clean(text)
    for pattern in HP_VARIANTS:
        cleaned = re.sub(pattern, "h&p", cleaned)
    return find_first(tuple(cues), cleaned) is not None
