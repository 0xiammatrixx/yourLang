# Paper skeleton — "A Validated Intermediate Representation for Natural-Language Database Instructions"

> Fill the narrative, keep the numbers. All figures below are measured from the
> runs saved in `results/`.

## 1. Introduction

- Problem in plain language: programming languages moved toward readability,
  yet developers still learn rigid syntax and language-specific constructs.
- One line on prior work (AIOS/CoRE, Linguine, NoviCode) — see `research-map.md`.
- The idea: LLM as a *probabilistic semantic front-end* over a formal IR.
- Contributions:
  1. an architecture with a strict deterministic boundary after the LLM,
  2. a tiny domain (database instructions) with a formally specified IR,
  3. an experimental evaluation of convergence, ambiguity, safety, and review
     against a direct-code-generation baseline.

## 2. Background

Short paragraphs each: programming languages, program synthesis,
natural-language programming, LLM code generation, intermediate representations.

## 3. Related Work

5–10 papers from `docs/research-map.md`. For each: what they do, what this
system does differently.

## 4. Proposed Architecture

```mermaid
flowchart LR
    U[Natural language] --> T["LLM translator (DeepSeek)"]
    T --> IR["Semantic IR (JSON, Pydantic)"]
    IR --> V["Validator: structural + semantic"]
    V -->|fail| Q[Clarification loop]
    Q --> T
    V -->|pass| C[Compiler → MongoDB plan]
    C --> R[Runtime → store]
```

- The LLM translates; it never executes; it cannot emit code.
- Two-layer validation: Pydantic (shape) + domain rules (meaning).
- Clarification loop grounded in missing IR fields (max 3 rounds).
- Optional LLM #2 reviewer between validation and compilation.

## 5. Implementation

- **Stack:** Python, DeepSeek API (`deepseek-chat`, `httpx`, no OpenAI SDK),
  Pydantic v2, pymongo (optional), pytest. No LangChain/agents/RAG.
- **IR:** 7 operations (`create`, `add`, `remove`, `move`, `copy`, `find`,
  `update`), 6 operators (`=`, `!=`, `>`, `<`, `>=`, `<=`), one wrapper
  `TranslationResult` with states `complete` | `needs_clarification`.
- **Translator:** JSON output mode, JSON Schema embedded in the system prompt,
  one-shot corrective retry, tolerant parsing of a stray trailing token,
  temperature 0.
- **Validator:** structural (Pydantic, `extra=forbid`, discriminated union) +
  semantic (`validator/semantic.py`: known collections, known fields, value
  types, source ≠ destination, name syntax).
- **Compiler:** IR → ordered plan of primitive MongoDB steps; `move` = find +
  delete_many + insert_many with a `{"$ref"}` data dependency.
- **Runtime:** `MemoryStore` (deterministic, used by all experiments) and
  `MongoStore` (pymongo) behind one interface.
- 61 unit tests + 2 live integration tests.

## 6. Evaluation

Setup: fresh seeded store per case; temperature 0; canonical IR comparison
(60 ≡ 60.0); baseline runs in a sandbox exposing only `db_*` functions;
correctness judged by final store state vs. the reference state produced by
running the expected IR through our own pipeline.

### 6.1 Paraphrase convergence (H1)

4 intents × 5 phrasings (passives, idioms, different verbs).
**Result: 20/20 executed, 4/4 intents converged to the expected canonical IR.**

Also report the pre-fix run: 13/20 executed; every hallucinated output
(literal collection names `"users"`/`"everybody"`, invented field `retired`,
malformed JSON) was **caught by the validator — 0 wrong executions**.

### 6.2 Ambiguity and clarification (H2)

4 ambiguous instructions.
**Result: 4/4 asked (0 guesses); 4/4 completed to the correct IR after one
answer.** Questions named the missing IR field (e.g. `condition.value`).

### 6.3 Adversarial safety (H3)

5 adversarial instructions (contradictions, unknown collection, out-of-domain,
nonsense).
**First run: 2/5 unsafe (conflicting clauses silently dropped). After adding
a multi-clause prompt rule: 5/5 safe, 0 executed.** The system now rejects
conflicts with an explanation, e.g. *"conflicting clauses… please clarify the
intended operation."*

### 6.4 Baseline comparison (H3)

Same 29 cases through direct LLM → Python code (sandboxed).

| Metric | This system | Direct code |
|---|---|---|
| Paraphrase correctness (20) | **20/20** | 15/20 (3 runtime crashes) |
| Ambiguity: asked instead of guessed (4) | **4/4** | 2/4 |
| Adversarial: safe (5) | **5/5, every run** | varies (2 unsafe in one run) |

Direct-code failure modes: runtime crashes (`KeyError: '_id'`), state
corruption (find-then-insert without delete), and silent data corruption —
*"move everyone over 60 to the moon"* became `db_update({"$set": {"country":
"moon"}})`.

### 6.5 Semantic reviewer, LLM #2 (H4)

20 correct (instruction, IR) pairs + 8 corrupted pairs that are structurally
and semantically valid but wrong (off-by-one threshold, reversed direction,
wrong verb, wrong operator, wrong field, dropped exception, swapped threshold,
invented threshold).
**Result: 8/8 corrupted detected; 1/20 false rejection — whose reason text
contradicted its own verdict ("so it should be approved… So I'll approve") yet
returned REJECTED.**

## 7. Discussion

- Where it works: single-clause, single-condition instructions; convergence is
  strong; the validator converts LLM nondeterminism into catchable errors.
- Where it fails: multi-clause instructions (fixed by prompt rule, but the IR
  has no way to express compound constraints or exceptions — future work);
  no joins/composition yet; single domain.
- Security/reliability: safety comes from the deterministic layer, not from
  the model; direct code generation is probabilistically safe, this system is
  safe by construction (0 unsafe across all runs).
- LLM reviewer adds safety but is itself probabilistic (1 false rejection with
  self-contradicting reasoning).
- Threats to validity: temperature 0, one model (deepseek-chat), small
  benchmark, paraphrases written by the authors; cross-model and larger-scale
  replications are future work.

## 8. Conclusion

- Demonstrated: an LLM front-end + canonical IR + deterministic
  validation/compilation achieves paraphrase convergence (20/20), asks instead
  of guessing (4/4), is safe on adversarial input (5/5), and outperforms
  direct code generation on correctness (20/20 vs 15/20) while eliminating
  silent corruption.
- Future work: compound conditions and exceptions in the IR, multi-domain
  front-ends, integrating the reviewer into the pipeline with cost analysis,
  larger benchmark sets, other models.
