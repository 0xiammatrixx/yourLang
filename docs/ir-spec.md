# Intermediate Representation — formal specification

The IR is the deterministic boundary of the system. The LLM maps natural
language ONTO these structures; validation, compilation, and execution after
this point are pure code.

## Top level: `TranslationResult`

Every LLM response must match exactly one of two states:

| Field | Type | Notes |
|---|---|---|
| `status` | `"complete" \| "needs_clarification" \| "needs_confirmation"` | discriminates the payload |
| `command` | `Operation \| list[Operation] \| null` | a single operation, or an array for multi-task instructions |
| `clarification` | `ClarificationRequest \| null` | required iff `status == "needs_clarification"` or `"needs_confirmation"` |

Invariants (enforced by a model validator):
- `complete` ⇒ `command` present, `clarification` absent
- `needs_clarification` ⇒ `clarification` present, `command` absent
- `needs_confirmation` ⇒ BOTH `command` (best guess) and `clarification` (the
  "did you mean …?" question) present

## Operations (discriminated union on `operation`)

All operations forbid unknown fields (`extra="forbid"`).

| Operation | Required fields | Example |
|---|---|---|
| `create` | `destination` | `{"operation":"create","destination":"archive"}` |
| `add` | `destination`, `records` (≥1) | insert records into a collection |
| `remove` | `source`, `condition` (optional), `limit` (optional) | delete matching records; `limit` caps how many |
| `move` | `source`, `destination`, `condition` | move matching records to destination |
| `copy` | `source`, `destination`, `condition` | copy without deleting source |
| `find` | `source`, `condition` | return matching records (read-only) |
| `update` | `source`, `condition`, `set` (≥1) | `set` maps field → value |

`condition` may be `null` on `remove`/`move`/`copy`/`find`/`update`, meaning
**match all records** — this is how "everybody"/"all" with no other criterion is
represented. (A null condition compiles to an empty MongoDB filter `{}`.)

## `Condition`

| Field | Type | Domain |
|---|---|---|
| `field` | `str` | a known field of the source collection; `_id` (or `id`) references the unique numeric record id |
| `operator` | enum | `=` `!=` `>` `<` `>=` `<=` |
| `value` | `int \| float \| str` | type must match the field's declared type (a whole number for `_id`) |

## `ClarificationRequest`

| Field | Type | Notes |
|---|---|---|
| `message` | `str` | the question to ask the user |
| `missing` | `list[str]` | which IR fields could not be determined |

## Canonical comparison rule

Two IRs are *equal* iff their canonical JSON forms are equal, where
canonicalization converts any integral float to an int (`60.0` → `60`) and
sorts object keys. This is how the paraphrase-convergence experiment decides
that two phrasings produced "the same" IR.

## Machine-readable schema

`ir/schema.py` exports the full JSON Schema (`TranslationResult.model_json_schema()`);
the same schema is embedded in the translator's system prompt.
