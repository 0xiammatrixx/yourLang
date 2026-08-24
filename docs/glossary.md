# Terminology

This is for **human readers only** — the LLM is given none of this as rules;
it absorbs these synonyms from context.

| Term | Also called | Notes |
|---|---|---|
| collection | table | the known collections here are `people`, `employees`, `pension` |
| record | row, document, item, entry, tuple | the thing stored in a collection |
| field | column, attribute, property | e.g. `name`, `age`, `country`, `salary`, `status` |
| id / `_id` | record id, primary key | a unique whole number per record, assigned by the store |

**Design principle:** the system maintains no thesaurus of word meanings. The
only finite things it fixes are *structural* (operation semantics such as
"copy" vs "move", operator words such as "above" → `>`), not vocabulary.
Synonym variation ("row" vs "record" vs "document") is delegated to the LLM,
and ambiguity is resolved by a confirmation protocol.
