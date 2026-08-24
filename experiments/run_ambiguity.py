"""Experiment 2.2 — ambiguity detection and the clarification loop.

Two passes:
1. Detection: does the system ask instead of guessing on ambiguous input?
2. Completion: with a canned answer, does the loop then produce the right IR?

Run (from the project root):
    .venv/bin/python -m experiments.run_ambiguity
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from experiments.benchmark import ir_key, load_cases, run_cases
from main import process_instruction, seed_demo_store
from translator import Translator


def run_completion(
    cases: list[dict[str, Any]],
    answers: dict[str, str],
    temperature: float,
) -> list[dict[str, Any]]:
    """Run each ambiguous case with its canned answer on a fresh store."""
    results: list[dict[str, Any]] = []
    with Translator(temperature=temperature) as translator:
        for case in cases:
            store = seed_demo_store()
            answer = answers.get(case["id"])

            def clarify(question: str, _answer: str | None = answer) -> str | None:
                return _answer

            outcome = process_instruction(
                case["instruction"], translator, store, clarify_fn=clarify
            )
            results.append(
                {
                    "id": case.get("id"),
                    "answer": case.get("answer"),
                    "expected_ir_after_answer": case.get("expected_ir_after_answer"),
                    **outcome,
                }
            )
    return results


def print_report(
    detection: list[dict[str, Any]], completion: list[dict[str, Any]]
) -> None:
    n = len(detection)
    asked = sum(1 for r in detection if r["status"] == "needs_clarification")
    guessed = sum(1 for r in detection if r["status"] == "executed")
    other = n - asked - guessed

    print(f"Ambiguity detection: {n} cases\n")
    for r in detection:
        if r["status"] == "needs_clarification":
            clarification = r["clarification"] or {}
            msg = clarification.get("message", "")
            missing = clarification.get("missing", [])
            print(f"  {r['id']:<26} ✓ asked: \"{msg}\"  (missing: {', '.join(missing)})")
        elif r["status"] == "executed":
            print(f"  {r['id']:<26} ✗ GUESSED: {ir_key(r['ir'])}")
        else:
            print(f"  {r['id']:<26} {r['status']}: {r['error']}")

    print(f"\nDETECTION  asked={asked}/{n}  guessed={guessed}/{n}  other={other}/{n}")

    done = sum(1 for r in completion if r["status"] == "executed")
    correct = sum(
        1
        for r in completion
        if r["status"] == "executed"
        and ir_key(r["ir"]) == ir_key(r["expected_ir_after_answer"])
    )

    print("\nClarification loop completion (canned answers)\n")
    for r in completion:
        if r["status"] == "executed":
            match = ir_key(r["ir"]) == ir_key(r["expected_ir_after_answer"])
            if match:
                print(
                    f"  {r['id']:<26} ✓ executed after \"{r['answer']}\" → IR matches expected"
                )
            else:
                print(
                    f"  {r['id']:<26} ✗ WRONG IR after \"{r['answer']}\": {ir_key(r['ir'])}"
                )
        else:
            print(f"  {r['id']:<26} {r['status']}: {r['error']}")

    print(f"\nCOMPLETION  executed={done}/{n}  correct={correct}/{n}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ambiguity experiment")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args()

    cases = load_cases("ambiguity")
    if args.limit:
        cases = cases[: args.limit]

    detection = run_cases(cases, temperature=args.temperature)
    answers = {case["id"]: case.get("answer", "") for case in cases}
    completion = run_completion(cases, answers, args.temperature)

    print_report(detection, completion)

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path("results") / f"ambiguity_{stamp}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(
        json.dumps({"detection": detection, "completion": completion}, indent=2)
    )
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
