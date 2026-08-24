"""Tests for the full pipeline, using a fake translator (no LLM, no tokens)."""

from ir.models import TranslationResult
from main import process_instruction, seed_demo_store
from translator import TranslationError

MOVE = {
    "operation": "move",
    "source": "people",
    "destination": "pension",
    "condition": {"field": "age", "operator": ">", "value": 60},
}


def complete(command: dict) -> TranslationResult:
    return TranslationResult.model_validate({"status": "complete", "command": command})


def clarifying(message: str) -> TranslationResult:
    return TranslationResult.model_validate(
        {
            "status": "needs_clarification",
            "clarification": {"message": message, "missing": ["condition.value"]},
        }
    )


def confirming(command: dict, message: str) -> TranslationResult:
    return TranslationResult.model_validate(
        {
            "status": "needs_confirmation",
            "command": command,
            "clarification": {"message": message, "missing": ["condition.value"]},
        }
    )


class FakeTranslator:
    """Returns scripted responses; records every call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[str] = []

    def translate(self, instruction: str) -> TranslationResult:
        self.calls.append(instruction)
        if not self.responses:
            return clarifying("give more detail")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_executed_happy_path():
    store = seed_demo_store()
    fake = FakeTranslator([complete(MOVE)])
    outcome = process_instruction(
        "Move everyone aged above 60 to pension.", fake, store
    )
    assert outcome["status"] == "executed"
    assert outcome["ir"]["operation"] == "move"
    assert len(outcome["execution"]["log"]) == 3
    assert len(store.find("pension", None)) == 2


def test_clarification_loop_then_execute():
    store = seed_demo_store()
    fake = FakeTranslator(
        [clarifying('What age counts as "old"?'), complete(MOVE)]
    )
    asked: list[str] = []

    def clarify(question: str) -> str:
        asked.append(question)
        return "60"

    outcome = process_instruction(
        "Move all the old people to pension.", fake, store, clarify_fn=clarify
    )
    assert outcome["status"] == "executed"
    assert len(fake.calls) == 2
    assert 'answered "60"' in fake.calls[1]
    assert asked == ['What age counts as "old"?']


def test_clarification_without_clarify_fn_stops():
    store = seed_demo_store()
    fake = FakeTranslator([clarifying("what age?")])
    outcome = process_instruction("Move the old people to pension.", fake, store)
    assert outcome["status"] == "needs_clarification"
    assert outcome["clarification"]["message"] == "what age?"
    assert len(store.find("people", None)) == 3  # nothing executed


def test_semantic_error_reported_as_invalid():
    store = seed_demo_store()
    fake = FakeTranslator([complete({**MOVE, "source": "banana"})])
    outcome = process_instruction("Move people from banana to pension.", fake, store)
    assert outcome["status"] == "invalid"
    assert "banana" in outcome["error"]


def test_translation_error_reported():
    store = seed_demo_store()
    fake = FakeTranslator([TranslationError("boom")])
    outcome = process_instruction("Move people to pension.", fake, store)
    assert outcome["status"] == "error"
    assert "boom" in outcome["error"]


def test_max_rounds_reached():
    store = seed_demo_store()
    fake = FakeTranslator([clarifying("a?"), clarifying("b?"), clarifying("c?")])

    def clarify(question: str) -> str:
        return "x"

    outcome = process_instruction(
        "...", fake, store, clarify_fn=clarify, max_rounds=2
    )
    assert outcome["status"] == "needs_clarification"
    assert "2 clarification rounds" in outcome["error"]


def test_confirmation_yes_executes():
    store = seed_demo_store()
    fake = FakeTranslator([confirming(MOVE, "Did you mean: move over 60 to pension?")])
    outcome = process_instruction(
        "Move all the seniors to pension.", fake, store, confirm_fn=lambda q: True
    )
    assert outcome["status"] == "executed"
    assert len(store.find("pension", None)) == 2


def test_confirmation_no_stops():
    store = seed_demo_store()
    fake = FakeTranslator([confirming(MOVE, "Did you mean: move over 60 to pension?")])
    outcome = process_instruction(
        "Move all the seniors to pension.", fake, store, confirm_fn=lambda q: False
    )
    assert outcome["status"] == "needs_confirmation"
    assert "Not confirmed" in outcome["error"]
    assert len(store.find("pension", None)) == 0
