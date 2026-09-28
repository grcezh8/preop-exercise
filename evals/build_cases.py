"""builds evals/data/scenarios.jsonl from evals/scenarios.py, in the same format as the seed data
so the harness scripts (run_baseline.py, run_evals.py) can run it too

run: uv run --with pydantic python -m evals.build_cases
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evals.mutate import apply_edits
from evals.scenarios import SCENARIOS, Scenario

ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "data" / "patients_sample_50.jsonl"
OUT_PATH = ROOT / "evals" / "data" / "scenarios.jsonl"


def load_seeds() -> dict[str, dict[str, Any]]:
    with SEED_PATH.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return {row["case_id"]: row for row in rows}


def check_label(scenario: Scenario) -> None:
    # the hand-written answer must agree with itself, catches typos in labels
    categories = [category for category, _ in scenario.issues]
    has_safety = "ACUTE_SAFETY_EXCLUSION" in categories
    ok = {
        "READY": not scenario.issues,
        "NOT_CLEARED": has_safety,
        "NEEDS_FOLLOW_UP": bool(scenario.issues) and not has_safety,
    }.get(scenario.decision, False)
    if not ok:
        raise ValueError(f"{scenario.id}: decision {scenario.decision} doesn't fit issues {scenario.issues}")


def build_row(scenario: Scenario, seeds: dict[str, dict[str, Any]]) -> dict[str, Any]:
    check_label(scenario)
    submission = apply_edits(seeds[scenario.seed]["submission"], scenario.edits)
    issues = [
        # evidence is the system's job, labels only fix the category and description
        {"category": c, "description": d, "evidence": {"source": "label", "details": "hand-labeled"}}
        for c, d in scenario.issues
    ]
    explanation = " | ".join(f"{c}: {d}" for c, d in scenario.issues) or "hand-labeled READY"
    return {
        "case_id": scenario.id,
        "submission": submission,
        "expected_output": {"decision": scenario.decision, "issues": issues, "explanation": explanation},
        "group": scenario.group,
        "seed": scenario.seed,
        "needs_reading": scenario.needs_reading,
        "why": scenario.why,
    }


def main() -> None:
    ids = [scenario.id for scenario in SCENARIOS]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"duplicate scenario ids: {sorted(duplicates)}")
    seeds = load_seeds()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as handle:
        for scenario in SCENARIOS:
            handle.write(json.dumps(build_row(scenario, seeds), ensure_ascii=True) + "\n")
    groups: dict[str, int] = {}
    for scenario in SCENARIOS:
        groups[scenario.group] = groups.get(scenario.group, 0) + 1
    print(f"wrote {len(SCENARIOS)} scenarios -> {OUT_PATH.relative_to(ROOT)} {groups}")


if __name__ == "__main__":
    main()
