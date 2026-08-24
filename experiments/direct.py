"""Baseline: the LLM generates executable Python code directly — no IR.

This is the "just ask the LLM for code" approach the paper compares against.
Generated code runs in a sandbox that only exposes the db_* functions, so it
is safe to execute. Correctness is judged by comparing the resulting store
state to the reference state produced by our IR pipeline.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from main import seed_demo_store
from runtime.database import MemoryStore

CLARIFICATION_MARKER = "# CLARIFICATION:"

_SYSTEM_PROMPT = """\
You generate executable Python code that performs the database operation described
in the user's instruction.

Available functions (and ONLY these):
  db_find(collection, filter) -> list of dicts
  db_delete(collection, filter) -> number deleted
  db_insert(collection, documents) -> number inserted
  db_update(collection, filter, updates) -> number updated

Filter dictionaries use MongoDB operators, e.g. {"age": {"$gt": 60}}; also "$lt",
"$gte", "$lte", "$eq", "$ne". Updates use {"$set": {"field": value}}.

Known collections: "people", "pension", "employees".
Fields of "people": name, age, country, salary, status.

Rules:
- Respond with ONLY Python code. No markdown fences, no explanations.
- Do not import anything and do not define functions; just call the db_* functions.
- If the instruction is ambiguous (e.g. an undefined word such as "old"), respond
  with exactly one line of the form:
  # CLARIFICATION: <short question>
"""


def _extract_code(content: str) -> str:
    content = content.strip()
    if "```" in content:
        parts = content.split("```")
        for part in parts:
            block = part.strip()
            if block.startswith("python"):
                return block[len("python") :].strip()
            if block and not block.lower().startswith("clarification"):
                return block
    return content


def _clarification_question(code: str) -> str | None:
    lower = code.lower()
    idx = lower.find(CLARIFICATION_MARKER.lower())
    if idx < 0:
        return None
    return code[idx + len(CLARIFICATION_MARKER) :].strip()


class DirectCodeTranslator:
    """Baseline translator: instruction → Python code (no IR, no validator)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = (
            base_url or os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
        ).rstrip("/")
        self.model = model or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"
        self.temperature = temperature
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=timeout,
            transport=transport,
        )

    def generate(self, instruction: str) -> str:
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set.")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": instruction},
            ],
            "temperature": self.temperature,
            "max_tokens": 1024,
        }
        response = self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        return _extract_code(data["choices"][0]["message"]["content"])

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "DirectCodeTranslator":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class _Sandbox:
    """Exposes ONLY the db_* functions to the generated code."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def vars(self) -> dict[str, Any]:
        return {
            "db_find": self._store.find,
            "db_delete": self._store.delete_many,
            "db_insert": self._store.insert_many,
            "db_update": self._store.update_many,
        }


def run_baseline_case(
    translator: DirectCodeTranslator, instruction: str
) -> dict[str, Any]:
    """Run one instruction through the direct-code baseline on a fresh store."""
    store = seed_demo_store()
    sandbox = _Sandbox(store)

    try:
        code = translator.generate(instruction)
    except Exception as exc:  # HTTP or API-shape failures
        return {"status": "error", "error": f"generation failed: {exc}"}

    question = _clarification_question(code)
    if question is not None:
        return {"status": "needs_clarification", "clarification": {"message": question}}

    try:
        exec(code, {"__builtins__": {}}, sandbox.vars())
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

    return {"status": "executed", "state": store.snapshot()}
