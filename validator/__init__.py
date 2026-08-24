"""Deterministic validation layer (semantic domain rules)."""

from .semantic import (
    COLLECTION_SCHEMA,
    SemanticError,
    known_collections,
    validate,
)

__all__ = ["COLLECTION_SCHEMA", "SemanticError", "known_collections", "validate"]
