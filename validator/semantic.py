"""Semantic validation: domain rules the IR shape cannot express.

Structural validation (shape) is handled by the Pydantic models. This module
checks that a well-shaped command is also meaningful in this domain:

- collections must be known,
- the record id (`_id`) is immutable and must be a whole number,
- move/copy must not use the same collection for source and destination,
- create must use a syntactically valid, not-yet-existing collection name.

Fields are SCHEMALESS (like MongoDB): any record may carry any fields, so the
validator does not restrict field names or value types.
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


# Known collections and their TYPICAL fields (informational only — fields are
# schemaless and are not enforced).
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


def _check_known(name: str, role: str) -> None:
    if name not in COLLECTION_SCHEMA:
        raise SemanticError(
            f"Unknown {role} collection '{name}'. "
            f"Known collections: {', '.join(sorted(COLLECTION_SCHEMA))}."
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
    # schemaless: any other field is allowed


def _check_records(collection: str, records: list[dict[str, Any]]) -> None:
    # Schemaless: records may carry any fields (any incoming `_id` is ignored
    # by the runtime, which assigns the id).
    return


def _check_updates(collection: str, updates: dict[str, Any]) -> None:
    # The record id is immutable, like MongoDB's `_id`; everything else may be set.
    if "_id" in updates or "id" in updates:
        raise SemanticError("The record id is immutable and cannot be updated.")


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


def validate_command(command: Any) -> Any:
    """Validate a single operation or every operation in a sequence."""
    if isinstance(command, list):
        for c in command:
            validate(c)
        return command
    validate(command)
    return command
