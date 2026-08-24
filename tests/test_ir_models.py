"""Tests for the IR models — this is the structural validator.

`pytest` runs from the project root, so `ir` is importable directly.
"""

import json

import pytest
from pydantic import ValidationError

from ir.models import MoveOperation, TranslationResult
from ir.schema import json_schema

MOVE_IR = {
    "operation": "move",
    "source": "people",
    "destination": "pension",
    "condition": {"field": "age", "operator": ">", "value": 60},
}


def test_valid_move_parses():
    result = TranslationResult.model_validate(
        {"status": "complete", "command": MOVE_IR}
    )
    assert result.status == "complete"
    assert isinstance(result.command, MoveOperation)
    assert result.command.condition.operator == ">"


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        MoveOperation.model_validate({"operation": "move", "banana": "hello"})


def test_missing_required_field_rejected():
    with pytest.raises(ValidationError):
        MoveOperation.model_validate(
            {"operation": "move", "source": "people"}
        )


def test_bad_operator_rejected():
    with pytest.raises(ValidationError):
        MoveOperation.model_validate(
            {
                "operation": "move",
                "source": "people",
                "destination": "pension",
                "condition": {"field": "age", "operator": ">>", "value": 60},
            }
        )


def test_clarification_result_parses():
    result = TranslationResult.model_validate(
        {
            "status": "needs_clarification",
            "clarification": {
                "message": 'What age counts as "old"?',
                "missing": ["condition.value"],
            },
        }
    )
    assert result.clarification.missing == ["condition.value"]


def test_complete_without_command_rejected():
    with pytest.raises(ValidationError):
        TranslationResult.model_validate({"status": "complete"})


def test_needs_clarification_without_clarification_rejected():
    with pytest.raises(ValidationError):
        TranslationResult.model_validate({"status": "needs_clarification"})


def test_needs_confirmation_parses_and_requires_both():
    ok = TranslationResult.model_validate(
        {
            "status": "needs_confirmation",
            "command": MOVE_IR,
            "clarification": {"message": "Did you mean this?", "missing": []},
        }
    )
    assert ok.status == "needs_confirmation"
    assert ok.command.operation == "move"

    with pytest.raises(ValidationError):
        TranslationResult.model_validate({"status": "needs_confirmation", "command": MOVE_IR})


def test_find_and_update_operations():
    find = TranslationResult.model_validate(
        {
            "status": "complete",
            "command": {
                "operation": "find",
                "source": "people",
                "condition": {"field": "country", "operator": "=", "value": "Nigeria"},
            },
        }
    )
    assert find.command.operation == "find"

    update = TranslationResult.model_validate(
        {
            "status": "complete",
            "command": {
                "operation": "update",
                "source": "people",
                "condition": {"field": "age", "operator": ">=", "value": 60},
                "set": {"status": "retired"},
            },
        }
    )
    assert update.command.set == {"status": "retired"}


def test_schema_is_exportable_and_contains_operations():
    schema = json_schema()
    dumped = json.dumps(schema)
    for op in ("move", "find", "update", "create", "add", "remove", "copy"):
        assert op in dumped
    assert "Condition" in schema["$defs"]


def test_condition_is_optional_for_all_records():
    result = TranslationResult.model_validate(
        {
            "status": "complete",
            "command": {
                "operation": "copy",
                "source": "people",
                "destination": "employees",
            },
        }
    )
    assert result.command.condition is None


def test_remove_limit_parses_and_validates():
    result = TranslationResult.model_validate(
        {
            "status": "complete",
            "command": {
                "operation": "remove",
                "source": "people",
                "limit": 1,
            },
        }
    )
    assert result.command.limit == 1
    with pytest.raises(ValidationError):
        TranslationResult.model_validate(
            {
                "status": "complete",
                "command": {"operation": "remove", "source": "people", "limit": 0},
            }
        )


def test_command_sequence_parses():
    result = TranslationResult.model_validate(
        {
            "status": "complete",
            "command": [
                {"operation": "move", "source": "people", "destination": "employees"},
                {"operation": "move", "source": "pension", "destination": "employees"},
            ],
        }
    )
    assert isinstance(result.command, list)
    assert len(result.command) == 2
    assert result.command[0].operation == "move"
