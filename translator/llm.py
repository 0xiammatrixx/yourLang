"""DeepSeek translator: natural language -> IR (TranslationResult).

This is the ONLY place an LLM appears in the system.

- In:  unrestricted natural-language instruction (a string).
- Out: a fully validated `TranslationResult` (the IR).

The translator maps language onto the IR. It never executes anything, and
its output is always checked against the Pydantic models before it leaves
this module — that is the deterministic boundary of the architecture.

DeepSeek specifics:
- Uses DeepSeek's OpenAI-compatible /chat/completions endpoint via httpx
  (no OpenAI SDK).
- Uses JSON output mode (response_format: {"type": "json_object"}).
- DeepSeek does not do schema-constrained generation, so Pydantic stays the
  enforcement layer: any output that does not match the IR raises
  TranslationError instead of propagating.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from pydantic import ValidationError

from ir.models import TranslationResult
from ir.schema import json_schema_string

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Accept .env at the project root or in ir/ (both are git-ignored).
for _candidate in (PROJECT_ROOT / ".env", PROJECT_ROOT / "ir" / ".env"):
    if _candidate.exists():
        load_dotenv(_candidate, override=False)

_SYSTEM_PROMPT = """\
You are the natural-language front end of a database system. Translate the user's
natural-language database instruction into the exact JSON representation described
by the JSON Schema below.

Rules:
1. Never execute anything; you only produce JSON.
2. The instruction may be written in any natural language (English, French,
   Spanish, …). Translate its MEANING into the IR; IR field names, collection
   names, and operator symbols stay in English.
3. Infer collections from context. Generic words that refer to the people
   collection — "users", "everyone", "everybody", "anyone", "anybody",
   "persons", and similar — map to "people", unless another collection is
   explicitly named. Map words to operators:
   "above/more than/over/exceeds" -> ">", "at least" -> ">=",
   "below/less than/under" -> "<", "at most" -> "<=",
   "equals/is" -> "=", "not equal" -> "!=".
4. Scope: if the instruction explicitly says all/everyone/everybody/everything
   with no other criterion, set "condition" to null to match ALL records. If no
   quantifier and no condition is given (e.g. "move people to pension"), the
   scope is unclear — use "needs_confirmation" or "needs_clarification".
5. Verb → operation: "copy/add/put/duplicate … without deleting or removing
   from the source" maps to "copy" (the source is left unchanged).
   "move/transfer" maps to "move" (source records are deleted). Never treat the
   phrase "without deleting" as a filter on a "deleted" status or field.
6. Ambiguity is the default, not the exception. If any word or phrase could be
   interpreted in more than one way that changes the IR (for example "retire"
   could mean set status to "retired", move records to "pension", or delete
   them), do NOT silently pick one meaning. Set "status" to "needs_confirmation":
   return your best-guess "command" AND a "clarification" whose "message" asks
   the user to confirm while naming the alternative(s), e.g. "Did you mean: set
   their status to retired? Or move them to pension?".
7. If a required field cannot be determined and you do NOT have a reasonable
   guess (e.g. an undefined word such as "old"), set "status" to
   "needs_clarification" and list the missing field names in "missing".
8. If the instruction does not match any supported operation, use
   "needs_clarification".
9. Respond with exactly one JSON object matching the schema; no prose.
10. For "update", set fields only among the known fields of the source collection
    (name, age, country, salary, status). If the instruction uses an explicit
    "mark X as Y" / "set X to Y" phrase, map Y onto the most appropriate known
    field (e.g. "mark as retired" → status = "retired"). Never invent a new
    field named after the value.
11. If the instruction contains several clauses joined by "but", "and", "unless"
    or similar (for example "move X, but don't move Y"), every clause must be
    captured by the representation. If clauses conflict with each other or cannot
    all be represented, set "status" to "needs_clarification" and explain the
    conflict in "message".

Examples:
Instruction: "Move all employees whose salary is below 30000 to pension."
Response: {"status": "complete", "command": {"operation": "move", "source": "employees",
"destination": "pension", "condition": {"field": "salary", "operator": "<", "value": 30000}}}

