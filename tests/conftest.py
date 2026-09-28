from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "data" / "patients_sample_50.jsonl"


def load_seed_cases() -> list[dict[str, Any]]:
    with SEED_PATH.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


@pytest.fixture(scope="session")
def seed_cases() -> list[dict[str, Any]]:
    return load_seed_cases()


@pytest.fixture(autouse=True)
def no_real_openai(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # tests never reach the real api, even on a machine with a key set, and never share an answer cache
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("TRIAGE_CACHE_DIR", str(tmp_path / "cache"))
