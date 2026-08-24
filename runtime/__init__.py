"""Deterministic runtime: executes compiled plans against a store."""

from .database import (
    MemoryStore,
    MongoStore,
    Store,
    StoreError,
    execute_plan,
    nearest_collection,
)

__all__ = [
    "MemoryStore",
    "MongoStore",
    "Store",
    "StoreError",
    "execute_plan",
    "nearest_collection",
]
