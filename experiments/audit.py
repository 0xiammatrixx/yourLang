"""Audit: recompute the headline metrics from saved raw results.

Two jobs:
1. print the recomputed numbers next to the claims in the paper,
2. exit non-zero if any headline claim does not hold in the raw results.

Run: .venv/bin/python -m experiments.audit
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path
from typing import Any

from experiments.benchmark import ir_key

RESULTS = Path(__file__).resolve().parent.parent / "results"


def newest(pattern: str) -> dict[str, Any]:
    files = sorted(glob.glob(str(RESULTS / pattern)))
    if not files:
        print(f"no files for {pattern}")
        return {}
    with open(files[-1], encoding="utf-8") as f:
        return json.load(f)


def metric_paraphrases(data: dict[str, Any]) -> dict[str, Any]:
    results = data.get("results", [])
    intents: dict[str, list[dict[str, Any]]] = {}
    executed = correct = 0
    for r in results:
        if r["status"] == "executed":
            executed += 1
            if ir_key(r["ir"]) == ir_key(r["expected_ir"]):
                correct += 1
        intents.setdefault(r["intent"], []).append(r)
    converged = 0
    for rs in intents.values():
        ex = [r for r in rs if r["status"] == "executed"]
        irs = {ir_key(r["ir"]) for r in ex}
        if len(ex) == len(rs) and len(irs) == 1:
            converged += 1
    return {
        "cases": len(results),
        "intents": len(intents),
        "executed": executed,
        "correct": correct,
        "converged": converged,
    }


def metric_ambiguity(data: dict[str, Any]) -> dict[str, Any]:
    det = data.get("detection", [])
    comp = data.get("completion", [])
    asked = sum(1 for r in det if r["status"] == "needs_clarification")
    guessed = sum(1 for r in det if r["status"] == "executed")
    completed = sum(1 for r in comp if r["status"] == "executed")
    correct = sum(
        1
        for r in comp
        if r["status"] == "executed"
        and ir_key(r["ir"]) == ir_key(r["expected_ir_after_answer"])
    )
    return {
        "n": len(det),
        "asked": asked,
        "guessed": guessed,
        "completed": completed,
        "correct": correct,
    }


def metric_adversarial(data: dict[str, Any]) -> dict[str, Any]:
    results = data.get("results", [])
    safe = sum(1 for r in results if r["status"] in ("needs_clarification", "invalid"))
    executed = sum(1 for r in results if r["status"] == "executed")
    return {"n": len(results), "safe": safe, "executed": executed}


def metric_baseline(data: dict[str, Any]) -> dict[str, Any]:
    return data.get("table", {})


def metric_review(data: dict[str, Any]) -> dict[str, Any]:
    correct = data.get("correct", [])
    corrupt = data.get("corrupt", [])
    false_rejections = sum(1 for r in correct if r["verdict"] == "REJECTED")
    detected = sum(1 for r in corrupt if r["verdict"] == "REJECTED")
    return {
        "n_correct": len(correct),
        "false_rejections": false_rejections,
        "n_corrupt": len(corrupt),
        "detected": detected,
    }


def collect() -> dict[str, Any]:
    return {
        "paraphrases": metric_paraphrases(newest("paraphrases_*.json")),
        "ambiguity": metric_ambiguity(newest("ambiguity_*.json")),
        "adversarial": metric_adversarial(newest("adversarial_*.json")),
        "baseline": metric_baseline(newest("baseline_*.json")),
        "review": metric_review(newest("review_*.json")),
    }


def main() -> int:
    s = collect()
    checks: list[tuple[str, bool]] = []

    p = s["paraphrases"]
    checks.append(
        (
            f"paraphrases {p['correct']}/{p['cases']} correct, "
            f"{p['converged']}/{p['intents']} intents converged",
            p["correct"] == p["cases"] and p["converged"] == p["intents"],
        )
    )
    a = s["ambiguity"]
    checks.append(
        (
            f"ambiguity {a['asked']}/{a['n']} asked (0 guessed), "
            f"{a['correct']}/{a['n']} completed correctly",
            a["asked"] == a["n"] and a["guessed"] == 0 and a["correct"] == a["n"],
        )
    )
    x = s["adversarial"]
    checks.append(
        (
            f"adversarial {x['safe']}/{x['n']} safe ({x['executed']} unsafe)",
            x["safe"] == x["n"] and x["executed"] == 0,
        )
    )
    r = s["review"]
    checks.append(
        (
            f"reviewer {r['detected']}/{r['n_corrupt']} detected, "
            f"{r['false_rejections']}/{r['n_correct']} false rejections",
            r["detected"] == r["n_corrupt"],
        )
    )
    b = s["baseline"]
    par = b.get("paraphrases", {})
    pipe = par.get("pipeline", {})
    direct = par.get("direct", {})
    checks.append(
        (
            f"baseline pipeline {pipe.get('correct', 0)}/20 correct "
            f"(direct code {direct.get('correct', 0)}/20)",
            pipe.get("correct") == 20 and pipe.get("executed") == 20,
        )
    )

    print("=== Audit (recomputed from saved raw results) ===\n")
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed

    print(f"\n  direct-code: {json.dumps(direct, sort_keys=True)}")
    print(f"  review:      {json.dumps(r, sort_keys=True)}")
    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
