"""LLM #2 — the semantic reviewer.

Given (instruction, IR), asks the model whether the IR completely and
faithfully captures the instruction. This is the "second LLM in the loop"
experiment: measuring whether LLM review catches semantically-valid-but-wrong
IRs that the deterministic validator cannot catch.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from translator.llm import _parse_json

_SYSTEM_PROMPT = """\
You are a strict semantic reviewer for a natural-language database system.
Given the user's original instruction and a proposed intermediate representation
(IR), decide whether the IR completely and faithfully captures the instruction.

Rules:
- APPROVED if the IR captures every part of the instruction and nothing more.
- REJECTED if anything is missing, wrong, ambiguous, or added.
- Pay special attention to: operator direction ("above" vs "at least"),
  thresholds, whether the operation matches the verb (move vs copy),
  source and destination, and clauses that were dropped.

Respond with exactly one JSON object, nothing else:
{"verdict": "APPROVED", "reason": "short explanation"}
"""


class Reviewer:
    """Second LLM: reviews a proposed IR against the original instruction."""

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

    def review(self, instruction: str, ir: dict[str, Any]) -> dict[str, str]:
        """Return {"verdict": APPROVED|REJECTED|ERROR, "reason": ...}."""
        if not self.api_key:
            return {"verdict": "ERROR", "reason": "DEEPSEEK_API_KEY is not set."}

        user = f'Instruction: "{instruction}"\n\nProposed IR: {json.dumps(ir)}'
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": self.temperature,
            "max_tokens": 512,
        }

        for attempt in range(2):
            try:
                response = self._client.post("/chat/completions", json=payload)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                return {"verdict": "ERROR", "reason": f"request failed: {exc}"}

            data = response.json()
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                return {"verdict": "ERROR", "reason": "unexpected API response shape"}

            try:
                raw = _parse_json(content)
                verdict = raw["verdict"]
                reason = raw.get("reason", "")
            except (json.JSONDecodeError, KeyError, TypeError):
                if attempt == 0:
                    continue
                return {
                    "verdict": "ERROR",
                    "reason": f"unparseable: {content[:150]!r}",
                }

            if verdict not in ("APPROVED", "REJECTED"):
                return {"verdict": "ERROR", "reason": f"unknown verdict: {verdict!r}"}
            return {"verdict": verdict, "reason": reason}

        return {"verdict": "ERROR", "reason": "retries exhausted"}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Reviewer":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
