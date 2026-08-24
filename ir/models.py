"""Pydantic models defining the Intermediate Representation (IR).

Design decisions:
- One model per operation; a discriminated union on `operation` picks the right one.
- `extra="forbid"`: unknown fields are rejected (so `{"operation": "move", "banana": "hello"}`
  fails instead of being silently accepted).
- `TranslationResult` is the single LLM-facing wrapper with exactly two states:
  `complete` (command present) or `needs_clarification` (question present).

This file IS the structural validator for everything the LLM produces.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------

Operator = Literal["=", "!=", ">", "<", ">=", "<="]

ScalarValue = int | float | str


class Condition(BaseModel):
    """A single condition of the form: field OPERATOR value.

    Example: {"field": "age", "operator": ">", "value": 60}
    """

    field: str
    operator: Operator
    value: ScalarValue


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


class BaseOperation(BaseModel):
    """All operations forbid extra fields."""

    model_config = ConfigDict(extra="forbid")


class CreateOperation(BaseOperation):
    """Create a collection.

    Example: "Create a collection called pension."
    """

    operation: Literal["create"]
    destination: str


class AddOperation(BaseOperation):
    """Insert records into a collection.

    Example: "Add David, aged 30, to employees."
    """

    operation: Literal["add"]
    destination: str
    records: list[dict[str, ScalarValue]] = Field(min_length=1)


class RemoveOperation(BaseOperation):
    """Remove matching records from a collection.

    Example: "Remove everyone younger than 18 from people."
    """

    operation: Literal["remove"]
    source: str
    condition: Condition | None = None


class MoveOperation(BaseOperation):
    """Move matching records from one collection to another.

    Example: "Move everyone aged above 60 to pension."
    """

    operation: Literal["move"]
    source: str
    destination: str
    condition: Condition | None = None


class CopyOperation(BaseOperation):
    """Copy matching records into another collection (source is unchanged)."""

    operation: Literal["copy"]
    source: str
    destination: str
    condition: Condition | None = None


class FindOperation(BaseOperation):
    """Return matching records without changing anything.

    Example: "Find everyone whose country is Nigeria."
    """

    operation: Literal["find"]
    source: str
    condition: Condition | None = None


class UpdateOperation(BaseOperation):
    """Set fields on matching records.

    Example: 'Set status to "retired" for everyone over 60 in people.'
    """

    operation: Literal["update"]
    source: str
    condition: Condition | None = None
    set: dict[str, ScalarValue | bool] = Field(min_length=1)


Operation = Annotated[
    CreateOperation
    | AddOperation
    | RemoveOperation
    | MoveOperation
    | CopyOperation
    | FindOperation
    | UpdateOperation,
    Field(discriminator="operation"),
]


# ---------------------------------------------------------------------------
# The LLM-facing wrapper
# ---------------------------------------------------------------------------


class ClarificationRequest(BaseModel):
    """What to ask the user when the IR cannot be completed without guessing."""

    message: str = Field(description="Question to ask the user.")
    missing: list[str] = Field(
        description="Names of the IR fields that could not be determined."
    )


class TranslationResult(BaseModel):
    """Every LLM response must match this shape.

    - status == "complete"             -> `command` is required
    - status == "needs_clarification"  -> `clarification` is required
    - status == "needs_confirmation"   -> `command` AND `clarification` required
    """

    status: Literal["complete", "needs_clarification", "needs_confirmation"]
    command: Operation | None = None
    clarification: ClarificationRequest | None = None

    @model_validator(mode="after")
    def _require_matching_payload(self) -> "TranslationResult":
        if self.status == "complete" and self.command is None:
            raise ValueError("status 'complete' requires a 'command'")
        if self.status == "needs_clarification" and self.clarification is None:
            raise ValueError(
                "status 'needs_clarification' requires a 'clarification'"
            )
        if self.status == "needs_confirmation" and (
            self.command is None or self.clarification is None
        ):
            raise ValueError(
                "status 'needs_confirmation' requires both 'command' and "
                "'clarification'"
            )
        return self
