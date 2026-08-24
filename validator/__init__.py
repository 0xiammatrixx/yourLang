"""Deterministic validation layer (semantic domain rules)."""

from .semantic import (
    COLLECTION_SCHEMA,
    SemanticError,
    known_collections,
    validate,
    validate_command,
)

__all__ = [
    "COLLECTION_SCHEMA",
    "SemanticError",
    "known_collections",
    "validate",
    "validate_command",
]
