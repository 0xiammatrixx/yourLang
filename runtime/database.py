"""Runtime: executes CompiledPlans against a store.

Two backends behind one interface:
- MemoryStore: in-memory dict-of-lists; deterministic, no server needed.
- MongoStore: real MongoDB via pymongo (needs a running server).

The runtime is deterministic code — the LLM never appears here.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from compiler.mongodb import CompiledPlan


class StoreError(RuntimeError):
    """A step could not be executed against the store."""


class Store(Protocol):
    """The interface both backends implement."""

    def list_collections(self) -> list[str]: ...

    def find(self, collection: str, filter: dict[str, Any] | None) -> list[dict]: ...

    def insert_many(self, collection: str, documents: list[dict]) -> int: ...

    def delete_many(self, collection: str, filter: dict[str, Any] | None) -> int: ...

    def update_many(
        self, collection: str, filter: dict[str, Any] | None, updates: dict[str, Any]
    ) -> int: ...

    def create_collection(self, name: str) -> None: ...


# ---------------------------------------------------------------------------
# Filter evaluation (used by the in-memory store)
# ---------------------------------------------------------------------------


def _cmp(actual: Any, op: str, expected: Any) -> bool:
    if op == "$eq":
        return actual == expected
    if op == "$ne":
        return actual != expected
    if op == "$gt":
        return actual is not None and actual > expected
    if op == "$lt":
        return actual is not None and actual < expected
    if op == "$gte":
        return actual is not None and actual >= expected
    if op == "$lte":
        return actual is not None and actual <= expected
    raise StoreError(f"Unsupported filter operator: {op}")


def _matches(doc: dict, filter: dict[str, Any]) -> bool:
    for field, expr in filter.items():
        actual = doc.get(field)
        if isinstance(expr, dict):
            for op, expected in expr.items():
                if not _cmp(actual, op, expected):
                    return False
        elif actual != expr:
            return False
    return True


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


class MemoryStore:
    """Deterministic in-memory store: {collection: [documents]}."""

    def __init__(self, data: dict[str, list[dict]] | None = None) -> None:
        self._data: dict[str, list[dict]] = {
            name: [dict(doc) for doc in docs] for name, docs in (data or {}).items()
        }

    def list_collections(self) -> list[str]:
        return sorted(self._data)

    def _require(self, collection: str) -> list[dict]:
        if collection not in self._data:
            raise StoreError(f"Unknown collection '{collection}'.")
        return self._data[collection]

    def find(self, collection: str, filter: dict[str, Any] | None) -> list[dict]:
        docs = self._require(collection)
        if not filter:
            return [dict(d) for d in docs]
        return [dict(d) for d in docs if _matches(d, filter)]

    def insert_many(self, collection: str, documents: list[dict]) -> int:
        self._require(collection)
        for doc in documents:
            self._data[collection].append(dict(doc))
        return len(documents)

    def delete_many(self, collection: str, filter: dict[str, Any] | None) -> int:
        docs = self._require(collection)
        keep = [d for d in docs if not _matches(d, filter or {})]
        removed = len(docs) - len(keep)
        self._data[collection] = keep
        return removed

    def update_many(
        self, collection: str, filter: dict[str, Any] | None, updates: dict[str, Any]
    ) -> int:
        docs = self._require(collection)
        changed = 0
        for doc in docs:
            if _matches(doc, filter or {}):
                for field, value in updates.get("$set", {}).items():
                    doc[field] = value
                changed += 1
        return changed

    def create_collection(self, name: str) -> None:
        if name in self._data:
            raise StoreError(f"Collection '{name}' already exists.")
        self._data[name] = []

    def snapshot(self) -> dict[str, list[dict]]:
        """Order-insensitive, serializable picture of the whole store.

        Used by the experiments to compare final states between systems.
        """
        return {
            name: sorted(
                (dict(doc) for doc in docs),
                key=lambda d: json.dumps(d, sort_keys=True),
            )
            for name, docs in sorted(self._data.items())
        }


class MongoStore:
    """Real MongoDB backend (pymongo). Requires a running MongoDB server."""

    def __init__(self, uri: str | None = None, db_name: str = "nldb") -> None:
        import pymongo  # lazy import: the runtime works without pymongo installed

        self._client = pymongo.MongoClient(uri or "mongodb://localhost:27017")
        self._db = self._client[db_name]

    def list_collections(self) -> list[str]:
        return self._db.list_collection_names()

    def find(self, collection: str, filter: dict[str, Any] | None) -> list[dict]:
        return list(self._db[collection].find(filter or {}, {"_id": 0}))

    def insert_many(self, collection: str, documents: list[dict]) -> int:
        if documents:
            self._db[collection].insert_many(documents)
        return len(documents)

    def delete_many(self, collection: str, filter: dict[str, Any] | None) -> int:
        return self._db[collection].delete_many(filter or {}).deleted_count

    def update_many(
        self, collection: str, filter: dict[str, Any] | None, updates: dict[str, Any]
    ) -> int:
        return self._db[collection].update_many(filter or {}, updates).modified_count

    def create_collection(self, name: str) -> None:
        self._db.create_collection(name)

    def close(self) -> None:
        self._client.close()


# ---------------------------------------------------------------------------
# Plan execution
# ---------------------------------------------------------------------------


def _resolve_documents(documents: Any, stores: dict[str, list[dict]]) -> list[dict]:
    if isinstance(documents, dict) and "$ref" in documents:
        name = documents["$ref"]
        if name not in stores:
            raise StoreError(f"Plan referenced unknown store '{name}'.")
        return stores[name]
    return list(documents or [])


def execute_plan(plan: CompiledPlan, store: Store) -> dict[str, Any]:
    """Execute a compiled plan against a store.

    Returns {"result": ..., "log": [...]}. The log records what happened so
    experiments can compare executions (e.g. paraphrase consistency).
    """
    stores: dict[str, list[dict]] = {}
    log: list[dict[str, Any]] = []

    for step in plan.steps:
        action = step.action
        if action == "find":
            docs = store.find(step.collection, step.filter)
            if step.store is None:
                raise StoreError("find step without a store name")
            stores[step.store] = docs
            log.append(
                {"action": "find", "collection": step.collection, "matched": len(docs)}
            )
        elif action == "delete_many":
            n = store.delete_many(step.collection, step.filter)
            log.append(
                {"action": "delete_many", "collection": step.collection, "removed": n}
            )
        elif action == "insert_many":
            docs = _resolve_documents(step.documents, stores)
            n = store.insert_many(step.collection, docs)
            log.append(
                {"action": "insert_many", "collection": step.collection, "inserted": n}
            )
        elif action == "update_many":
            n = store.update_many(step.collection, step.filter, step.updates or {})
            log.append(
                {"action": "update_many", "collection": step.collection, "modified": n}
            )
        elif action == "create_collection":
            store.create_collection(step.collection)
            log.append({"action": "create_collection", "collection": step.collection})
        else:
            raise StoreError(f"Unknown plan action: {action!r}")

    result = stores.get(plan.return_store) if plan.return_store else None
    return {"result": result, "log": log}
