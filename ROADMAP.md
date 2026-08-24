# Roadmap — NL → LLM → Semantic IR → Compiler

**Core research question**

> Can an LLM reliably translate semantically equivalent natural-language instructions into the same executable intermediate representation (IR), while detecting ambiguity and requesting clarification when required?

**Thesis of the project**

> An LLM acts as a *probabilistic semantic front-end* mapping unconstrained natural language onto a formally specified IR. After that boundary, ordinary deterministic computer science (validation, compilation, execution) takes over.

---

## Part 0 — Research positioning (read, don't code)

**Goal:** Establish that this is a real research area, position the work against existing approaches, and fix the research question before writing any code.

### 0.1 Literature map (5–8 targeted papers)

Read each paper *for a specific reason*, not line-by-line.

| # | Paper | Why read it | Extraction checklist |
|---|-------|-------------|----------------------|
| 1 | Systematic review (2014–2024) | Use as a **map only** — "NL → program synthesis has existed for years; LLMs changed the field" | Nothing else initially |
| 2 | **AIOS Compiler / CoRE** | Most similar system: LLM as interpreter of NL programs | What goes in? What comes out? Where does the LLM sit? What representation? How is execution done? How is ambiguity handled? How is it evaluated? What did they NOT solve? |
| 3 | **Linguine** | The programming-language side: NL-inspired language with formal compiler pipeline (parser → clause graph → typed IR → verification → Python) | Why did they need a formal grammar? Could an LLM replace the front end while the formal backend is preserved? |
| 4 | **NoviCode** | Non-programmers describing programs in everyday language; evaluates whether programs *execute correctly* (not just syntactically) | How do they measure executability? What inputs do non-programmers use? |
| 5 | IR / code-generation paper(s) | Evidence that intermediate representations between NL and code matter; NL itself can be a strong IR; recent work on canonical IRs | What IR choices were compared? What metrics improved? |

**Deliverable:** A half-page of notes per paper using the checklist. ✅ Done when each checklist row has an answer (or an explicit "paper does not address this").

### 0.2 One-page research map

Create a single-page table (this may later go into the paper):

| Existing approach | What it does | Problem / limitation |
|---|---|---|
| Traditional programming languages | Human writes formal syntax | Syntax burden on the human |
| Natural-language → code | LLM directly generates executable code | Hallucination / unreliability |
| Natural-language programming | Restricts language/grammar | Human still has to learn rules |
| AIOS / CoRE | LLM interprets NL programs | Different architecture/domain |
| Linguine | NL-like formal language + compiler | Requires controlled language/grammar |
| **Your proposed system** | NL → LLM → validated semantic IR → deterministic compiler | Reliability must be tested |

**Deliverable:** `docs/research-map.md` with this table.

### 0.3 Contribution & research question

Write it down exactly (one paragraph each):

- **Claim:** "I propose a natural-language-first programming architecture in which an LLM serves as a semantic translation layer between unrestricted user language and a deterministic intermediate representation." *(Do NOT claim to have invented NL programming.)*
- **Question:** "Can an LLM reliably translate semantically equivalent natural-language instructions into the same executable IR, while detecting ambiguity and requesting clarification when required?"
- **Architecture decision:** "The LLM must NOT generate executable code; it produces structured semantics only. The LLM must NOT execute database commands."

**Deliverable:** `docs/research-question.md`.

### 0.4 Tiny language design (one domain only)

Start with **database manipulation** (not HTML, not full apps, not Python).

- Operations: `create`, `add`, `remove`, `move`, `copy`, `find`, `update`
- Conditions: `age above 60`, `name equals David`, `salary below 100000`, `country is Nigeria`
- Operators: `=`, `!=`, `>`, `<`, `>=`, `<=`

**Deliverable:** A one-page spec of what version 0.1 can express. Explicitly list what it CANNOT express (out of scope).

### 0.5 IR specification (the core artifact)

Formally define the IR. Example:

```json
{
  "operation": "move",
  "source": "people",
  "destination": "pension",
  "condition": {
    "field": "age",
    "operator": ">",
    "value": 60
  }
}
```

Formally specify every field:

```
operator ∈ {equals, not_equals, greater_than, less_than, greater_or_equal, less_or_equal}
```

State the invariant: *different English sentences with the same meaning MUST map to the same IR.*

**Deliverable:** `docs/ir-spec.md` — field tables, allowed values, examples, and an explicit JSON Schema.

---

## Part 1 — Build the prototype (a few hundred lines)

