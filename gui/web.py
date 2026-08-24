"""Pure logic behind the web GUI — no Flask import here (keeps it testable).

One request at a time: run an instruction against the persistent in-memory
store, and manage the pending-clarification state.
"""

from __future__ import annotations

from typing import Any

from compiler.mongodb import compile_command
from ir.models import TranslationResult, command_to_json
from main import _follow_up, seed_demo_store
from runtime.database import MemoryStore, execute_plan
from translator import TranslationError
from validator.semantic import SemanticError, validate_command


def new_store() -> MemoryStore:
    """Fresh seeded store (people, employees, pension)."""
    return seed_demo_store()


def _execute(instruction: str, command: Any, store: MemoryStore) -> dict[str, Any]:
    """Validate, compile, and execute a command (single operation or sequence)."""
    try:
        validate_command(command)  # semantic (domain) rules
    except SemanticError as exc:
        return {
            "status": "invalid",
            "instruction": instruction,
            "ir": command_to_json(command),
            "error": f"Semantic validation failed: {exc}",
        }
    plan = compile_command(command)
    execution = execute_plan(plan, store)
    return {
        "status": "executed",
        "instruction": instruction,
        "ir": command_to_json(command),
        "plan": plan.to_dict(),
        "execution": execution,
    }


def run_web(
    translator: Any,
    store: MemoryStore,
    state: dict,
    instruction: str,
    answer: str | None = None,
) -> dict[str, Any]:
    """Run one instruction; state['pending'] tracks clarification/confirmation."""
    instruction = (instruction or "").strip()
    pending = state.get("pending")

    # An answer to a previous "did you mean …?" confirmation.
    if pending and pending.get("kind") == "confirm" and answer:
        state["pending"] = None
        if answer.strip().lower() in ("yes", "y"):
            command = TranslationResult.model_validate(
                {"status": "complete", "command": pending["command"]}
            ).command
            return _execute(pending["instruction"], command, store)
        return {
            "status": "needs_confirmation",
            "instruction": pending["instruction"],
            "clarification": {
                "message": "Not confirmed. Please rephrase or give more detail.",
                "missing": [],
            },
        }

    if not instruction:
        return {"status": "error", "error": "No instruction given."}

    # An answer to a previous open clarification.
    if pending and pending.get("kind") == "clarify" and answer:
        state["pending"] = None
        instruction = _follow_up(pending["instruction"], pending["question"], answer)

    try:
        result: TranslationResult = translator.translate(instruction)
    except TranslationError as exc:
        return {"status": "error", "error": f"Translation failed: {exc}"}

    if result.status == "needs_clarification":
        clarification = result.clarification
        state["pending"] = {
            "kind": "clarify",
            "instruction": instruction,
            "question": clarification.message,
            "missing": clarification.missing,
        }
        return {
            "status": "needs_clarification",
            "instruction": instruction,
            "clarification": {
                "message": clarification.message,
                "missing": clarification.missing,
            },
        }

    if result.status == "needs_confirmation":
        clarification = result.clarification
        command = result.command
        state["pending"] = {
            "kind": "confirm",
            "instruction": instruction,
            "question": clarification.message,
            "command": command_to_json(command),
        }
        return {
            "status": "needs_confirmation",
            "instruction": instruction,
            "ir": command_to_json(command),
            "clarification": {
                "message": clarification.message,
                "missing": clarification.missing,
            },
        }

    return _execute(instruction, result.command, store)
