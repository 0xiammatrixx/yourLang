"""Tests for the semantic validator — no LLM involved."""

import pytest

from ir.models import TranslationResult
from validator.semantic import SemanticError, validate, validate_command


def command(raw: dict):
    """Build a structurally validated IR command from raw JSON."""
    return TranslationResult.model_validate(
        {"status": "complete", "command": raw}
    ).command


MOVE = {
    "operation": "move",
    "source": "people",
    "destination": "pension",
    "condition": {"field": "age", "operator": ">", "value": 60},
}


def test_valid_move_passes():
    assert validate(command(MOVE)) is not None


def test_move_without_condition_is_allowed():
    validate(
        command(
            {
                "operation": "move",
                "source": "people",
                "destination": "employees",
            }
        )
    )


def test_move_by_record_id_is_allowed():
    validate(
        command(
            {
                "operation": "move",
                "source": "people",
                "destination": "pension",
                "condition": {"field": "_id", "operator": "=", "value": 1},
            }
        )
    )


def test_record_id_must_be_numeric():
    with pytest.raises(SemanticError):
        validate(
            command(
                {
                    "operation": "move",
                    "source": "people",
                    "destination": "pension",
                    "condition": {"field": "_id", "operator": "=", "value": "1"},
                }
            )
        )


def test_cannot_set_record_id():
    with pytest.raises(SemanticError):
        validate(
            command(
                {
                    "operation": "update",
                    "source": "people",
                    "condition": {"field": "age", "operator": ">", "value": 60},
                    "set": {"_id": 99},
                }
            )
        )


def test_validate_command_sequence():
    ok = command({"operation": "move", "source": "people", "destination": "employees"})
    bad = command({"operation": "move", "source": "banana", "destination": "employees"})
    validate_command([ok, ok])
    with pytest.raises(SemanticError):
        validate_command([ok, bad])


def test_unknown_source_rejected():
    with pytest.raises(SemanticError):
        validate(command({**MOVE, "source": "banana"}))


def test_unknown_destination_rejected():
    with pytest.raises(SemanticError):
        validate(command({**MOVE, "destination": "banana"}))


def test_unknown_field_rejected():
    with pytest.raises(SemanticError):
        validate(
            command(
                {
                    **MOVE,
                    "condition": {"field": "hair", "operator": ">", "value": 60},
                }
            )
        )


def test_wrong_value_type_rejected():
    with pytest.raises(SemanticError):
        validate(
            command(
                {
                    **MOVE,
                    "condition": {"field": "age", "operator": ">", "value": "sixty"},
                }
            )
        )


def test_same_source_and_destination_rejected():
    with pytest.raises(SemanticError):
        validate(command({**MOVE, "destination": "people"}))


def test_create_new_collection_allowed():
    validate(command({"operation": "create", "destination": "archive"}))


def test_create_existing_collection_rejected():
    with pytest.raises(SemanticError):
        validate(command({"operation": "create", "destination": "people"}))


def test_create_bad_name_rejected():
    with pytest.raises(SemanticError):
        validate(command({"operation": "create", "destination": "2 fast"}))


def test_find_string_condition_ok():
    validate(
        command(
            {
                "operation": "find",
                "source": "people",
                "condition": {"field": "name", "operator": "=", "value": "David"},
            }
        )
    )


def test_add_known_record_ok():
    validate(
        command(
            {
                "operation": "add",
                "destination": "employees",
                "records": [{"name": "David", "age": 30, "salary": 50000.0}],
            }
        )
    )


def test_add_unknown_field_rejected():
    with pytest.raises(SemanticError):
        validate(
            command(
                {
                    "operation": "add",
                    "destination": "employees",
                    "records": [{"pet": "cat"}],
                }
            )
        )


def test_update_set_ok():
    validate(
        command(
            {
                "operation": "update",
                "source": "people",
                "condition": {"field": "age", "operator": ">=", "value": 60},
                "set": {"status": "retired"},
            }
        )
    )


def test_update_set_unknown_field_rejected():
    with pytest.raises(SemanticError):
        validate(
            command(
                {
                    "operation": "update",
                    "source": "people",
                    "condition": {"field": "age", "operator": ">=", "value": 60},
                    "set": {"pets": "retired"},
                }
            )
        )


def test_update_set_wrong_type_rejected():
    with pytest.raises(SemanticError):
        validate(
            command(
                {
                    "operation": "update",
                    "source": "people",
                    "condition": {"field": "age", "operator": ">=", "value": 60},
                    "set": {"salary": "a lot"},
                }
            )
        )
