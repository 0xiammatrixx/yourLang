"""Pure logic behind the web GUI — no Flask import here (keeps it testable).

One request at a time: run an instruction against the persistent in-memory
store, and manage the pending-clarification state.
"""

from __future__ import annotations

from typing import Any

from compiler.mongodb import compile_operation
from ir.models import TranslationResult
from main import _follow_up, seed_demo_store
from runtime.database import MemoryStore, execute_plan
from translator import TranslationError
from validator.semantic import SemanticError, validate


def new_store() -> MemoryStore:
    """Fresh seeded store (people, employees, pension)."""
    return seed_demo_store()


def run_web(
    translator: Any,
    store: MemoryStore,
    state: dict,
    instruction: str,
    answer: str | None = None,
) -> dict[str, Any]:
    """Run one instruction; state['pending'] tracks clarification flows.

    Returns an outcome dict with the same shape as main.process_instruction.
    """
    instruction = (instruction or "").strip()
    if not instruction:
        return {"status": "error", "error": "No instruction given."}

    # If the previous step asked a question and the user just answered it,
    # combine the answer with the original instruction and re-translate.
    if state.get("pending") and answer:
        pending = state["pending"]
        state["pending"] = None
        instruction = _follow_up(pending["instruction"], pending["question"], answer)

    try:
        result: TranslationResult = translator.translate(instruction)
    except TranslationError as exc:
        return {"status": "error", "error": f"Translation failed: {exc}"}

    if result.status == "needs_clarification":
        clarification = result.clarification
        state["pending"] = {
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

    command = result.command
    try:
        validate(command)  # semantic (domain) rules
    except SemanticError as exc:
        return {
            "status": "invalid",
            "instruction": instruction,
            "ir": command.model_dump(),
            "error": f"Semantic validation failed: {exc}",
        }

    plan = compile_operation(command)
    execution = execute_plan(plan, store)
    return {
        "status": "executed",
        "instruction": instruction,
        "ir": command.model_dump(),
        "plan": plan.to_dict(),
        "execution": execution,
    }
