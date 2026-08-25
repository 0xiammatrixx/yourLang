# A Validated Semantic Boundary Between Natural Language and Database Execution

## Abstract

Programming systems that accept instructions in unrestricted natural language
would remove the syntax barrier, but natural language has no stable mapping from
words to computational meaning: "remove the employees" admits several readings,
each with a different effect on the data. This paper presents a
database-instruction system in which a large language model (LLM) acts as a
probabilistic front end that translates instructions into a formally specified,
JSON-based intermediate representation (IR), while validation, compilation, and
execution are performed entirely by deterministic code. The LLM never emits
executable code and never executes; the IR is the boundary. Five controlled
experiments, including a direct code-generation baseline, evaluate that
boundary on a database-instruction domain. Semantically equivalent phrasings
converged to one canonical IR in 20/20 cases; ambiguous instructions were met
with grounded clarification rather than guesses in 4/4 cases; adversarial
instructions were handled safely in 5/5 cases, with zero unsafe executions
across every run, while the baseline executed unsafe operations in 6 of 25
adversarial cases (audited across 5 runs) and crashed twice. On the shared
paraphrase task the system scored 20/20 against the baseline's 14–16/20, and a
second LLM reviewing (instruction, IR) pairs detected all 8 corrupted-but-valid
IRs. The evidence indicates that safety and reliability come from the
deterministic boundary, not from the model.

## 1. Introduction

Programming languages have spent decades moving toward human readability: from
machine code to structured programming, from manual memory management to
garbage collection, and from verbose annotations to type inference. One
boundary, however, has not moved. Developers must still learn rigid syntax and
language-specific constructs, and programs remain opaque to non-programmers.
Given the fluency of modern large language models (LLMs), the tempting question
is "what if English were a programming language?" Building the system described
in this paper showed that this is the wrong question. English is not a
programming language with slightly ambiguous surface syntax over precise
semantics; it is a language in which the same words carry several incompatible
computational meanings, and the listener is expected to resolve them from
context.

What the system exposed is that natural language gives no stable mapping from
words to computation. "Remove the employees." can mean delete the employee
records, remove employees from a group, drop the `employees` collection
entirely, remove employees from some other collection, or simply exclude them
from a query result — one sentence, several different database effects. "Move
the old people to pension." carries uncertainty in every token: "old" (which
field? which threshold?), "people" (which collection?), "pension" (a
destination collection, a field, or a status?), and "move" (copy then delete,
update a field, or transfer a reference?).

These ambiguities are not noise to be eliminated; they are a property of
language that a programming interface must manage. We therefore make the
following claim: *LLMs can provide a flexible natural-language interface to a
programming system, but their probabilistic interpretation must be bounded by a
deterministic semantic representation and execution layer.* In the system
presented here, the LLM has exactly one job — translating unrestricted natural
language into a formally specified intermediate representation (IR), a
structured JSON document defined by a strict schema. Everything downstream of
the IR — validation, compilation to a database plan, and execution — is
deterministic code. The LLM never emits executable code and never executes
anything.

The research question follows directly: *Can a validated intermediate
representation provide a reliable boundary between unconstrained
natural-language instructions and deterministic program execution?* We answer
it empirically with five controlled experiments on a database-instruction
domain: paraphrase convergence, ambiguity detection and clarification,
adversarial safety, a comparison against a direct code-generation baseline,
and a second-LLM semantic review. All figures are measured from saved run data
and audited by script.

The remainder of the paper is organized as follows. §2 gives background; §3
positions this work against related approaches; §4 states the hypotheses; §5
presents the architecture and its deterministic boundary; §6 describes the
implementation; §7 documents the design evolution — nine observed failures and
their structural fixes; §8 reports the evaluation; §9 discusses the resulting
failure taxonomy, architectural insights, and limitations; §10 concludes.

