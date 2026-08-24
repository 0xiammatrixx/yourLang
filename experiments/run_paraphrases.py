"""Experiment 2.1 — paraphrase convergence.

Do different English phrasings of the same intent converge to the same IR?

Run (from the project root):
    .venv/bin/python -m experiments.run_paraphrases
    .venv/bin/python -m experiments.run_paraphrases --limit 5
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from experiments.benchmark import (
    ir_key,
    load_cases,
    run_cases,
    score_paraphrases,
)


def print_report(results: list[dict[str, Any]], summary: list[dict[str, Any]]) -> None:
    total = len(results)
    executed = sum(1 for r in results if r["status"] == "executed")
    converged = sum(1 for s in summary if s["converged"])
    correct = sum(1 for s in summary if s["converged"] and s["all_match_expected"])

    print(f"Paraphrase convergence: {total} cases, {len(summary)} intents\n")

    groups: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        groups.setdefault(r["intent"], []).append(r)

    for s in summary:
        rs = groups[s["intent"]]
        print(f"INTENT {s['intent']}")
        print(f"  expected IR: {ir_key(rs[0]['expected_ir'])}")
        for r in rs:
            if r["status"] == "executed":
                if ir_key(r["ir"]) == ir_key(r["expected_ir"]):
                    print(f"  {r['id']:<8} ✓ executed, IR matches expected")
                else:
                    print(f"  {r['id']:<8} ✗ WRONG IR: {ir_key(r['ir'])}")
            elif r["status"] == "needs_clarification":
                msg = r["clarification"]["message"] if r["clarification"] else r["error"]
                print(f"  {r['id']:<8} ⚠ asked: {msg}")
            else:
                print(f"  {r['id']:<8} {r['status']}: {r['error']}")
        print(
            f"  → distinct IRs: {s['distinct_irs']}, "
            f"converged: {'yes' if s['converged'] else 'no'}\n"
        )

    print("SUMMARY")
    print(f"  executed:            {executed}/{total}")
    print(f"  converged intents:   {converged}/{len(summary)}")
    print(f"  converged + correct: {correct}/{len(summary)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Paraphrase convergence experiment")
    parser.add_argument("--limit", type=int, default=0, help="run only the first N cases")
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args()

    cases = load_cases("paraphrases")
    if args.limit:
        cases = cases[: args.limit]

    results = run_cases(cases, temperature=args.temperature)
    summary = score_paraphrases(results)

    print_report(results, summary)

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path("results") / f"paraphrases_{stamp}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"results": results, "summary": summary}, indent=2))
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
