"""Run the complete benchmark suite from a clean environment.

Runs experiments 2.1–2.5 in order (≈115 live DeepSeek calls), then writes
results/summary.json with the recomputed headline metrics.

Usage: .venv/bin/python -m experiments.run_all
"""

from __future__ import annotations

import json
from pathlib import Path

from experiments import (
    audit,
    run_adversarial,
    run_ambiguity,
    run_baseline,
    run_paraphrases,
    run_review,
)


def main() -> None:
    print("Running the complete benchmark suite (2.1 → 2.5)…\n")
    run_paraphrases.main()
    run_ambiguity.main()
    run_adversarial.main()
    run_baseline.main()
    run_review.main()

    summary = audit.collect()
    out = Path("results") / "summary.json"
    out.write_text(json.dumps(summary, indent=2))
    print(f"\nConsolidated summary written to {out}")


if __name__ == "__main__":
    main()