**Tech stack (and only this):** Python + DeepSeek API (small `httpx` client against DeepSeek's OpenAI-compatible endpoint — no OpenAI SDK) + Pydantic + pymongo + pytest.
**Explicitly avoid:** LangChain, LangGraph, RAG, vector DBs, agents, fine-tuning, custom models, Kubernetes, microservices.

**Build order matters: IR first, LLM second.**

```
nl-programming/
├── main.py                  # the pipeline: translate → validate → clarify | compile → execute
├── translator/
│   └── llm.py               # NL → IR (the ONLY place the LLM appears)
├── ir/
│   ├── models.py            # Pydantic models
│   └── schema.py            # JSON Schema export
├── validator/
│   ├── structural.py        # "is it shaped correctly?"
│   └── semantic.py          # "does it mean something valid in this domain?"
├── compiler/
│   └── mongodb.py           # IR → MongoDB query, pure Python, NO LLM
├── runtime/
│   └── database.py          # executes the compiled query
├── tests/
│   ├── paraphrases.json
│   ├── ambiguity.json
│   └── contradictions.json
└── README.md
```

### 1.1 IR models (Pydantic) — build FIRST

```python
class Condition(BaseModel):
    field: str
    operator: Literal[">", "<", ">=", "<=", "=", "!="]
    value: int | str | float

class MoveOperation(BaseModel):
    operation: Literal["move"]
    source: str
    destination: str
    condition: Condition
```

✅ **Done when:** valid JSON passes, malformed JSON fails, and `schema.py` can emit the JSON Schema that will be handed to the LLM.

### 1.2 LLM translator — build SECOND

- **System prompt:** "Translate natural-language database instructions into the provided semantic representation. Do not execute commands. Do not invent missing information. If a required property cannot be determined, indicate that clarification is required."
- Give the LLM the JSON Schema and use DeepSeek's JSON output mode (`response_format: {"type": "json_object"}`) so it reliably returns JSON.
- Note: DeepSeek does not offer OpenAI-style schema-constrained generation, so Pydantic stays the enforcement layer — the LLM response is parsed into `TranslationResult` and structurally validated on our side.
- API key comes from `.env` (`DEEPSEEK_API_KEY`), never hard-coded.
- Input → `translator/llm.py` → IR object.

✅ **Done when:** "Move everyone aged above 60 to collection pension." returns the exact IR from 0.5.

### 1.3 Structural validator

- "Is this shaped correctly?" — handled by Pydantic: operation exists, source/destination present, condition present, operator legal, value type correct.

✅ **Done when:** `{"operation": "move", "banana": "hello"}` is rejected with a precise error.

### 1.4 Semantic validator (two-layer validation!)

Schema-valid ≠ semantically valid. Write plain Python rules:

```python
VALID_COLLECTIONS = {"people", "pension", "employees"}

if command.source not in VALID_COLLECTIONS:
    raise ValueError("Unknown source collection")
```

Additional checks: does `age` exist in `people`? Is it numeric? Is the operation allowed on these collections? Does the user have permission?

✅ **Done when:** structurally valid but nonsense IRs (unknown collections, wrong-typed fields) are rejected.

### 1.5 Compiler (IR → MongoDB) — deterministic, boring by design

Pure Python, no LLM:

```python
def compile_move(command):
    return {
        "$match": {
            command.condition.field: {"$gt": command.condition.value}
        }
        # ...destination handling
    }
```

✅ **Done when:** every supported operation has a deterministic mapping IR → MongoDB operation, and it's covered by a pytest.

### 1.6 Runtime

Connects to MongoDB and executes compiled operations. The LLM never touches this.

### 1.7 Main pipeline + clarification loop

```python
user_input
    ↓
translate()          # LLM → IR
    ↓
validate()           # structural + semantic
    ↓
if invalid or ambiguous:
    clarify()        # ask the user, then re-translate
else:
    compile() → execute()
```

- The LLM, when unable to complete a required field, must return a clarification request instead of guessing.
- Loop: "Move all the old people to pension." → system asks for threshold → user says "60" → full IR → validate → compile → execute.

✅ **Done when:** the happy path runs end-to-end from one English sentence to a real MongoDB operation, and the ambiguity loop can complete a conversation.

---

## Part 2 — Experiments (this is the actual research)

### 2.1 Paraphrase convergence (central experiment)

Run these through the pipeline and compare IRs:

- A: "Move everyone aged above 60 to pension."
- B: "Put all people older than sixty in the pension collection."
- C: "Transfer users whose age exceeds 60 into pension."
- D: "Take everybody over the age of 60 and move them to pension."
- E: "Pension should contain all users with age greater than 60."

**Expected result:** A–E → **identical IR**. Measure convergence rate over N paraphrases (e.g., 10 intents × 5 phrasings = 50 cases).

✅ **Done when:** convergence rate is measured and reported.

### 2.2 Ambiguity detection & clarification

Cases where the IR cannot be completed:

- "Move all the old people to pension." → must ask for threshold, then continue.
- "Move people to pension." → must detect missing condition.

✅ **Done when:** the system asks instead of guessing, and a measured percentage of ambiguous inputs are correctly flagged.

### 2.3 Deliberately break it (adversarial cases)

- "Move people aged 60 to pension, but don't move people over 70." → contradiction detection?
- "Move everyone over 60 to pension and make sure nobody older than 60 goes there." → constraint understanding?
- Unknown collections, unknown fields, out-of-domain requests ("send an email").

✅ **Done when:** each adversarial case has a defined expected behavior (reject / clarify / correct IR) and a test in `tests/`.

### 2.4 Baseline comparison: direct code generation vs your pipeline

```
Natural Language → LLM → MongoDB code          (baseline)
Natural Language → LLM → Semantic IR → Validator → MongoDB   (yours)
```

Measure both on the same cases:

- Correctness
- Invalid outputs
- Execution success
- Paraphrase consistency
- Ambiguity detection
- Number of clarification questions

✅ **Done when:** a comparison table exists — you are now testing a hypothesis, not just demonstrating an idea.

### 2.5 (Optional, later) Second LLM as semantic reviewer

```
USER → LLM #1 (translator) → IR → deterministic validator → LLM #2 (reviewer) → APPROVED? → compile | clarify
```

Prompt LLM #2: "Original request X, proposed IR Y — does Y completely and faithfully capture X?" Add this only as an experiment, never as the starting design.

---

## Part 3 — Paper & portfolio

### 3.1 Paper structure (only after the prototype works)

1. **Introduction** — problem in plain language; programs moved toward readability, yet syntax burden remains.
2. **Background** — programming languages, program synthesis, NL programming, LLM code generation, IRs (very short).
3. **Related Work** — 5–10 relevant papers: "here's what they do, here's what I do differently."
4. **Proposed Architecture** — the diagram:

   ```
   Natural Language → LLM (semantic translator) → Semantic IR → Validator
                       → (FAIL: clarification) / (PASS: Compiler → Database)
   ```

5. **Implementation** — technologies, IR schema, LLM, validator, compiler, database.
6. **Evaluation** — paraphrase experiment, ambiguity experiment, baseline comparison, results.
7. **Discussion** — where it works/fails; security; reliability; hallucination; complex programs.
8. **Conclusion** — what was demonstrated, what future work should investigate.

### 3.2 Repository for the application (e.g., Padua)

A working GitHub repo is stronger evidence than a motivation letter:

- Working prototype with the pipeline above
- Experiments and benchmark cases (`tests/*.json`)
- A short research paper in the repo
- `README.md` with: research question, architecture diagram, how to run, results table

---

## Immediate next steps (in order)

1. Read **AIOS / CoRE** (checklist in 0.1).
2. Read **Linguine** (front-end/back-end question in 0.1).
3. Read **NoviCode** (executability evaluation).
4. Read the **IR / code-generation paper(s)** (IR choices + metrics).
5. Write `docs/research-map.md` (the table).
6. Write `docs/research-question.md` (claim + question + architecture decision).
7. Specify the mini-language (0.4) and the IR (0.5).
8. Build Part 1 in order: IR models → LLM translator → validators → compiler → runtime → pipeline.
9. Run Part 2 experiments.
10. Write the paper (Part 3).

**Golden rules carried through every step:**
- The LLM translates; it never executes.
- Deterministic validation and compilation happen *after* the LLM — that boundary is the research contribution.
- Start with one domain (databases), one schema, a few operations.
- Avoid all LLM-framework tooling (LangChain, agents, RAG) — it obscures the research.

---

## Build log

- [x] Part 1.1 — IR models + JSON Schema export (`ir/`)
- [x] Part 1.2 — DeepSeek translator (`translator/llm.py`)
- [x] Part 1.3 — Semantic validator (domain rules) (`validator/semantic.py`)
- [x] Part 1.4 — Compiler (IR → MongoDB) (`compiler/mongodb.py`)
- [x] Part 1.5 — Runtime (execution) (`runtime/database.py`)
- [x] Part 1.6 — Main pipeline + clarification loop (`main.py`)
- [x] Part 2.1 — Paraphrase convergence experiment (`experiments/run_paraphrases.py`)
- [x] Part 2.2 — Ambiguity experiment (`experiments/run_ambiguity.py`)
- [x] Part 2.3 — Adversarial cases (`experiments/run_adversarial.py`)
- [x] Part 2.4 — Baseline comparison (direct code generation) (`experiments/run_baseline.py`)
- [x] Part 2.5 — Semantic reviewer (LLM #2) (`experiments/run_review.py`)
- [x] Part 3 — Paper skeleton + portfolio docs (`README.md`, `docs/`)