**Contributions:**
  1. an architecture with a strict deterministic boundary after the LLM — the
     LLM translates, never executes, and cannot emit code;
  2. a formally specified IR for a database-instruction domain
     (`docs/ir-spec.md`);
  3. an ambiguity protocol with two modes — open clarification when no guess
     exists, and propose-then-confirm ("did you mean X or Y?") when a word has
     multiple plausible readings — without any closed dictionary or rule module
     resolving word meanings (the prompt carries only finite structural
     mappings and a few illustrative examples);
  4. a multilingual front end that maps any natural language (English, French,
     …) onto the same IR;
  5. an empirical **failure taxonomy** of natural-language-programming failure
     modes, each mapped to the architectural layer that catches it (§9);
  6. an experimental evaluation (five experiments, 92 tests) against a
     direct-code-generation baseline.

## 2. Background

**Programming languages.** Programming languages abstract over machine
behavior, and the industry's direction of travel has been toward readability
and abstraction. But the syntax barrier remains absolute: a program is only a
program if it parses, and only correct if it type-checks. The human adapts to
the language, not the reverse.

**Program synthesis and semantic parsing.** Two long-standing research lines
attempt to remove the syntax burden from the other direction. Program synthesis
constructs programs from examples or specifications; semantic parsing maps
sentences onto executable logical forms, with learned grammars and
combinatory-categorial or lambda-calculus targets [9, 10]. Both traditions
demonstrate that natural language can be mapped to formal meaning — but they
either constrain the input language or aim the output at a fixed formal
language, and they do not offer an interactive protocol for what to do when a
sentence is ambiguous.

**Natural-language programming.** A complementary line treats natural language
itself as the programming notation: interpreters for natural-language programs
[1], and controlled natural languages with formal semantics, type systems, and
compiler pipelines [2]. These systems trade expressiveness for soundness — the
language is restricted until a classical pipeline can reason about it.

**LLM code generation.** LLMs trained on code generate executable programs
directly from natural-language descriptions [6, 7], surveyed comprehensively in
the NL2Code literature [5]. Direct generation is remarkably capable but
probabilistic end to end: nothing between the model's output and execution
guarantees that the generated code means what the user said, a gap that
execution-based evaluations make measurable [3].

**Intermediate representations.** Compilers have always centered on IRs that
separate meaning from surface syntax. This work adopts that idea at the
human–machine boundary: a canonical IR between unrestricted natural language
and deterministic execution, with the additional, deliberately simple step that
the IR is the only artifact the probabilistic component may produce.

Throughout this paper we use the database terminology of the implemented
domain: a **collection** corresponds to a table; a **record** to a row,
document, or item; and a **field** to a column or attribute. Records carry a
unique `_id`.

## 3. Related Work

**Surveys and the field map.** Hou et al. [4] systematically review 395 papers
on LLMs for software engineering (2017–2024), and Zan et al. [5] survey 27
large language models for NL2Code. We use these as the field map rather than as
competitors: they catalog end-to-end generation systems, none of which is
organized around a validated semantic boundary of the kind evaluated here.

**Semantic parsing and structured intermediates.** Zettlemoyer and Collins [9]
learn to map sentences to lambda-calculus logical forms with probabilistic
combinatory categorial grammars; Liang [10] defines dependency-based
compositional semantics for the same goal. In text-to-SQL, RAT-SQL [8] builds a
relation-aware intermediate encoding between question and query. These works
show that structured meanings can sit between language and execution — but the
structured artifact is the *output* of a learned parser that then becomes the
program itself; ambiguity handling is not part of the interface, and the input
language is constrained to the domain's grammar. Here the IR is instead a
*validation boundary*: the model proposes it, deterministic code checks it, and
an interactive protocol resolves whatever the model cannot determine.

**Direct LLM code generation.** Codex [6] and the MBPP line of work [7]
generate executable code directly from natural language, and this remains the
dominant paradigm. NoviCode [3] shows that descriptions written by
non-programmers are still beyond current text-to-code models, and evaluates
programs by whether they *execute correctly* rather than whether they look
right. These systems put the LLM on both sides of the trust boundary: the model
both interprets the instruction and produces the executable artifact, so a
semantic error is executable by construction. This work removes the second
role: the LLM cannot produce code at all.

