"""saves each successful llm answer on disk, keyed by everything that could change it
same step + model + prompt version + answer schema + exact (redacted) input -> same answer, no new call
makes runs repeatable and lets evals re-run for free, failures are never cached
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from triage.llm.base import CallMeta, LLMOk, LLMRequest, LLMResult, T


def cache_key(request: LLMRequest[Any]) -> str:
    parts = {
        "step": request.step,
        "model": request.model,
        "prompt_version": request.prompt_version,
        "instructions": request.instructions,
        "input": request.input_text,
        "schema": request.output_type.model_json_schema(),
    }
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


class CachingClient:
    def __init__(self, inner: Any, directory: Path) -> None:
        self.inner = inner
        self.directory = Path(directory)

    def parse(self, request: LLMRequest[T]) -> LLMResult[T]:
        key = cache_key(request)
        path = self.directory / key[:2] / f"{key}.json"
        if path.exists():
            try:
                value = request.output_type.model_validate_json(path.read_text(encoding="utf-8"))
                meta = CallMeta(request.step, request.model, request.prompt_version, cache_hit=True)
                return LLMOk(value, meta)
            except (ValidationError, OSError):
                pass  # a broken cache file is ignored and replaced
        result = self.inner.parse(request)
        if isinstance(result, LLMOk):
            _write_atomic(path, result.value.model_dump_json())
        return result


def _write_atomic(path: Path, text: str) -> None:
    # write to a temp file then rename, so parallel runs never read half a file
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        out.write(text)
    os.replace(temp, path)
