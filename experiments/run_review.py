"""Experiment 2.5 — the semantic reviewer (LLM #2).

Measures, on real instruction→IR pairs:
- false rejection rate on 20 known-correct IRs (the paraphrase benchmark)
- detection rate on corrupted IRs that are structurally/semantically valid
  but do NOT faithfully capture the instruction (the deterministic validator
  cannot catch these)

Run (from the project root):
    .venv/bin/python -m experiments.run_review
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from experiments.benchmark import load_cases
from experiments.review import Reviewer


def print_report(
    correct: list[dict[str, Any]], corrupt: list[dict[str, Any]]
) -> None:
    n_correct = len(correct)
    n_corrupt = len(corrupt)

    approved = sum(1 for r in correct if r["verdict"] == "APPROVED")
    false_rejections = [r for r in correct if r["verdict"] == "REJECTED"]
    correct_errors = sum(1 for r in correct if r["verdict"] == "ERROR")

    detected = sum(1 for r in corrupt if r["verdict"] == "REJECTED")
    misses = [r for r in corrupt if r["verdict"] == "APPROVED"]
    corrupt_errors = sum(1 for r in corrupt if r["verdict"] == "ERROR")

    print(f"Semantic reviewer on {n_correct} known-correct IRs\n")
    for r in correct:
        mark = "✓" if r["verdict"] == "APPROVED" else "✗"
        print(f"  {mark} {r['id']:<12} {r['verdict']:<9} {r['reason']}")
    print(
        f"\nCORRECT SET  approved={approved}/{n_correct}  "
        f"false_rejections={len(false_rejections)}  errors={correct_errors}"
    )

    print(f"\nSemantic reviewer on {n_corrupt} corrupted IRs (validator cannot catch)\n")
    for r in corrupt:
        if r["verdict"] == "REJECTED":
            print(f"  ✓ {r['id']:<20} detected: {r['reason']}")
        elif r["verdict"] == "APPROVED":
            print(f"  ✗ {r['id']:<20} MISSED (approved)")
        else:
            print(f"  ⚠ {r['id']:<20} {r['reason']}")
    print(
        f"\nCORRUPT SET   detected={detected}/{n_corrupt}  "
        f"missed={len(misses)}  errors={corrupt_errors}"
    )

    print(
        "\nREVIEWER SUMMARY  "
        f"false-rejection={len(false_rejections)}/{n_correct}  "
        f"detection={detected}/{n_corrupt}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Semantic reviewer experiment")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args()

    correct = load_cases("paraphrases")
    corrupt = load_cases("review_corrupt")
    if args.limit:
        correct = correct[: args.limit]

    with Reviewer(temperature=args.temperature) as reviewer:
        correct_results = [
            {
                "id": c["id"],
                "instruction": c["instruction"],
                **reviewer.review(c["instruction"], c["expected_ir"]),
            }
            for c in correct
        ]
        corrupt_results = [
            {
                "id": c["id"],
                "instruction": c["instruction"],
                **reviewer.review(c["instruction"], c["ir"]),
            }
            for c in corrupt
        ]

    print_report(correct_results, corrupt_results)

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path("results") / f"review_{stamp}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(
        json.dumps(
            {"correct": correct_results, "corrupt": corrupt_results}, indent=2
        )
    )
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