**LLM as interpreter.** The AIOS Compiler / CoRE [1] positions an LLM as the
interpreter of natural-language programs and agent flows, unifying natural
language, pseudocode, and flow programming under one representation. The
interpreter is the model itself, so execution remains probabilistic. Here,
interpretation stops at the IR; from that point on the "interpreter" is
deterministic Python and MongoDB operations.

**Controlled natural language with formal semantics.** Linguine [2] is the
closest architectural relative: a natural-language-inspired language with
anaphoric constructs, referent tracking, a Hindley–Milner-style type system,
and a compiler pipeline (lexing → clause graph → typed IR → verification →
code) that proves properties such as unambiguous pronoun resolution. Its
soundness comes from fixing the language. We take the complementary trade: the
language stays **unrestricted**, soundness is replaced by *validation* — wrong
meanings are caught, not proved absent — and the unresolved remainder of
natural language is handled by clarification and confirmation protocols.

In summary, prior approaches sit at two poles: the LLM emits executable code
directly [1, 3, 6, 7], or the language is fixed and controlled so that a formal
pipeline can be built [2, 9, 10]. This work occupies the position in between:
the language remains unrestricted, and all determinism is moved behind a formal
IR boundary — and that boundary is the thing evaluated.

## 4. Research Question and Framing

- The project began from: "Can English replace programming syntax?"
- Building the system moved the question: **"Can a validated intermediate
  representation provide a reliable boundary between unconstrained
  natural-language instructions and deterministic program execution?"**
- The shift matters: ambiguity is not a bug to eliminate but a property of
  language to be *managed*. The engineering problem is deciding, at every point,
  where interpretation stops being probabilistic.
- Hypotheses (from `docs/research-question.md`):
  - **H1 (convergence):** semantically equivalent phrasings map to one canonical IR.
  - **H2 (ambiguity):** when IR fields cannot be determined, the system asks instead of guessing.
  - **H3 (safety):** the deterministic boundary prevents execution of wrong commands, unlike direct code generation.
  - **H4 (review):** a second LLM reviewing (instruction, IR) pairs catches valid-but-wrong IRs.
  - **H5 (confirmation):** words with multiple plausible readings trigger a best-guess + confirm instead of a silent choice.

## 5. Proposed Architecture

```mermaid
flowchart LR
    U[Natural language] --> T["LLM translator<br/>(DeepSeek)"]
    T --> IR["Semantic IR<br/>(JSON + Pydantic)"]
    IR --> P["Ambiguous word?<br/>confirm: did you mean X or Y?"]
    P -->|confirmed| V["Validator<br/>structural + semantic"]
    P -->|not confirmed| T
    V -->|fail| Q[Clarification loop<br/>(max 3 rounds)]
    Q --> T
    V -->|pass| C[Compiler → MongoDB plan]
    C --> R["Runtime<br/>MemoryStore / MongoStore"]
    R --> D[(Database)]
```

- **The boundary is the contribution.** The LLM handles the messy, flexible,
  human side of language. Once output crosses into the IR, no probabilistic
  component remains: validation, compilation, and execution are pure code.
- **The LLM never executes anything and never emits code.** Its only output is
  the structured IR.
- **Two validation layers:** Pydantic (shape) + domain rules (meaning).
- **Clarification loop** grounded in missing IR fields (max 3 rounds).
- **Propose-then-confirm:** any word with multiple plausible meanings triggers
  a best-guess IR plus a "did you mean X … or Y …?" question before execution —
  word meanings are inferred from context, never hardcoded.
- **Optional LLM #2 reviewer** between validation and compilation.
- **Runtime collection resolution:** a missing collection triggers a create
  offer or a typo suggestion against the store's actual collections.

## 6. Implementation

- **Stack:** Python, DeepSeek API (`deepseek-chat`, `httpx`, no OpenAI SDK),
  Pydantic v2, pymongo (optional), Flask (GUI), pytest. No LangChain, agents,
  or RAG.
