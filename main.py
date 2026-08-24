"""The complete pipeline: NL → LLM → IR → validate → clarify | compile → execute.

Usage:
    .venv/bin/python main.py
    .venv/bin/python main.py "Move everyone aged above 60 to collection pension."
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

from compiler.mongodb import compile_operation
from ir.models import TranslationResult
from runtime.database import MemoryStore, Store, StoreError, execute_plan
from translator import TranslationError, Translator
from validator.semantic import SemanticError, validate

MAX_ROUNDS = 3


def seed_demo_store() -> MemoryStore:
    """Fresh demo data for a pipeline run."""
    return MemoryStore(
        {
            "people": [
                {"name": "David", "age": 30, "country": "Nigeria", "salary": 50000.0, "status": "active"},
                {"name": "Alice", "age": 65, "country": "Italy", "salary": 80000.0, "status": "active"},
                {"name": "Ben", "age": 70, "country": "Nigeria", "salary": 90000.0, "status": "active"},
            ],
            "pension": [],
            "employees": [],
        }
    )


def _follow_up(instruction: str, question: str, answer: str) -> str:
    """Combine the original instruction with the user's answer to a question."""
    return (
        f"{instruction}\n"
        f'Additional information: the user was asked "{question}" '
        f'and answered "{answer}". Use this to complete the instruction.'
    )


def _outcome(
    status: str,
    instruction: str,
    *,
    rounds: int = 0,
    ir: dict | None = None,
    plan: dict | None = None,
    execution: dict | None = None,
    clarification: dict | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "instruction": instruction,
        "rounds": rounds,
        "ir": ir,
        "plan": plan,
        "execution": execution,
        "clarification": clarification,
        "error": error,
    }


def process_instruction(
    instruction: str,
    translator: Any,
    store: Store,
    clarify_fn: Callable[[str], str | None] | None = None,
    max_rounds: int = MAX_ROUNDS,
) -> dict[str, Any]:
    """Run one instruction through the whole pipeline.

    Returns an outcome dict with one of these statuses:
    - "executed"             translation → validation → compilation → execution
    - "needs_clarification"  the LLM asked a question (and got no usable answer)
    - "invalid"              structurally fine but semantically rejected
    - "error"                translation or execution failed
    """
    current = instruction
    rounds = 0

    for _ in range(max_rounds):
        rounds += 1
        try:
            result: TranslationResult = translator.translate(current)
        except TranslationError as exc:
            return _outcome(
                "error", instruction, rounds=rounds, error=f"Translation failed: {exc}"
            )

        if result.status == "needs_clarification":
            clarification = result.clarification
            if clarification is None:  # impossible per the IR models, but be safe
                return _outcome(
                    "error",
                    instruction,
                    rounds=rounds,
                    error="Clarification response without details.",
                )
            details = {
                "message": clarification.message,
                "missing": clarification.missing,
            }
            if clarify_fn is None:
                return _outcome(
                    "needs_clarification",
                    instruction,
                    rounds=rounds,
                    clarification=details,
                )
            answer = clarify_fn(clarification.message)
            if not answer:
                return _outcome(
                    "needs_clarification",
                    instruction,
                    rounds=rounds,
                    clarification=details,
                )
            current = _follow_up(current, clarification.message, answer)
            continue

        command = result.command
        try:
            validate(command)  # semantic (domain) rules
        except SemanticError as exc:
            return _outcome(
                "invalid",
                instruction,
                rounds=rounds,
                ir=command.model_dump(),
                error=f"Semantic validation failed: {exc}",
            )

        try:
            plan = compile_operation(command)
            execution = execute_plan(plan, store)
        except StoreError as exc:
            return _outcome(
                "error",
                instruction,
                rounds=rounds,
                ir=command.model_dump(),
                error=f"Execution failed: {exc}",
            )

        return _outcome(
            "executed",
            instruction,
            rounds=rounds,
            ir=command.model_dump(),
            plan=plan.to_dict(),
            execution=execution,
        )

    return _outcome(
        "needs_clarification",
        instruction,
        rounds=rounds,
        error=f"Reached {max_rounds} clarification rounds without a complete instruction.",
    )


def _interactive_clarify(question: str) -> str | None:
    try:
        answer = input(f"   ? {question}\n   Your answer: ").strip()
    except EOFError:
        return None
    return answer or None


def _print_outcome(outcome: dict[str, Any]) -> None:
    print(f"\n[{outcome['status']}] ({outcome['rounds']} round(s))")
    if outcome["ir"]:
        print(f"IR:       {json.dumps(outcome['ir'])}")
    if outcome["plan"]:
        print(f"Plan:     {json.dumps(outcome['plan'])}")
    if outcome["execution"]:
        print(f"Result:   {json.dumps(outcome['execution']['result'])}")
        print(f"Log:      {json.dumps(outcome['execution']['log'])}")
    if outcome["clarification"]:
        print(f"Question: {outcome['clarification']['message']}")
    if outcome["error"]:
        print(f"Error:    {outcome['error']}")
    print()


def main() -> None:
    store = seed_demo_store()

    if len(sys.argv) > 1:
        instruction = " ".join(sys.argv[1:])
        with Translator() as translator:
            outcome = process_instruction(
                instruction, translator, store, clarify_fn=_interactive_clarify
            )
        print(json.dumps(outcome, indent=2))
        return

    with Translator() as translator:
        print("NL → IR → MongoDB mini semantic compiler")
        print(
            'Type an instruction (e.g. "Move everyone aged above 60 to pension."), '
            'or "quit".\n'
        )
        while True:
            try:
                instruction = input("> ").strip()
            except EOFError:
                break
            if not instruction or instruction.lower() in {"quit", "exit"}:
                break
            outcome = process_instruction(
                instruction, translator, store, clarify_fn=_interactive_clarify
            )
            _print_outcome(outcome)


if __name__ == "__main__":
    main()
