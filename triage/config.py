"""runtime settings, read from environment variables prefixed with TRIAGE_"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

ENV_PREFIX = "TRIAGE_"
DEFAULT_MEDIUM_MODEL = "gpt-4.1-mini"
DEFAULT_SMALL_MODEL = "gpt-4.1-nano"


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    # small model: document type, consent, blood thinners mentioned in notes
    model_small: str = DEFAULT_SMALL_MODEL
    # medium model: anticoagulation plan, the harness `--model` flag overrides it
    model_medium: str = DEFAULT_MEDIUM_MODEL
    # sent only when set, some reasoning models reject a temperature parameter
    temperature: float | None = 0.0

    request_timeout_s: float = 30.0
    max_retries: int = 3
    max_concurrency: int = 8
    max_output_tokens: int = 800

    # longest document text we process, longer text is cut and marked truncated
    max_doc_chars: int = 20_000
    # characters kept on each side of a keyword when cutting passages for the LLM
    snippet_radius: int = 250

    cache_enabled: bool = True
    cache_dir: Path = Path(".triage_cache")
    audit_enabled: bool = True
    audit_dir: Path = Path("data/audit")

    @classmethod
    def from_env(cls, **overrides: object) -> Settings:
        values: dict[str, object] = {}
        for name in cls.model_fields:
            raw = os.environ.get(ENV_PREFIX + name.upper())
            if raw is not None:
                values[name] = None if raw.lower() in ("", "none") else raw
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls.model_validate(values)
