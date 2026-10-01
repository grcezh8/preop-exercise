"""full eval: runs the seed cases and the hand-labeled scenarios, scores every text check on its own,
and writes data/eval_full_report.json plus a readable summary

run: uv run --with pydantic --with openai python -m evals.run_evals_full [--mode pattern_only] [--llm yes_man]
--llm openai uses the real api (needs OPENAI_API_KEY), the others are scripted misbehaving llms that check
the system stays safe when the llm is down, broken, or confidently wrong
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import run_evals as harness
from evals.build_cases import OUT_PATH as SCENARIO_PATH
from evals.build_cases import main as build_scenarios
from evals.labeled import CONSENT, DOC_TYPE, NOTE_MEDS, PLAN
from triage.config import Settings
from triage.extract.anticoag_plan import assess_plans
from triage.extract.consent import assess_consent, pattern_consent
from triage.extract.doc_type import resolve_doc_types
from triage.extract.note_meds import assess_note_mentions
from triage.extract.reader import Reader
from triage.llm.base import LLMClient
from triage.llm.fake_personalities import PERSONALITIES
from triage.llm.openai_client import default_client
from triage.llm.redact import Redactor
from triage.normalize.doc_titles import classify_document
from triage.normalize.text import clean, find_first
from triage.pipeline import run_triage
from triage.schemas.normalized import NormalizedCase, NormDoc, NormMed, NormProcedure
from triage.vocab.phrases import PLAN_PENDING

ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "data" / "patients_sample_50.jsonl"
DISAGREEMENTS_PATH = ROOT / "evals" / "known_oracle_disagreements.json"
DECISIONS = ("READY", "NEEDS_FOLLOW_UP", "NOT_CLEARED")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("default", "pattern_only"), default="default")
    parser.add_argument("--llm", choices=("openai", *PERSONALITIES), default="openai", help="ignored in pattern_only mode")
    parser.add_argument("--model", default=None, help="medium model, used once llm steps exist")
    parser.add_argument("--repeat", type=int, default=2, help="extra runs per case for the repeatability check")
    parser.add_argument("--report", default=str(ROOT / "data" / "eval_full_report.json"))
    return parser.parse_args()


def load_rows() -> list[dict[str, Any]]:
    build_scenarios()
    rows: list[dict[str, Any]] = []
    with SEED_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                rows.append({**row, "group": "seed", "needs_reading": False})
    with SCENARIO_PATH.open(encoding="utf-8") as handle:
        rows.extend(json.loads(line) for line in handle if line.strip())
    return rows


# end-to-end


def run_case(row: dict[str, Any], settings: Settings, repeat: int, llm: LLMClient | None) -> dict[str, Any]:
    expected = row["expected_output"]
    record: dict[str, Any] = {
        "case_id": row["case_id"],
        "group": row["group"],
        "needs_reading": row.get("needs_reading", False),
        "expected_decision": expected["decision"],
        "expected_issues": sorted((i["category"], i["description"]) for i in expected["issues"]),
    }
    try:
        started = time.perf_counter()
        run = run_triage(row["submission"], settings, llm)
        record["latency_ms"] = (time.perf_counter() - started) * 1000
        output = run.output
        repeats = [run_triage(row["submission"], settings, llm).output.model_dump_json() for _ in range(repeat)]
    except Exception as exc:  # a crash is a finding, not a reason to stop the eval
        record.update(error=f"{type(exc).__name__}: {exc}", decision="ERROR", issues=[], latency_ms=0.0)
        return record
    record.update(
        error=None,
        decision=output.decision,
        issues=sorted((i.category, i.description) for i in output.issues),
        repeatable=all(r == output.model_dump_json() for r in repeats),
        grounded=harness._check_issues_value_grounding(row["submission"], output),
        llm_calls=len(run.audit.llm_calls),
        llm_failed=sum(not c.ok for c in run.audit.llm_calls),
        tokens=sum(c.input_tokens + c.output_tokens for c in run.audit.llm_calls),
    )
    return record


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(records)
    if not n:
        return {"cases": 0}
    not_ready = [r for r in records if r["expected_decision"] != "READY"]
    must_block = [r for r in records if r["expected_decision"] == "NOT_CLEARED"]
    unsafe_ready = [r["case_id"] for r in not_ready if r["decision"] == "READY"]
    missed_block = [r["case_id"] for r in must_block if r["decision"] != "NOT_CLEARED"]
    ok = [r for r in records if r["error"] is None]
    latencies = sorted(r["latency_ms"] for r in ok)
    return {
        "cases": n,
        "safety": {
            "unsafe_ready": len(unsafe_ready),
            "unsafe_ready_rate_pct": _pct(len(unsafe_ready), len(not_ready)),
            "unsafe_ready_cases": unsafe_ready,
            "missed_not_cleared": len(missed_block),
            "missed_not_cleared_rate_pct": _pct(len(missed_block), len(must_block)),
            "missed_not_cleared_cases": missed_block,
        },
        "decision_accuracy_pct": _pct(sum(r["decision"] == r["expected_decision"] for r in records), n),
        "issues_exact_match_pct": _pct(sum(r.get("issues") == r["expected_issues"] for r in records), n),
        "categories_exact_match_pct": _pct(
            sum(sorted(c for c, _ in r.get("issues", [])) == sorted(c for c, _ in r["expected_issues"]) for r in records), n
        ),
        "issue_scores": _issue_scores(records),
        "confusion": {
            exp: {got: sum(r["expected_decision"] == exp and r["decision"] == got for r in records) for got in (*DECISIONS, "ERROR")}
            for exp in DECISIONS
        },
        "grounded_pct": _pct(sum(r.get("grounded", False) for r in ok), n),
        "repeatable_pct": _pct(sum(r.get("repeatable", False) for r in ok), n),
        "crashes": [r["case_id"] for r in records if r["error"]],
        "latency_ms": {
            "p50": round(statistics.median(latencies), 2) if latencies else None,
            "p95": round(latencies[int(0.95 * (len(latencies) - 1))], 2) if latencies else None,
        },
        "llm_calls_per_case": round(sum(r.get("llm_calls", 0) for r in ok) / max(len(ok), 1), 2),
        "llm_calls_failed_or_rejected": sum(r.get("llm_failed", 0) for r in ok),
        "tokens_per_case": round(sum(r.get("tokens", 0) for r in ok) / max(len(ok), 1), 1),
    }


def _issue_scores(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    # per issue type: how many real issues we found (recall) and how many we raised were real (precision)
    found: Counter[tuple[str, str]] = Counter()
    expected: Counter[tuple[str, str]] = Counter()
    raised: Counter[tuple[str, str]] = Counter()
    for r in records:
        got, want = Counter(map(tuple, r.get("issues", []))), Counter(map(tuple, r["expected_issues"]))
        found.update(got & want)
        expected.update(want)
        raised.update(got)
    keys = sorted(set(expected) | set(raised))
    return {
        f"{c}: {d}": {
            "expected": expected[(c, d)],
            "raised": raised[(c, d)],
            "recall_pct": _pct(found[(c, d)], expected[(c, d)]),
            "precision_pct": _pct(found[(c, d)], raised[(c, d)]),
        }
        for c, d in keys
    }


# text checks on their own, each labeled example runs through the real extractor in a one-document case
# without an llm (pattern_only) this scores the python half alone


def _doc(text: str, title: str = "", kind: str | None = None, pattern_only: bool = False) -> NormDoc:
    found, source = classify_document(title, clean(text), pattern_only=pattern_only)
    return NormDoc(
        index=0, title_raw=title, kind=kind or found, kind_source=source,
        date=None, text_raw=text, text_clean=clean(text),
    )


def _case(doc: NormDoc, meds: list[NormMed] | None = None) -> NormalizedCase:
    return NormalizedCase(
        procedure=NormProcedure(date=None, risk=None), blood_pressures=[], temperatures=[],
        labs=[], lab_entries=[], meds=meds or [], docs=[doc],
    )


def score_doc_types(settings: Settings, reader: Reader | None) -> dict[str, Any]:
    rows = []
    for title, text, truth in DOC_TYPE:
        case = _case(_doc(text, title, pattern_only=settings.pattern_only))
        if reader:
            case = resolve_doc_types(case, reader)
        kind = case.docs[0].kind
        got = kind if kind in ("HP", "CONSENT", "ANTICOAG_NOTE", "OTHER") else "UNDECIDED"
        rows.append((title, truth, got))
    return _component(rows, dangerous=lambda truth, got: got in ("HP", "CONSENT") and got != truth)


def score_consent(settings: Settings, reader: Reader | None) -> dict[str, Any]:
    rows = []
    for text, truth in CONSENT:
        if settings.pattern_only:
            got, _ = pattern_consent(clean(text))
        else:
            finding = assess_consent(_case(_doc(text, kind="CONSENT")), pattern_only=False, reader=reader)
            got = finding.status if finding else "UNCLEAR"
        rows.append((text, truth, got))
    return _component(rows, dangerous=lambda truth, got: got == "SIGNED" and truth != "SIGNED")


def score_note_meds(settings: Settings, reader: Reader | None) -> dict[str, Any]:
    rows = []
    for passage, drug, truth in NOTE_MEDS:
        mentions = [m for m in assess_note_mentions(_case(_doc(passage)), reader) if m.drug == drug]
        rows.append((passage, truth, mentions[0].taking if mentions else "UNCLEAR"))
    return _component(rows, dangerous=lambda truth, got: got == "NO" and truth != "NO")


def score_plans(settings: Settings, reader: Reader | None) -> dict[str, Any]:
    rows = []
    for passage, drug, truth, _ in PLAN:
        med = NormMed(index=0, name_raw=drug, anticoagulant=drug, active=True)
        plans = assess_plans(_case(_doc(passage, "Perioperative Medication Plan", "ANTICOAG_NOTE"), [med]), [], reader)
        rows.append((passage, "COMPLETE" if truth else "INCOMPLETE", "COMPLETE" if plans and plans[0].passes else "INCOMPLETE"))
    result = _component(rows, dangerous=lambda truth, got: got == "COMPLETE" and truth != "COMPLETE")
    vetoed = {passage for passage, _, _, _ in PLAN if find_first(PLAN_PENDING, clean(passage))}
    incomplete = [p for p, _, truth, _ in PLAN if not truth]
    complete = [p for p, _, truth, _ in PLAN if truth]
    result["pending_check_catches_incomplete_pct"] = _pct(sum(p in vetoed for p in incomplete), len(incomplete))
    result["pending_check_blocks_complete"] = [p for p in complete if p in vetoed]
    return result


def _component(rows: list[tuple[str, str, str]], dangerous: Any) -> dict[str, Any]:
    return {
        "examples": len(rows),
        "accuracy_pct": _pct(sum(truth == got for _, truth, got in rows), len(rows)),
        "dangerous_mistakes": [{"input": x, "truth": t, "got": g} for x, t, g in rows if dangerous(t, g)],
        "wrong": [{"input": x, "truth": t, "got": g} for x, t, g in rows if t != g],
    }


def _pct(part: int, whole: int) -> float | None:
    return round(100.0 * part / whole, 2) if whole else None


# report


def main() -> None:
    args = parse_args()
    settings = Settings.from_env(
        model_medium=args.model, pattern_only=args.mode == "pattern_only", audit_enabled=False
    )
    llm: LLMClient | None = None
    if not settings.pattern_only:
        llm = default_client(settings) if args.llm == "openai" else PERSONALITIES[args.llm]()
    disagreements = set(json.loads(DISAGREEMENTS_PATH.read_text())["cases"])
    rows = load_rows()
    # cases run side by side, the openai client caps calls in flight across all of them
    with ThreadPoolExecutor(max_workers=settings.max_concurrency) as pool:
        records = list(pool.map(lambda row: run_case(row, settings, args.repeat, llm), rows))
    reader = Reader(llm, settings, Redactor({})) if llm is not None else None
    comparable = [r for r in records if r["case_id"] not in disagreements]
    groups = sorted({r["group"] for r in records})
    report = {
        "mode": args.mode,
        "llm": None if settings.pattern_only else args.llm,
        "models": None if settings.pattern_only else {"small": settings.model_small, "medium": settings.model_medium},
        "overall": summarize(comparable),
        "known_disagreements_excluded": sorted(disagreements),
        "by_group": {g: summarize([r for r in comparable if r["group"] == g]) for g in groups},
        "needs_reading": summarize([r for r in comparable if r["needs_reading"]]),
        "text_checks": {
            "doc_type": score_doc_types(settings, reader),
            "consent": score_consent(settings, reader),
            "note_meds": score_note_meds(settings, reader),
            "anticoag_plan": score_plans(settings, reader),
        },
        "mismatches": [
            {k: r[k] for k in ("case_id", "group", "expected_decision", "decision", "expected_issues", "issues", "error") if k in r}
            for r in records
            if r["decision"] != r["expected_decision"] or r.get("issues") != r["expected_issues"]
        ],
    }
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print_summary(report)
    print(f"\nwrote {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")


def print_summary(report: dict[str, Any]) -> None:
    overall = report["overall"]
    safety = overall["safety"]
    print(f"mode: {report['mode']}   llm: {report['llm']}   models: {report['models']}")
    print(f"cases: {overall['cases']} (known disagreements excluded: {', '.join(report['known_disagreements_excluded'])})")
    print("\nsafety (must be 0)")
    print(f"  wrong READY          {safety['unsafe_ready']}  {safety['unsafe_ready_cases']}")
    print(f"  missed NOT_CLEARED   {safety['missed_not_cleared']}  {safety['missed_not_cleared_cases']}")
    print("\noverall")
    for key in ("decision_accuracy_pct", "categories_exact_match_pct", "issues_exact_match_pct", "grounded_pct", "repeatable_pct"):
        print(f"  {key:28s} {overall[key]}")
    print(f"  crashes                      {overall['crashes']}")
    print(f"  latency ms p50/p95           {overall['latency_ms']['p50']} / {overall['latency_ms']['p95']}")
    print(f"  llm calls per case           {overall['llm_calls_per_case']}  (failed or rejected: {overall['llm_calls_failed_or_rejected']})")
    print(f"  tokens per case              {overall['tokens_per_case']}")
    print("\nby group                 cases  decision%  issues%  wrong READY  missed NOT_CLEARED")
    for name, g in [*report["by_group"].items(), ("needs_reading", report["needs_reading"])]:
        print(f"  {name:22s} {g['cases']:5d}  {g['decision_accuracy_pct']!s:>9}  {g['issues_exact_match_pct']!s:>7}  {g['safety']['unsafe_ready']:11d}  {g['safety']['missed_not_cleared']:18d}")
    print("\ntext checks                 examples  accuracy%  dangerous mistakes")
    for name, c in report["text_checks"].items():
        print(f"  {name:26s} {c['examples']:8d}  {c['accuracy_pct']!s:>9}  {len(c['dangerous_mistakes'])}")
    plan = report["text_checks"]["anticoag_plan"]
    print(f"  pending check catches incomplete plans: {plan['pending_check_catches_incomplete_pct']}%, blocks complete plans: {len(plan['pending_check_blocks_complete'])}")
    print(f"\nmismatches: {len(report['mismatches'])} (details in the report)")


if __name__ == "__main__":
    main()
