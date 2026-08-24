"""Tests for the web GUI logic (no Flask server needed)."""

from gui.web import new_store, run_web
from ir.models import TranslationResult

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


class FakeTranslator:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[str] = []

    def translate(self, instruction: str) -> TranslationResult:
        self.calls.append(instruction)
        if not self.responses:
            return clarifying("more detail")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_create_collection_appears_in_store():
    store = new_store()
    state = {"pending": None}
    fake = FakeTranslator(
        [complete({"operation": "create", "destination": "arsenal_players"})]
    )
    outcome = run_web(
        fake, store, state, "Create a new collection called arsenal_players"
    )
    assert outcome["status"] == "executed"
    assert "arsenal_players" in store.snapshot()


def test_clarification_flow_then_answer():
    store = new_store()
    state = {"pending": None}
    fake = FakeTranslator([clarifying("What age counts as old?"), complete(MOVE)])

    out1 = run_web(fake, store, state, "Move all the old people to pension.")
    assert out1["status"] == "needs_clarification"
    assert state["pending"]["question"] == "What age counts as old?"

    out2 = run_web(
        fake, store, state, "Move all the old people to pension.", answer="60"
    )
    assert out2["status"] == "executed"
    assert len(store.find("pension", None)) == 2


def test_semantic_error_reported_as_invalid():
    store = new_store()
    state = {"pending": None}
    fake = FakeTranslator([complete({**MOVE, "source": "banana"})])
    outcome = run_web(fake, store, state, "Move people from banana to pension.")
    assert outcome["status"] == "invalid"
    assert "banana" in outcome["error"]
