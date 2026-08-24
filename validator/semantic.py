"""Semantic validation: domain rules the IR shape cannot express.

Structural validation (shape) is handled by the Pydantic models. This module
checks that a well-shaped command is also meaningful in this domain:

- collections must be known,
- condition/set/record fields must exist on the relevant collection,
- values must match the declared field types,
- move/copy must not use the same collection for source and destination,
- create must use a syntactically valid, not-yet-existing collection name.
"""

import re
from typing import Any

from ir.models import (
    AddOperation,
    CopyOperation,
    CreateOperation,
    FindOperation,
    MoveOperation,
    Operation,
    RemoveOperation,
    UpdateOperation,
)


class SemanticError(ValueError):
    """The command is well-shaped but not meaningful in this domain."""


# Static domain knowledge for version 0.1.
COLLECTION_SCHEMA: dict[str, dict[str, type]] = {
    "people": {
        "name": str,
        "age": int,
        "country": str,
        "salary": float,
        "status": str,
    },
    "employees": {
        "name": str,
        "age": int,
        "country": str,
        "salary": float,
        "status": str,
    },
    "pension": {
        "name": str,
        "age": int,
        "country": str,
        "status": str,
    },
}

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def known_collections() -> tuple[str, ...]:
    return tuple(COLLECTION_SCHEMA)


def _type_matches(value: Any, field_type: type) -> bool:
    if field_type in (int, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, field_type)


def _check_known(name: str, role: str) -> None:
    if name not in COLLECTION_SCHEMA:
        raise SemanticError(
            f"Unknown {role} collection '{name}'. "
            f"Known collections: {', '.join(sorted(COLLECTION_SCHEMA))}."
        )


def _check_field_value(collection: str, field: str, value: Any) -> None:
    schema = COLLECTION_SCHEMA[collection]
    if field not in schema:
        raise SemanticError(
            f"Unknown field '{field}' in collection '{collection}'. "
            f"Known fields: {', '.join(schema)}."
        )
    if not _type_matches(value, schema[field]):
        raise SemanticError(
            f"Value {value!r} for field '{field}' must be of type "
            f"{schema[field].__name__}."
        )


def _check_condition(collection: str, condition: Any) -> None:
    if condition is None:
        return  # no condition = match all records
    if condition.field in ("id", "_id"):
        if not (isinstance(condition.value, int) and not isinstance(condition.value, bool)):
            raise SemanticError(
                f"Record id must be a whole number, got {condition.value!r}."
            )
        return
    _check_field_value(collection, condition.field, condition.value)


def _check_records(collection: str, records: list[dict[str, Any]]) -> None:
    for record in records:
        for field, value in record.items():
            _check_field_value(collection, field, value)


def _check_updates(collection: str, updates: dict[str, Any]) -> None:
    for field, value in updates.items():
        _check_field_value(collection, field, value)


def _check_collection_name(name: str) -> None:
    if not _NAME_PATTERN.match(name):
        raise SemanticError(
            f"Invalid collection name '{name}'. "
            f"Names must match {_NAME_PATTERN.pattern}."
        )


def validate(command: Operation) -> Operation:
    """Raise SemanticError if the command is not meaningful; return it otherwise."""
    if isinstance(command, CreateOperation):
        _check_collection_name(command.destination)
        if command.destination in COLLECTION_SCHEMA:
            raise SemanticError(
                f"Collection '{command.destination}' already exists."
            )
    elif isinstance(command, AddOperation):
        _check_known(command.destination, "destination")
        _check_records(command.destination, command.records)
    elif isinstance(command, (MoveOperation, CopyOperation)):
        _check_known(command.source, "source")
        _check_known(command.destination, "destination")
        if command.source == command.destination:
            raise SemanticError(
                f"Source and destination are the same collection: '{command.source}'."
            )
        _check_condition(command.source, command.condition)
    elif isinstance(command, (RemoveOperation, FindOperation)):
        _check_known(command.source, "source")
        _check_condition(command.source, command.condition)
    elif isinstance(command, UpdateOperation):
        _check_known(command.source, "source")
        _check_condition(command.source, command.condition)
        _check_updates(command.source, command.set)
    else:  # pragma: no cover — the discriminated union is exhaustive
        raise SemanticError(f"Unsupported operation: {command!r}")
    return command
