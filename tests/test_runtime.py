"""Tests for the runtime, using the deterministic in-memory store."""

import pytest

from compiler.mongodb import CompiledPlan, Step, compile_operation
from ir.models import TranslationResult
from runtime.database import MemoryStore, StoreError, execute_plan, nearest_collection


def command(raw: dict):
    return TranslationResult.model_validate(
        {"status": "complete", "command": raw}
    ).command


def seeded_store() -> MemoryStore:
    return MemoryStore(
        {
            "people": [
                {"name": "David", "age": 30, "country": "Nigeria", "salary": 50000.0, "status": "active"},
                {"name": "Alice", "age": 65, "country": "Italy", "salary": 80000.0, "status": "active"},
                {"name": "Ben", "age": 70, "country": "Nigeria", "salary": 90000.0, "status": "active"},
            ],
            "pension": [],
            "employees": [],
        }
    )


MOVE = {
    "operation": "move",
    "source": "people",
    "destination": "pension",
    "condition": {"field": "age", "operator": ">", "value": 60},
}


def test_move_executes_end_to_end():
    store = seeded_store()
    plan = compile_operation(command(MOVE))
    out = execute_plan(plan, store)
    assert [d["name"] for d in store.find("people", None)] == ["David"]
    assert sorted(d["name"] for d in store.find("pension", None)) == ["Alice", "Ben"]
    assert [e["action"] for e in out["log"]] == ["find", "delete_many", "insert_many"]


def test_find_returns_result_and_does_not_modify():
    store = seeded_store()
    plan = compile_operation(
        command(
            {
                "operation": "find",
                "source": "people",
                "condition": {"field": "country", "operator": "=", "value": "Nigeria"},
            }
        )
    )
    out = execute_plan(plan, store)
    assert sorted(d["name"] for d in out["result"]) == ["Ben", "David"]
    assert len(store.find("people", None)) == 3


def test_remove_deletes_matches():
    store = seeded_store()
    plan = compile_operation(
        command(
            {
                "operation": "remove",
                "source": "people",
                "condition": {"field": "age", "operator": ">=", "value": 60},
            }
        )
    )
    out = execute_plan(plan, store)
    assert out["log"][0]["removed"] == 2
    assert len(store.find("people", None)) == 1


def test_update_sets_fields():
    store = seeded_store()
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
    out = execute_plan(plan, store)
    assert out["log"][0]["modified"] == 2
    alice = next(d for d in store.find("people", None) if d["name"] == "Alice")
    assert alice["status"] == "retired"


def test_add_inserts_records():
    store = seeded_store()
    plan = compile_operation(
        command(
            {
                "operation": "add",
                "destination": "employees",
                "records": [
                    {
                        "name": "Eve",
                        "age": 25,
                        "country": "Ghana",
                        "salary": 40000.0,
                        "status": "active",
                    }
                ],
            }
        )
    )
    execute_plan(plan, store)
    assert [d["name"] for d in store.find("employees", None)] == ["Eve"]


def test_copy_leaves_source_unchanged():
    store = seeded_store()
    plan = compile_operation(command({**MOVE, "operation": "copy"}))
    execute_plan(plan, store)
    assert len(store.find("people", None)) == 3
    assert len(store.find("pension", None)) == 2


def test_copy_all_copies_everyone_and_keeps_source():
    store = seeded_store()
    plan = compile_operation(
        command(
            {
                "operation": "copy",
                "source": "people",
                "destination": "employees",
            }
        )
    )
    execute_plan(plan, store)
    assert len(store.find("people", None)) == 3
    assert sorted(d["name"] for d in store.find("employees", None)) == ["Alice", "Ben", "David"]


def test_move_by_id_moves_the_right_record():
    store = seeded_store()
    plan = compile_operation(
        command(
            {
                "operation": "move",
                "source": "people",
                "destination": "pension",
                "condition": {"field": "_id", "operator": "=", "value": 1},
            }
        )
    )
    execute_plan(plan, store)
    assert sorted(d["name"] for d in store.find("people", None)) == ["Alice", "Ben"]
    assert [d["name"] for d in store.find("pension", None)] == ["David"]


def test_create_then_collection_exists():
    store = seeded_store()
    plan = compile_operation(command({"operation": "create", "destination": "archive"}))
    execute_plan(plan, store)
    assert "archive" in store.list_collections()


def test_filter_operators_in_memory_store():
    store = seeded_store()
    assert [d["name"] for d in store.find("people", {"age": {"$lte": 30}})] == ["David"]
    assert [d["name"] for d in store.find("people", {"country": {"$ne": "Nigeria"}})] == ["Alice"]


def test_unknown_collection_raises():
    store = seeded_store()
    plan = CompiledPlan(steps=[Step("find", "ghost", filter={}, store="x")])
    with pytest.raises(StoreError):
        execute_plan(plan, store)


def test_plan_with_dangling_reference_raises():
    store = seeded_store()
    plan = CompiledPlan(
        steps=[Step("insert_many", "pension", documents={"$ref": "matched"})]
    )
    with pytest.raises(StoreError):
        execute_plan(plan, store)


def test_snapshot_is_deterministic_and_serializable():
    store = seeded_store()
    snap = store.snapshot()
    assert set(snap) == {"people", "pension", "employees"}
    # Docs are sorted by their canonical JSON (age comes first), so:
    assert [d["name"] for d in snap["people"]] == ["David", "Alice", "Ben"]
    import json as _json

    _json.dumps(snap)


def test_records_get_unique_ids_and_ids_are_stripped_from_results():
    store = MemoryStore({"employees": []})
    store.insert_many("employees", [{"name": "A"}, {"name": "A"}])
    records = store.records_with_ids()["employees"]
    assert len(records) == 2
    ids = [r["_id"] for r in records]
    assert len(set(ids)) == 2
    # find() and snapshot() strip _id so experiments compare clean data
    assert all("_id" not in d for d in store.find("employees", None))
    assert all("_id" not in d for d in store.snapshot()["employees"])


def test_delete_any_removes_one_arbitrary_record():
    store = MemoryStore({"employees": []})
    store.insert_many("employees", [{"name": "A"}, {"name": "A"}, {"name": "A"}])
    removed = store.delete_many("employees", None, limit=1)
    assert removed == 1
    assert len(store.find("employees", None)) == 2


def test_nearest_collection():
    existing = ["people", "employees", "pension", "intern"]
    assert nearest_collection("intenr", existing) == "intern"
    assert nearest_collection("ppl", existing) == "people"
    assert nearest_collection("zzz", existing) is None
