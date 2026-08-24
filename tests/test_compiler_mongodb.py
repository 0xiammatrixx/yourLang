"""Tests for the compiler — deterministic, no LLM involved."""

import json

import pytest

from compiler.mongodb import (
    MONGO_OPERATOR,
    compile_operation,
    condition_to_filter,
)
from ir.models import Condition, TranslationResult
from validator.semantic import SemanticError


def command(raw: dict):
    return TranslationResult.model_validate(
        {"status": "complete", "command": raw}
    ).command


MOVE = {
    "operation": "move",
    "source": "people",
    "destination": "pension",
    "condition": {"field": "age", "operator": ">", "value": 60},
}


def test_operator_table_is_complete():
    assert set(MONGO_OPERATOR) == {"=", "!=", ">", "<", ">=", "<="}
    assert MONGO_OPERATOR[">"] == "$gt"
    assert MONGO_OPERATOR["<="] == "$lte"


def test_condition_to_filter():
    condition = Condition(field="age", operator=">", value=60)
    assert condition_to_filter(condition) == {"age": {"$gt": 60}}


def test_condition_to_filter_none_means_all():
    assert condition_to_filter(None) == {}


def test_condition_to_filter_normalizes_id():
    assert condition_to_filter(Condition(field="id", operator="=", value=1)) == {
        "_id": {"$eq": 1}
    }
    assert condition_to_filter(Condition(field="_id", operator="=", value=1)) == {
        "_id": {"$eq": 1}
    }


def test_copy_all_compiles_with_empty_filter():
    plan = compile_operation(
        command(
            {
                "operation": "copy",
                "source": "people",
                "destination": "employees",
            }
        )
    )
    assert [step.action for step in plan.steps] == ["find", "insert_many"]
    assert plan.steps[0].filter == {}


def test_remove_with_limit_compiles():
    plan = compile_operation(
        command({"operation": "remove", "source": "people", "limit": 1})
    )
    assert plan.steps[0].action == "delete_many"
    assert plan.steps[0].limit == 1
    assert plan.steps[0].filter == {}


def test_move_compiles_to_three_steps():
    plan = compile_operation(command(MOVE))
    assert len(plan.steps) == 3
    find, delete, insert = plan.steps
    assert (find.action, find.collection, find.store) == ("find", "people", "matched")
    assert find.filter == {"age": {"$gt": 60}}
    assert (delete.action, delete.collection) == ("delete_many", "people")
    assert delete.filter == {"age": {"$gt": 60}}
    assert (insert.action, insert.collection) == ("insert_many", "pension")
    assert insert.documents == {"$ref": "matched"}


def test_copy_has_no_delete():
    plan = compile_operation(command({**MOVE, "operation": "copy"}))
    assert [step.action for step in plan.steps] == ["find", "insert_many"]


def test_remove_compiles_to_delete_many():
    plan = compile_operation(
        command(
            {
                "operation": "remove",
                "source": "people",
                "condition": {"field": "age", "operator": "<", "value": 18},
            }
        )
    )
    assert len(plan.steps) == 1
    assert plan.steps[0].action == "delete_many"
    assert plan.steps[0].filter == {"age": {"$lt": 18}}


def test_find_compiles_and_marks_return_store():
    plan = compile_operation(
        command(
            {
                "operation": "find",
                "source": "people",
                "condition": {"field": "country", "operator": "=", "value": "Nigeria"},
            }
        )
    )
    assert plan.steps[0].action == "find"
    assert plan.return_store == "result"


def test_update_compiles_to_update_many_with_set():
    plan = compile_operation(
        command(
            {
                "operation": "update",
                "source": "people",
                "condition": {"field": "age", "operator": ">=", "value": 60},
                "set": {"status": "retired"},
            }
        )
    )
    assert plan.steps[0].action == "update_many"
    assert plan.steps[0].updates == {"$set": {"status": "retired"}}


def test_add_compiles_to_insert_many():
    plan = compile_operation(
        command(
            {
                "operation": "add",
                "destination": "employees",
                "records": [{"name": "David", "age": 30, "salary": 50000.0}],
            }
        )
    )
    assert plan.steps[0].action == "insert_many"
    assert plan.steps[0].documents == [{"name": "David", "age": 30, "salary": 50000.0}]


def test_create_compiles_to_create_collection():
    plan = compile_operation(command({"operation": "create", "destination": "archive"}))
    assert plan.steps[0].action == "create_collection"
    assert plan.steps[0].collection == "archive"


def test_unvalidated_command_is_rejected():
    with pytest.raises(SemanticError):
        compile_operation(command({**MOVE, "source": "banana"}))


def test_plan_serializes_to_json():
    plan = compile_operation(command(MOVE))
    dumped = json.dumps(plan.to_dict())
    assert '"action"' in dumped
    assert '"people"' in dumped
    assert '"pension"' in dumped