- **IR:** 7 operations (`create`, `add`, `remove`, `move`, `copy`, `find`,
  `update`), 6 operators (`=`, `!=`, `>`, `<`, `>=`, `<=`), one wrapper
  `TranslationResult` with states `complete` | `needs_clarification` |
  `needs_confirmation`. `condition` is optional; `null` means **match all
  records** and compiles to `{}`. `remove` takes an optional `limit` ("delete
  any one record"). Records carry a unique `_id`. A `command` may be a single
  operation or an array (multi-task instructions). See `docs/ir-spec.md` for
  the full formal specification.
- **Translator:** JSON output mode, JSON Schema embedded in the system prompt,
  one-shot corrective retry, tolerant parsing of a stray trailing token,
  temperature 0. The prompt resolves word meanings by **inference, not
  lookup**: it contains no closed vocabulary dictionary — only finite
  structural mappings (operation semantics, operator words, generic-word
  examples) and a small set of illustrative examples of the
  complete/clarify/confirm protocol.
- **Validator:** structural (Pydantic, `extra=forbid`, discriminated union) +
  semantic (`validator/semantic.py`: immutable record id, source ≠ destination,
  name syntax). Fields are schemaless, matching MongoDB's document model.
  Collection existence is a runtime concern.
- **Compiler:** IR → ordered plan of primitive MongoDB steps; `move` = find +
  delete_many + insert_many with a `{"$ref"}` data dependency.
- **Runtime:** `MemoryStore` (deterministic; used by experiments and the GUI)
  and `MongoStore` (pymongo) behind one interface.
- **GUI:** a Flask app renders the instruction, the IR, the MongoDB plan, the
  execution log, clarification/confirmation interactions, and the live database
  state (with `_id`s), on a resettable `MemoryStore` — making the
  "said → understood → validated → planned → happened" chain tangible.
- 90 unit tests + 2 live integration tests (92 total).

## 7. Design Evolution: Observed Failures and Iterative Fixes

This section documents the iterative history. Each failure was **observed by
probing the running system**, categorized, and fixed structurally rather than by
prompt patchwork. The order is chronological; §9 consolidates the resulting
failure taxonomy.

1. **"All records" was unrepresentable.** *"Add everybody to employees without
   deleting them from the previous collection"* produced `copy` with a
   fabricated filter `status != "deleted"` — because `condition` was a required
   field, so "everybody" (match-all) had no encoding, and the model invented
   one. **Fix:** `condition` optional; `null` = match-all. **Result:**
   `copy people → employees, condition: null`, 3 matched → 3 inserted, source
   untouched. Lesson: *an IR constraint that cannot express a legitimate
   meaning forces the LLM to hallucinate.*

2. **Multi-clause instructions silently dropped clauses.** The first
   adversarial run executed 2/5 unsafe cases: *"move everyone over 60 … and
   make sure nobody older than 60 goes there"* ran as a plain `move age > 60`,
   silently discarding the contradicting clause. **Fix:** a multi-clause prompt
   rule — every clause must be captured; conflicts trigger clarification.
   **Re-evaluation:** 5/5 safe.

3. **Per-word meaning rules do not scale.** A first fix hardcoded "retire" →
   `status = "retired"` in the prompt; the next ambiguous word would need
   another rule, forever. **Fix:** removed the hardcoding and replaced it with a
   general principle — *if any word has multiple plausible readings, confirm* —
   plus the `needs_confirmation` state. "Retire …" now yields *"Did you mean:
   set their status to retired? Or move them to pension?"*.

4. **Hardcoded alias lists are the same anti-pattern.** A paraphrase case
   ("anybody below 18") failed because the generic-word alias list lacked
   "anybody". Rather than extend the list, the rule was reframed as *infer from
   context* (with examples, not a closed set). Lesson: *any finite word list is
   wrong eventually; the model must do the inference, and the protocol must
   confirm when it cannot.*

5. **No record identity.** Two identical rows were unaddressable — no id, so
   "delete any row" had to ask, and nothing could single one out. **Fix:**
   unique `_id` per record (shown in the GUI), `remove.limit` ("delete any" =
   `condition: null, limit: 1`), and conditions may reference `_id` ("move
   id=1"). Identity is now generated, disclosed, and addressable.

6. **Domain opacity.** "Everybody → people" is a *correct* mapping, but
   non-technical users cannot be expected to know the domain vocabulary.
   **Fix:** clarification questions now name the available collections/fields;
   the GUI acts as a live dictionary; `docs/glossary.md` documents the terms for
   readers. The system discloses its domain instead of training the user.

7. **Fixed field schemas were stricter than MongoDB.** *"Add Benjamin … salary
   = 20000"* to `pension` was rejected because `pension`'s hardcoded field list
   lacked `salary`. Real MongoDB is schemaless. **Fix:** fields are schemaless —
   any record may carry any fields; only `_id` is immutable (as in MongoDB).

8. **Unknown collections produced raw errors.** Adding to a collection that
   does not exist returned "unknown collection" — unfriendly and unlike a real
   system. **Fix:** collection existence moved out of the static validator into
   the runtime; the pipeline now offers to **create** a missing collection or
   suggests the closest existing name for a likely typo (*"Collection 'intenr'
   does not exist. Did you mean 'intern'?"*).

9. **Single-task limitation.** "Move from people and pension …" and "move X and
   copy Y" could not be expressed. **Fix:** `command` may be an array of
   operations, compiled to one plan.

The recurring lesson: **probing the system surfaces IR design flaws, and each
flaw is fixed in the deterministic layer, not in the model.**

## 8. Evaluation

### 8.1 Methodology

Fresh seeded store per case; temperature 0; canonical IR comparison (`60 ≡
60.0`); baseline runs in a sandbox exposing only `db_*` functions; correctness
judged by final store state vs. the reference state produced by running the
expected IR through our own pipeline. The translator's few-shot examples are
disjoint from all benchmark cases, and the LLM never sees the expected IRs
(audited via `experiments/audit.py`).

### 8.2 H1 — Paraphrase convergence

4 intents × 5 phrasings (passives, idioms, different verbs).
**Result: 20/20 executed; 4/4 intents converged to the expected canonical IR.**
The pre-fix run (13/20) is reported deliberately: every hallucinated output —
literal collection names (`"users"`, `"everybody"`), an invented field
`retired`, malformed JSON — was **caught by the validator: 0 wrong executions**.

### 8.3 H2 — Ambiguity and clarification

4 ambiguous instructions. **Result: 4/4 asked (0 guesses); 4/4 completed to the
correct IR after one answer.** Questions named the missing IR field (e.g.
`condition.value`). Guessable ambiguity uses propose-then-confirm ("Move all
the seniors to pension." → `needs_confirmation` with `age > 60 → pension` and
"Did you mean: move everyone over 60 to pension?"). French input maps to the
same IR with no language-specific code.

### 8.4 H3 — Adversarial safety

5 adversarial instructions (contradictions, unknown collection, out-of-domain,
nonsense). **First run: 2/5 unsafe** (conflicting clauses silently dropped).
**After the multi-clause fix: 5/5 safe, 0 executed** — and this held across
every subsequent run.

### 8.5 H3 — Baseline comparison (direct LLM → code)

Same 29 cases through direct LLM → Python code (sandboxed).

| Metric | This system | Direct code |
|---|---|---|
| Paraphrase correctness (20) | **20/20** | 14/20 (3 crashes; 14–16 across runs) |
| Ambiguity: asked instead of guessed (4) | **4/4** | 3/4 |
| Adversarial: safe (5) | **5/5, every run** | 6/25 unsafe, 2 crashes, 17 asked (audited, 5 runs) |

Direct-code failure modes, classified by an audited metric
(`experiments/audit.py`, `baseline_safety_metric`): across the 5 recorded runs
of the baseline on the 5 adversarial cases (25 total), the baseline **executed
unsafe operations 6 times** (per-run: 2, 0, 2, 1, 1), **crashed twice**, and
asked 17 times. Unsafe executions include silent data corruption — *"move
everyone over 60 to the moon"* became `db_update({"$set": {"country":
"moon"}})` — and moving the wrong records; crashes include `KeyError: '_id'`
and `ValueError` from malformed generated code. The pipeline had **0 unsafe
executions in every run** (25/25 safe): its safety is by construction, the
baseline's is probabilistic.

### 8.6 H4 — Semantic reviewer (LLM #2)

20 correct (instruction, IR) pairs + 8 corrupted pairs that are structurally and
semantically valid but wrong (off-by-one threshold, reversed direction, wrong
verb, wrong operator, wrong field, dropped exception, swapped threshold,
invented threshold).
**Result: 8/8 corrupted detected; 1/20 false rejection — whose reason text
contradicted its own verdict ("so it should be approved… So I'll approve") yet
returned REJECTED.** The reviewer catches what the deterministic layers cannot
(valid-but-wrong IRs), but it is itself probabilistic.

## 9. Discussion

### 9.1 The failure taxonomy

The paper's empirical core: distinct ways natural-language programming fails,
and which layer catches each.

| Failure class | Example | Where caught |
|---|---|---|
| Missing referent | "Move them." | clarification (H2) |
| Missing scope | "Move people to pension." | clarification/confirmation |
| Ambiguous word, no guess | "the old people" | clarification (H2) |
| Ambiguous word, guessable | "the seniors" | propose-then-confirm (H5) |
| Verb with multiple readings | "retire" | confirmation naming alternatives |
| Naming collision (field vs collection) | "pension" as both | confirmation |
| Contradictory clauses | "move >60, nobody >60 goes" | prompt rule → clarification (H3) |
| Unrepresentable scope | "everybody" (all records) | fixed in IR: null condition |
| Unknown collection | "move to the moon" | runtime resolution: create / typo offer |
| Structurally invalid IR | `{"operation":"move","banana":1}` | Pydantic (structural) |
| Non-JSON / malformed output | stray `}` after valid JSON | translator retry + tolerant parse |
| Semantically invalid IR | `people → people`; `set: {"_id": 99}` | semantic validator |
| Valid-but-wrong IR | `age < 60` instead of `age > 60` | LLM #2 reviewer (H4) |
| Runtime execution failure | `KeyError: '_id'` in generated code | only the baseline suffers this |
| Silent semantic corruption | direct code writes `country: "moon"` | prevented by the pipeline (baseline demonstrates) |

The table is the answer to "where does NL programming fail, and where is each
failure caught?" — not "natural language is ambiguous", but an empirical map of
how a bounded system catches each kind of ambiguity.

### 9.2 Architecture insights

- **No closed dictionary of word meanings.** Interpretation is delegated to
  the LLM; ambiguity is resolved by a confirmation protocol. The prompt does
  contain finite, structural mappings (operation semantics, operator words,
  generic-word examples such as "users"/"everyone" → `people`) and a few
  illustrative examples of the protocol — including one involving "retire"
  that demonstrates confirm-with-alternatives. The claim is deliberately
  narrower than "no dictionary anywhere": there is no closed, enumerable
  vocabulary list and no rule module resolving arbitrary domain words;
  synonyms such as record/row/document/item are absorbed by the model, not
  enumerated (`docs/glossary.md` is for readers, not the model).
- **IR constraints surface failure modes.** Requiring `condition` caused the
  LLM to hallucinate a filter; making it optional removed the failure at its
  source. The IR is the primary design surface.
- **Safety by construction.** The deterministic boundary makes wrong execution
  structurally impossible; the baseline is only probabilistically safe.
- **The reviewer is a second, independent probabilistic layer** — it catches
  valid-but-wrong IRs (8/8) but also self-contradicts (1/20).

### 9.3 Limitations, threats to validity, and submission status

- **Scale.** n = 20/4/5/8 per condition is a demonstration, not a benchmark;
  the sizes were hand-chosen, not sized for statistical power. There is no
  held-out set: the same person wrote the system prompt and the test cases.
- **Single model, single temperature.** All results use `deepseek-chat` at
  temperature 0; cross-model replication (e.g. GPT-4o-mini, Claude Haiku) is
  required before claiming model independence.
- **Self-built baseline.** The direct-code baseline is a sandbox written by
  the authors, not a tuned third-party NL2SQL/code-generation system.
- **Reviewer independence.** LLM #2 is the same model family as the
  translator, so its 8/8 detection rate may partly reflect a model agreeing
  with itself.
- **In scope but disclosed:** single domain; single-clause conditions (no
  compound constraints or exceptions in the IR); no joins or composition;
  the GUI and reviewer additions postdate the main benchmark runs.

As it stands, this work is best positioned as a **workshop paper or arXiv
preprint** (systems/tools track of an NL-programming or LLM-systems workshop):
its soundest contributions — the bounded-boundary architecture, the design
evolution of §7, and the failure taxonomy of §9.1 — are honestly reported and
auditable. A full conference or journal submission additionally requires the
scale and independence items above: larger held-out benchmarks, ≥2 models,
independent or inter-rater scoring, and a stronger, equally-tuned baseline.

## 10. Conclusion and Future Work

- Demonstrated: an LLM front end + canonical IR + deterministic
  validation/compilation achieves paraphrase convergence (20/20), asks instead
  of guessing (4/4), is safe on adversarial input (5/5), and outperforms direct
  code generation (20/20 vs 14–16/20) while eliminating silent corruption. It
  maps any natural language to the same IR and resolves word meanings by
  inference rather than any closed dictionary — ambiguity is handled by
  clarification and confirmation protocols,
  and the failure taxonomy shows precisely which layer catches which failure.
- Future work: compound conditions and exceptions in the IR; joins and
  aggregation; multi-domain front ends; integrating the reviewer into the
  pipeline with a cost analysis; larger benchmark sets; other models;
  persistent MongoDB deployment of the same pipeline.

## References

All arXiv identifiers and author lists verified against arXiv as of August
2026.

1. Shuyuan Xu, Zelong Li, Kai Mei, and Yongfeng Zhang. "AIOS Compiler: LLM as
   Interpreter for Natural Language Programming and Flow Programming of AI
   Agents." arXiv:2405.06907, 2024.
2. Lifan Hu. "Linguine: A Natural-Language Programming Language with Formal
   Semantics and a Clean Compiler Pipeline." arXiv:2506.08396, 2025.
3. Asaf Achi Mordechai, Yoav Goldberg, and Reut Tsarfaty. "NoviCode: Generating
   Programs from Natural Language Utterances by Novices." arXiv:2407.10626,
   2024.
4. Xinyi Hou, Yanjie Zhao, Yue Liu, Zhou Yang, Kailong Wang, Li Li, Xiapu Luo,
   David Lo, John Grundy, et al. "Large Language Models for Software
   Engineering: A Systematic Literature Review." ACM Transactions on Software
   Engineering and Methodology, 2024. arXiv:2308.10620.
5. Daoguang Zan, Bei Chen, Fengji Zhang, Dianjie Lu, Bingchao Wu, Bei Guan,
   Yongji Wang, and Jian-Guang Lou. "Large Language Models Meet NL2Code: A
   Survey." In Proceedings of ACL 2023. arXiv:2212.09420.
6. Mark Chen et al. "Evaluating Large Language Models Trained on Code."
   arXiv:2107.03374, 2021.
7. Jacob Austin, Augustus Odena, Maxwell Nye, Maarten Bosma, Henryk
   Michalewski, David Dohan, Ellen Jiang, Carrie Cai, Michael Terry, Quoc Le,
   and Charles Sutton. "Program Synthesis with Large Language Models."
   arXiv:2108.07732, 2021.
8. Bailin Wang, Richard Shin, Xiaodong Liu, Oleksandr Polozov, and Matthew
   Richardson. "RAT-SQL: Relation-Aware Schema Encoding and Linking for
   Text-to-SQL Parsers." In Proceedings of ACL 2020. arXiv:1911.04942.
9. Luke S. Zettlemoyer and Michael Collins. "Learning to Map Sentences to
   Logical Form: Structured Classification with Probabilistic Categorial
   Grammars." In Proceedings of UAI, 2005.
10. Percy Liang. "Lambda Dependency-Based Compositional Semantics."
    arXiv:1309.4408, 2013.

