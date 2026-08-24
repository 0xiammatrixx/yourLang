"""Shared machinery for the experiments.

Each experiment loads cases from JSON, runs them through the full pipeline
with the live translator, and reports metrics. Comparison of IRs and
execution logs is deterministic (plain JSON).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from main import process_instruction, seed_demo_store
from translator import Translator

DATA_DIR = Path(__file__).resolve().parent / "data"


def load_cases(name: str) -> list[dict[str, Any]]:
    path = DATA_DIR / f"{name}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_cases(
    cases: list[dict[str, Any]],
    clarify_fn: Callable[[str], str | None] | None = None,
    max_rounds: int = 3,
    temperature: float = 0.0,
) -> list[dict[str, Any]]:
    """Run every case on a FRESH store so cases don't affect each other."""
    results: list[dict[str, Any]] = []
    with Translator(temperature=temperature) as translator:
        for case in cases:
            store = seed_demo_store()
            outcome = process_instruction(
                case["instruction"],
                translator,
                store,
                clarify_fn=clarify_fn,
                max_rounds=max_rounds,
            )
            results.append(
                {
                    "id": case.get("id"),
                    "intent": case.get("intent"),
                    "expected_ir": case.get("expected_ir"),
                    "expected_status": case.get("expected_status"),
                    "expected_ir_after_answer": case.get("expected_ir_after_answer"),
                    "answer": case.get("answer"),
                    **outcome,
                }
            )
    return results


def _canonical(value: Any) -> Any:
    """Normalize values so 60 and 60.0 compare equal."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    return value


def ir_key(ir: dict | None) -> str:
    """Canonical JSON form of an IR, for equality comparison."""
    return json.dumps(_canonical(ir), sort_keys=True)


def score_paraphrases(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per intent: do all phrasings converge to one IR, and is it the right one?"""
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        groups.setdefault(r["intent"], []).append(r)

    summary = []
    for intent, rs in groups.items():
        executed = [r for r in rs if r["status"] == "executed"]
        distinct_irs = {ir_key(r["ir"]) for r in executed}
        expected = ir_key(rs[0]["expected_ir"])
        all_match_expected = bool(executed) and all(
            ir_key(r["ir"]) == expected for r in executed
        )
        summary.append(
            {
                "intent": intent,
                "phrasings": len(rs),
                "executed": len(executed),
                "distinct_irs": len(distinct_irs),
                "converged": len(executed) == len(rs) and len(distinct_irs) == 1,
                "all_match_expected": all_match_expected,
            }
        )
    return summary
