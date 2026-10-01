"""the only file that talks to openai
strict json schema answers, store=False, sdk retries for rate limits and server errors, never raises
"""

from __future__ import annotations

import os
import threading
import time
from functools import cache
from typing import Any

from triage.config import Settings
from triage.llm.base import CallMeta, LLMFailed, LLMOk, LLMRequest, LLMResult, T


class OpenAIClient:
    def __init__(self, settings: Settings, sdk_client: Any | None = None) -> None:
        self.settings = settings
        # caps calls in flight across every case and thread, keeps batch runs under rate limits
        self._slots = threading.BoundedSemaphore(settings.max_concurrency)
        if sdk_client is None:
            from openai import OpenAI  # imported here so the rest of the package works without openai

            # the sdk retries timeouts, 429s and 5xx with backoff, it doesn't retry 400s
            sdk_client = OpenAI(timeout=settings.request_timeout_s, max_retries=settings.max_retries)
        self._sdk = sdk_client

    def parse(self, request: LLMRequest[T]) -> LLMResult[T]:
        meta = CallMeta(step=request.step, model=request.model, prompt_version=request.prompt_version)
        kwargs: dict[str, Any] = {
            "model": request.model,
            "instructions": request.instructions,
            "input": request.input_text,
            "text_format": request.output_type,
            "store": False,  # openai doesn't keep the request or answer
            "max_output_tokens": self.settings.max_output_tokens,
        }
        if self.settings.temperature is not None:
            kwargs["temperature"] = self.settings.temperature
        started = time.perf_counter()
        try:
            with self._slots:
                response = self._sdk.responses.parse(**kwargs)
        except Exception as exc:  # network, rate limit after retries, bad request, schema refusal by the sdk
            meta.latency_ms = (time.perf_counter() - started) * 1000
            return LLMFailed(f"{type(exc).__name__}: {str(exc)[:200]}", meta)
        meta.latency_ms = (time.perf_counter() - started) * 1000
        usage = getattr(response, "usage", None)
        meta.input_tokens = getattr(usage, "input_tokens", 0) or 0
        meta.output_tokens = getattr(usage, "output_tokens", 0) or 0
        if getattr(response, "status", "completed") != "completed":
            details = getattr(response, "incomplete_details", None)
            return LLMFailed(f"incomplete response: {getattr(details, 'reason', None)}", meta)
        refusal = _refusal(response)
        if refusal:
            return LLMFailed(f"refused: {refusal[:200]}", meta)
        parsed = getattr(response, "output_parsed", None)
        if not isinstance(parsed, request.output_type):
            return LLMFailed("no parsed answer in response", meta)
        return LLMOk(parsed, meta)


def _refusal(response: Any) -> str | None:
    for item in getattr(response, "output", None) or []:
        for content in getattr(item, "content", None) or []:
            if getattr(content, "type", None) == "refusal":
                return getattr(content, "refusal", "") or "refusal"
    return None


class UnavailableClient:
    """stands in when no llm can be used, every call fails so every free-text check stays cautious"""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def parse(self, request: LLMRequest[T]) -> LLMResult[T]:
        meta = CallMeta(step=request.step, model=request.model, prompt_version=request.prompt_version)
        return LLMFailed(self.reason, meta)


def default_client(settings: Settings) -> Any:
    # openai behind the answer cache, or an always-failing client when there's no key or no sdk
    # one client per settings and key, shared across cases so they share connections and the in-flight cap
    return _shared_client(settings, os.environ.get("OPENAI_API_KEY", ""))


@cache
def _shared_client(settings: Settings, api_key: str) -> Any:
    from triage.llm.cache import CachingClient

    if not api_key:
        return UnavailableClient("OPENAI_API_KEY is not set")
    try:
        client: Any = OpenAIClient(settings)
    except Exception as exc:
        return UnavailableClient(f"openai client unavailable: {type(exc).__name__}")
    return CachingClient(client, settings.cache_dir) if settings.cache_enabled else client
