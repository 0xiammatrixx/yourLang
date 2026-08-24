# Research map — existing approaches vs. this system

| Existing approach | What it does | Problem / limitation |
|---|---|---|
| Traditional programming languages | Human writes formal syntax | Syntax burden on the human |
| Natural-language → code | LLM directly generates executable code | Hallucination / unreliability |
| Natural-language programming | Restricts language/grammar | Human still has to learn rules |
| AIOS Compiler / CoRE | LLM interprets NL programs | Different architecture / domain |
| Linguine | NL-like formal language + compiler | Requires controlled language / formal grammar |
| **This system** | Unrestricted NL → LLM → validated semantic IR → deterministic compiler | Reliability must be tested (it is, in experiments 2.1–2.5) |

## Targeted reading checklist (5–8 papers)

1. **Systematic review (2014–2024)** — use as a map only: "NL → program
   synthesis has existed for years; LLMs recently changed the field."
2. **AIOS Compiler / CoRE** — LLM as interpreter of NL programs. Extract: what
   goes in, what comes out, where the LLM sits, representation, execution,
   ambiguity handling, evaluation, and *what they did not solve*.
3. **Linguine** — NL-inspired language with a formal compiler pipeline
   (parser → clause graph → typed IR → verification → Python). Key question:
   why did they need a formal grammar, and can an LLM replace the front end
   while preserving the formal backend?
4. **NoviCode** — can non-programmers describe programs in everyday language?
   Evaluates programs by whether they *execute correctly*, not just look right.
5. **IR / code-generation work** — intermediate representations between NL and
   generated code; evidence that NL itself can be a strong IR, and recent
   proposals for canonical IRs between NL and generated models.

Each row here should become a short paragraph in Related Work, with
"here is what they do" and "here is what this system does differently".
