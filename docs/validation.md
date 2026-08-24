# Validation — what catches each class of failure

Validation is layered. Each layer catches failures the previous one cannot.
The LLM never executes anything, so every rejection below is a *safe* stop.

## Layer 0 — structural (Pydantic, `ir/models.py`)

Catches *shape* errors in the LLM's output:

| Failure class | Example | Result |
|---|---|---|
| Missing required field | `{"operation":"move","source":"people"}` | rejected |
| Unknown field | `{"operation":"move","banana":"hello"}` | rejected (`extra=forbid`) |
| Illegal operator | `condition.operator == ">>"` | rejected |
| Wrong value type | `value: {"nested": 1}` for a scalar | rejected |
| Wrong operation shape | `move` missing `destination` | rejected (discriminated union) |
| Status/payload mismatch | `complete` without `command` | rejected |
| Non-JSON output | prose instead of JSON | translator retries once, then rejects |

## Layer 1 — semantic (domain rules, `validator/semantic.py`)

Catches *meaning* errors that are still structurally valid:

| Failure class | Example | Result |
|---|---|---|
| Unknown source collection | `source: "users"` (alias not mapped) | rejected |
| Unknown destination collection | `destination: "moon"` | rejected |
| Immutable record id | `update … set: {"_id": 99}` | rejected |
| Non-numeric record id | `condition: _id = "1"` | rejected |
| Same source and destination | `people → people` | rejected |
| Invalid collection name | `create "2 fast"` | rejected |
| Duplicate collection | `create "people"` (exists) | rejected |

Fields are **schemaless** (matching MongoDB's document model): any field name
or value type is accepted, so there is no "unknown field" rejection. This was a
deliberate relaxation from an earlier fixed-schema prototype.

## Layer 2 — semantic reviewer (LLM #2, `experiments/review.py`)

Catches *faithfulness* errors the deterministic layers cannot see — the IR is
valid and meaningful, but misrepresents the instruction:

| Failure class | Example | Result |
|---|---|---|
| Off-by-one threshold | "at least 60" → `age > 60` | REJECTED |
| Reversed direction | "out of pension back to people" → `people → pension` | REJECTED |
| Wrong verb | "copy" → `operation: move` | REJECTED |
| Wrong operator | "younger than 60" → `age > 60` | REJECTED |
| Wrong field | "retire" → `set: {salary: 100000}` | REJECTED |
| Dropped exception clause | "…except people named David" → no exception | REJECTED |
| Invented threshold | "the old people" → `age > 60` | REJECTED |

Measured: **8/8** corrupted IRs detected; **1/20** false rejection (whose reason
text contradicted its own verdict).

## Translator hardening (`translator/llm.py`)

| Failure | Handling |
|---|---|
| DeepSeek returns non-JSON | one corrective retry, then error |
| JSON fails schema | one corrective retry with the validation error, then error |
| Stray trailing `}` after valid JSON | tolerant parse (first complete JSON value), schema still enforced |

## Evidence

These layers are exercised by the experiments: paraphrase convergence (2.1),
ambiguity detection (2.2), adversarial safety (2.3), and the reviewer (2.5).
In the pre-fix paraphrase run, every hallucination (literal collection names,
invented field `retired`, malformed JSON) was caught at Layer 0/1 — **0 wrong
executions**.
