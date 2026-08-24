"""Experiment 2.4 — baseline comparison: direct code generation vs this system.

Both approaches run on the same cases:
- paraphrases (20): is the final database state correct?
- ambiguity (4): does the system ask instead of guessing?
- adversarial (5): does it execute something unsafe?

Run (from the project root):
    .venv/bin/python -m experiments.run_baseline
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from compiler.mongodb import compile_operation
from experiments.benchmark import ir_key, load_cases, run_cases
from experiments.direct import DirectCodeTranslator, run_baseline_case
from ir.models import TranslationResult
from main import seed_demo_store
from runtime.database import execute_plan


def reference_state(case: dict[str, Any]) -> dict:
    """Expected final store state: run the expected IR through OUR pipeline."""
    ir = TranslationResult.model_validate(
        {"status": "complete", "command": case["expected_ir"]}
    ).command
    store = seed_demo_store()
    execute_plan(compile_operation(ir), store)
    return store.snapshot()


def summarize_direct_paraphrases(results: list[dict[str, Any]]) -> dict[str, int]:
    executed = correct = asked = errors = 0
    for r in results:
        if r["status"] == "executed":
            executed += 1
            if r["state"] == r["reference"]:
                correct += 1
        elif r["status"] == "needs_clarification":
            asked += 1
        else:
            errors += 1
    return {"executed": executed, "correct": correct, "asked": asked, "errors": errors}


def summarize_pipeline_paraphrases(results: list[dict[str, Any]]) -> dict[str, int]:
    executed = sum(1 for r in results if r["status"] == "executed")
    correct = sum(
        1
        for r in results
        if r["status"] == "executed" and ir_key(r["ir"]) == ir_key(r["expected_ir"])
    )
    asked = sum(1 for r in results if r["status"] == "needs_clarification")
    errors = len(results) - executed - asked
    return {"executed": executed, "correct": correct, "asked": asked, "errors": errors}


def summarize_statuses(results: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"executed": 0, "needs_clarification": 0, "invalid": 0, "error": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return counts


def print_table(table: dict[str, Any], details: dict[str, list[dict[str, Any]]]) -> None:
    p = table["paraphrases"]
    a = table["ambiguity"]
    x = table["adversarial"]

    print("Baseline comparison\n" + "=" * 60)
    print(f"Paraphrase convergence ({20} cases)")
    print(
        f"  direct code: executed={p['direct']['executed']}  correct={p['direct']['correct']}  "
        f"asked={p['direct']['asked']}  errors={p['direct']['errors']}"
    )
    print(
        f"  pipeline:    executed={p['pipeline']['executed']}  correct={p['pipeline']['correct']}  "
        f"asked={p['pipeline']['asked']}  errors={p['pipeline']['errors']}"
    )

    print(f"\nAmbiguity detection ({4} cases)")
    print(
        f"  direct code: asked={a['direct']['needs_clarification']}  guessed={a['direct']['executed']}  "
        f"errors={a['direct']['error']}"
    )
    print(
        f"  pipeline:    asked={a['pipeline']['needs_clarification']}  guessed={a['pipeline']['executed']}  "
        f"errors={a['pipeline']['error']}"
    )

    safe_direct = x["direct"]["needs_clarification"] + x["direct"]["error"] + x["direct"]["invalid"]
    safe_pipe = (
        x["pipeline"]["needs_clarification"] + x["pipeline"]["error"] + x["pipeline"]["invalid"]
    )
    print(f"\nAdversarial safety ({5} cases)")
    print(
        f"  direct code: safe={safe_direct}  unsafe(executed)={x['direct']['executed']}"
    )
    print(f"  pipeline:    safe={safe_pipe}  unsafe(executed)={x['pipeline']['executed']}")

    print("\nDirect-code per-case details")
    for kind, rows in details.items():
        print(f"  [{kind}]")
        for r in rows:
            if r["status"] == "executed":
                if kind == "paraphrases":
                    verdict = "correct" if r["state"] == r["reference"] else "WRONG STATE"
                else:
                    verdict = "executed"
                print(f"    {r['id']:<24} executed ({verdict})")
            elif r["status"] == "needs_clarification":
                msg = (r["clarification"] or {}).get("message", "")
                print(f"    {r['id']:<24} asked: {msg}")
            else:
                print(f"    {r['id']:<24} {r['status']}: {r['error']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Baseline comparison experiment")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args()

    cases_p = load_cases("paraphrases")
    cases_a = load_cases("ambiguity")
    cases_x = load_cases("adversarial")
    if args.limit:
        cases_p = cases_p[: args.limit]

    pipe_p = run_cases(cases_p, temperature=args.temperature)
    pipe_a = run_cases(cases_a, temperature=args.temperature)
    pipe_x = run_cases(cases_x, temperature=args.temperature)

    with DirectCodeTranslator(temperature=args.temperature) as direct:
        base_p = [
            {
                "id": c["id"],
                "intent": c.get("intent"),
                "reference": reference_state(c),
                **run_baseline_case(direct, c["instruction"]),
            }
            for c in cases_p
        ]
        base_a = [
            {
                "id": c["id"],
                "intent": c.get("intent"),
                **run_baseline_case(direct, c["instruction"]),
            }
            for c in cases_a
        ]
        base_x = [
            {
                "id": c["id"],
                "intent": c.get("intent"),
                **run_baseline_case(direct, c["instruction"]),
            }
            for c in cases_x
        ]

    table = {
        "paraphrases": {
            "direct": summarize_direct_paraphrases(base_p),
            "pipeline": summarize_pipeline_paraphrases(pipe_p),
        },
        "ambiguity": {
            "direct": summarize_statuses(base_a),
            "pipeline": summarize_statuses(pipe_a),
        },
        "adversarial": {
            "direct": summarize_statuses(base_x),
            "pipeline": summarize_statuses(pipe_x),
        },
    }
    details = {"paraphrases": base_p, "ambiguity": base_a, "adversarial": base_x}

    print_table(table, details)

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path("results") / f"baseline_{stamp}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"table": table, "details": details}, indent=2))
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
