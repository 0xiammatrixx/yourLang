"""Compiler: deterministic translation from validated IR to MongoDB plans.

The compiler is ordinary code — no LLM. It turns each IR operation into a
sequence of primitive MongoDB steps (a small execution plan) that the runtime
executes.

Operator mapping (the only place IR operators meet MongoDB syntax):

    =   -> $eq        >   -> $gt        >=  -> $gte
    !=  -> $ne        <   -> $lt        <=  -> $lte

A "move" has no native MongoDB equivalent, so it compiles to three
primitives: find (remember matches) -> delete_many -> insert_many.
"""

from dataclasses import asdict, dataclass, field
from typing import Any

from ir.models import (
    AddOperation,
    Condition,
    CopyOperation,
    CreateOperation,
    FindOperation,
    MoveOperation,
    Operation,
    RemoveOperation,
    UpdateOperation,
)
from validator.semantic import validate


class CompileError(ValueError):
    """The IR could not be compiled (should not happen after validation)."""


MONGO_OPERATOR: dict[str, str] = {
    "=": "$eq",
    "!=": "$ne",
    ">": "$gt",
    "<": "$lt",
    ">=": "$gte",
    "<=": "$lte",
}


@dataclass
class Step:
    """One primitive MongoDB operation."""

    action: str
    collection: str
    filter: dict[str, Any] | None = None
    documents: Any = None  # literal list of records, or {"$ref": "store"}
    updates: dict[str, Any] | None = None
    store: str | None = None  # when action == "find": where to keep matches


@dataclass
class CompiledPlan:
    """An ordered list of primitive steps for the runtime to execute."""

    steps: list[Step] = field(default_factory=list)
    return_store: str | None = None  # which stored value to return to the user

    def to_dict(self) -> dict:
        return asdict(self)


def condition_to_filter(condition: Condition | None) -> dict[str, Any]:
    """Translate one IR condition into a MongoDB filter expression.

    None (no condition) means "match ALL records" and becomes an empty filter.
    """
    if condition is None:
        return {}
    return {condition.field: {MONGO_OPERATOR[condition.operator]: condition.value}}


def compile_operation(command: Operation) -> CompiledPlan:
    """Compile a validated IR operation into a MongoDB execution plan.

    Re-runs semantic validation first so the invariant "only meaningful IR
    reaches the compiler" is enforced here, not just in main().
    """
    validate(command)  # raises SemanticError if not meaningful

    if isinstance(command, MoveOperation):
        f = condition_to_filter(command.condition)
        return CompiledPlan(
            steps=[
                Step("find", command.source, filter=f, store="matched"),
                Step("delete_many", command.source, filter=f),
                Step("insert_many", command.destination, documents={"$ref": "matched"}),
            ]
        )

    if isinstance(command, CopyOperation):
        f = condition_to_filter(command.condition)
        return CompiledPlan(
            steps=[
                Step("find", command.source, filter=f, store="matched"),
                Step("insert_many", command.destination, documents={"$ref": "matched"}),
            ]
        )

    if isinstance(command, RemoveOperation):
        return CompiledPlan(
            steps=[
                Step(
                    "delete_many",
                    command.source,
                    filter=condition_to_filter(command.condition),
                )
            ]
        )

    if isinstance(command, FindOperation):
        return CompiledPlan(
            steps=[
                Step(
                    "find",
                    command.source,
                    filter=condition_to_filter(command.condition),
                    store="result",
                )
            ],
            return_store="result",
        )

    if isinstance(command, UpdateOperation):
        return CompiledPlan(
            steps=[
                Step(
                    "update_many",
                    command.source,
                    filter=condition_to_filter(command.condition),
                    updates={"$set": command.set},
                )
            ]
        )

    if isinstance(command, AddOperation):
        return CompiledPlan(
            steps=[
                Step("insert_many", command.destination, documents=command.records)
            ]
        )

    if isinstance(command, CreateOperation):
        return CompiledPlan(
            steps=[Step("create_collection", command.destination)]
        )

    raise CompileError(f"Unsupported operation: {command!r}")
