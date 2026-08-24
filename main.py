"""The complete pipeline: NL → LLM → IR → validate → clarify | compile → execute.

Usage:
    .venv/bin/python main.py
    .venv/bin/python main.py "Move everyone aged above 60 to collection pension."
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

from compiler.mongodb import compile_command
from ir.models import TranslationResult, command_to_json
from runtime.database import MemoryStore, Store, StoreError, execute_plan, nearest_collection
from translator import TranslationError, Translator
from validator.semantic import SemanticError, validate_command

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


def _execute_command(
    instruction: str, command: Any, store: Store, rounds: int
) -> dict[str, Any]:
    """Validate, compile, and execute a command (single operation or sequence)."""
    try:
        validate_command(command)  # semantic (domain) rules
    except SemanticError as exc:
        return _outcome(
            "invalid",
            instruction,
            rounds=rounds,
            ir=command_to_json(command),
            error=f"Semantic validation failed: {exc}",
        )
    try:
        plan = compile_command(command)
        execution = execute_plan(plan, store)
    except StoreError as exc:
        return _outcome(
            "error",
            instruction,
            rounds=rounds,
            ir=command_to_json(command),
            error=f"Execution failed: {exc}",
        )
    return _outcome(
        "executed",
        instruction,
        rounds=rounds,
        ir=command_to_json(command),
        plan=plan.to_dict(),
        execution=execution,
    )


def _referenced_collections(command: Any) -> list[str]:
    """All source/destination collection names a command REFERENCES.

    `create`'s destination is the new collection, not a reference, so it is
    skipped.
    """
    cmds = command if isinstance(command, list) else [command]
    names: list[str] = []
    for c in cmds:
        if getattr(c, "operation", None) == "create":
            continue
        for attr in ("source", "destination"):
            value = getattr(c, attr, None)
            if value:
                names.append(value)
    return names


def _missing_collections(command: Any, store: Store) -> list[str]:
    existing = set(store.list_collections())
    missing: list[str] = []
    for name in _referenced_collections(command):
        if name not in existing and name not in missing:
            missing.append(name)
    return missing


def _substitute_collection(command: Any, old: str, new: str) -> Any:
    """Return a copy of the command with collection `old` replaced by `new`."""
    if isinstance(command, list):
        return [_substitute_collection(c, old, new) for c in command]
    data = command.model_dump()
    for attr in ("source", "destination"):
        if data.get(attr) == old:
            data[attr] = new
    return TranslationResult.model_validate(
        {"status": "complete", "command": data}
    ).command


def process_instruction(
    instruction: str,
    translator: Any,
    store: Store,
    clarify_fn: Callable[[str], str | None] | None = None,
    confirm_fn: Callable[[str], bool | None] | None = None,
    max_rounds: int = MAX_ROUNDS,
) -> dict[str, Any]:
    """Run one instruction through the whole pipeline.

    Returns an outcome dict with one of these statuses:
    - "executed"             translation → validation → compilation → execution
    - "needs_clarification"  the LLM asked a question (and got no usable answer)
    - "needs_confirmation"   the LLM proposed a guess and asked the user to confirm
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

        if result.status == "needs_confirmation":
            clarification = result.clarification
            command = result.command
            details = {
                "message": clarification.message if clarification else "",
                "missing": clarification.missing if clarification else [],
            }
            if confirm_fn is None:
                return _outcome(
                    "needs_confirmation",
                    instruction,
                    rounds=rounds,
                    ir=command_to_json(command),
                    clarification=details,
                )
            answer = confirm_fn(details["message"])
            if answer is True:
                return _execute_command(instruction, command, store, rounds)
            # Not confirmed — ask for more detail, or stop.
            if clarify_fn is not None:
                fixed = clarify_fn(details["message"])
                if fixed:
                    current = _follow_up(current, details["message"], fixed)
                    continue
            return _outcome(
                "needs_confirmation",
                instruction,
                rounds=rounds,
                ir=command_to_json(command),
                clarification=details,
                error="Not confirmed by the user.",
            )

        command = result.command
        missing = _missing_collections(command, store)
        if missing:
            name = missing[0]
            suggestion = nearest_collection(name, store.list_collections())
            if suggestion:
                question = f'Collection "{name}" does not exist. Did you mean "{suggestion}"?'
            else:
                question = f'Collection "{name}" does not exist. Create it?'
            details = {"message": question, "missing": []}
            if confirm_fn is None:
                return _outcome(
                    "needs_confirmation",
                    instruction,
                    rounds=rounds,
                    ir=command_to_json(command),
                    clarification=details,
                )
            answer = confirm_fn(question)
            if answer is True:
                if suggestion:
                    command = _substitute_collection(command, name, suggestion)
                else:
                    store.create_collection(name)
                return _execute_command(instruction, command, store, rounds)
            return _outcome(
                "needs_clarification",
                instruction,
                rounds=rounds,
                ir=command_to_json(command),
                clarification=details,
                error="Not confirmed by the user.",
            )

        return _execute_command(instruction, command, store, rounds)

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


def _interactive_confirm(question: str) -> bool | None:
    try:
        answer = input(f"   ? {question}\n   [y/n]: ").strip().lower()
    except EOFError:
        return None
    if answer in ("y", "yes"):
        return True
    if answer in ("n", "no"):
        return False
    return None


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
                instruction,
                translator,
                store,
                clarify_fn=_interactive_clarify,
                confirm_fn=_interactive_confirm,
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
                instruction,
                translator,
                store,
                clarify_fn=_interactive_clarify,
                confirm_fn=_interactive_confirm,
            )
            _print_outcome(outcome)


if __name__ == "__main__":
    main()
