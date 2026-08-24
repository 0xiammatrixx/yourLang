# Research question & contribution

## Contribution statement

> I propose a natural-language-first programming architecture in which an LLM
> serves as a semantic translation layer between **unrestricted** user language
> and a deterministic intermediate representation.

This is deliberately narrower than "I invented natural-language programming"
(which is false — the literature shows decades of prior work).

## Research question

> Can an LLM reliably translate semantically equivalent natural-language
> instructions into the **same executable intermediate representation**, while
> detecting ambiguity and requesting clarification when required?

## Hypotheses

- **H1 (convergence):** semantically equivalent phrasings map to one canonical
  IR. *Tested by experiment 2.1.*
- **H2 (ambiguity):** when required IR fields cannot be determined, the system
  asks instead of guessing. *Tested by experiment 2.2.*
- **H3 (safety):** the deterministic validation/compilation boundary prevents
  the execution of wrong commands, unlike direct code generation. *Tested by
  experiments 2.3 and 2.4.*
- **H4 (review):** a second LLM reviewing (instruction, IR) pairs catches
  semantically-valid-but-wrong IRs. *Tested by experiment 2.5.*
- **H5 (confirmation):** when a word or phrase has multiple plausible readings,
  the system proposes its best guess and asks the user to confirm instead of
  silently choosing one meaning. *Tested by the `needs_confirmation` state and
  the failure analysis in §6.6.*

## Architecture decisions

1. **The LLM never generates executable code and never executes commands.**
   It only produces structured semantics (the IR).
2. **Conventional compiler machinery moves AFTER the LLM.** The LLM is a
   *probabilistic semantic front-end*; once output crosses into the IR,
   normal computer science takes over. That boundary is the contribution.
3. **Clarification is grounded in the IR:** the LLM reports which fields are
   missing, not a generic "please rephrase".