Instruction: "Remove all the heavy users."
Response: {"status": "needs_clarification", "clarification": {"message": "What makes a
user heavy?", "missing": ["condition.field", "condition.value"]}}

Instruction: "Move all the seniors to pension."
Response: {"status": "needs_confirmation", "command": {"operation": "move", "source": "people",
"destination": "pension", "condition": {"field": "age", "operator": ">", "value": 60}},
"clarification": {"message": "Did you mean: move everyone over 60 to pension?", "missing": ["condition.value"]}}

Instruction: "Add everybody to the employees collection without deleting them from the previous collection."
Response: {"status": "complete", "command": {"operation": "copy", "source": "people",
"destination": "employees", "condition": null}}

Instruction: "Retire everyone with a salary above 100000."
Response: {"status": "needs_confirmation", "command": {"operation": "update", "source": "people",
"condition": {"field": "salary", "operator": ">", "value": 100000},
"set": {"status": "retired"}},
"clarification": {"message": "Did you mean: set their status to retired? Or move them to pension?", "missing": []}}

JSON Schema:
{schema}
"""


def _build_system_prompt() -> str:
    # .replace, not .format: the prompt contains literal JSON braces.
    return _SYSTEM_PROMPT.replace("{schema}", json_schema_string())


def _parse_json(content: str) -> Any:
    """Parse model output as JSON, tolerating a stray trailing token.

    DeepSeek occasionally appends a redundant closing brace to an otherwise
    valid object. raw_decode accepts the first complete JSON value; the
    Pydantic models still enforce the schema strictly afterwards.
    """
    try:
        return json.loads(content)
    except json.JSONDecodeError as first_error:
        try:
            value, _ = json.JSONDecoder().raw_decode(content)
        except json.JSONDecodeError:
            raise first_error
        return value


class TranslationError(Exception):
    """The LLM output could not be turned into a valid IR.

    Causes: missing API key, HTTP failure, non-JSON output, or JSON that
    fails structural validation against the IR models.
    """


class Translator:
    """Thin DeepSeek chat client that returns validated IR objects."""

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
        self._last_content: str | None = None
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=timeout,
            transport=transport,
        )

    def translate(self, instruction: str) -> TranslationResult:
        """Translate one instruction into a validated IR object."""
        if not self.api_key:
            raise TranslationError(
                "DEEPSEEK_API_KEY is not set. Copy .env.example to .env and "
                "add your key."
            )

    def _call(self, instruction: str, correction: str | None = None) -> str:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": instruction},
        ]
        if correction and self._last_content:
            messages.append({"role": "assistant", "content": self._last_content})
            messages.append({"role": "user", "content": correction})

        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": self.temperature,
            "max_tokens": 2048,
        }

        try:
            response = self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TranslationError(f"DeepSeek request failed: {exc}") from exc

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise TranslationError(
                f"Unexpected API response shape: {json.dumps(data)[:300]!r}"
            ) from exc
        self._last_content = content
        return content

    def translate(self, instruction: str) -> TranslationResult:
        """Translate one instruction into a validated IR object.

        Retries once with a corrective message when the model's output is not
        valid JSON or does not match the IR schema.
        """
        if not self.api_key:
            raise TranslationError(
                "DEEPSEEK_API_KEY is not set. Copy .env.example to .env and "
                "add your key."
            )

        correction: str | None = None
        for attempt in range(2):
            content = self._call(instruction, correction)
            try:
                raw = _parse_json(content)
            except json.JSONDecodeError:
                if attempt == 0:
                    correction = (
                        "Your previous response was not valid JSON. Respond with "
                        "exactly one JSON object matching the schema, nothing else."
                    )
                    continue
                raise TranslationError(
                    f"Model did not return valid JSON: {content[:200]!r}"
                )

            try:
                return TranslationResult.model_validate(raw)
            except ValidationError as exc:
                if attempt == 0:
                    correction = (
                        f"Your previous response did not match the required JSON "
                        f"schema: {exc}. Follow the schema exactly and try again."
                    )
                    continue
                raise TranslationError(
                    f"Model output failed structural validation: {exc}"
                ) from exc

        raise TranslationError("Retries exhausted.")  # pragma: no cover

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Translator":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def translate(instruction: str) -> TranslationResult:
    """One-shot convenience: translate a single instruction."""
    with Translator() as translator:
        return translator.translate(instruction)
