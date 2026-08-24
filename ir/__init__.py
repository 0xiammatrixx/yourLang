"""Intermediate Representation (IR) — the deterministic core of the system.

Architecture role:
    The LLM maps unrestricted natural language ONTO these models.
    Everything after this boundary (validation, compilation, execution)
    is ordinary deterministic code. The LLM never executes anything.
"""

from .models import (
    AddOperation,
    ClarificationRequest,
    Condition,
    CopyOperation,
    CreateOperation,
    FindOperation,
    MoveOperation,
    Operation,
    RemoveOperation,
    TranslationResult,
    UpdateOperation,
)

__all__ = [
    "AddOperation",
    "ClarificationRequest",
    "Condition",
    "CopyOperation",
    "CreateOperation",
    "FindOperation",
    "MoveOperation",
    "Operation",
    "RemoveOperation",
    "TranslationResult",
    "UpdateOperation",
]
