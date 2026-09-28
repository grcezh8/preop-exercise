"""loads the versioned system prompt for each llm step, the version goes into the cache key and the audit trace"""

from __future__ import annotations

from functools import cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent

# step -> prompt version in use, bump the version and add a new file to change a prompt
VERSIONS: dict[str, str] = {
    "doc_type": "v1",
    "consent": "v1",
    "note_meds": "v1",
    "anticoag_plan": "v1",
}


@cache
def load(step: str) -> tuple[str, str]:
    # (version, prompt text)
    version = VERSIONS[step]
    return version, (PROMPT_DIR / f"{step}.{version}.md").read_text(encoding="utf-8").strip()
