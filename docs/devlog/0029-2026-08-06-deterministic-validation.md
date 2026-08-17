# 0029 — 2026-08-06 — 5.4: deterministic type-claim validation

## What was done

- **`api/rag/validation.py`:** `check_type_claims(answer, citation_map, type_lookup)` —
  regex-extracts a type claim from the answer (closed vocabulary: the 18 real type
  names from the DB, never an open-ended grammar guess) and cross-checks it against
  the cited Pokémon's real types. Only checks when **exactly one** Pokémon is cited
  (ambiguous otherwise — deliberately not attempted for multi-Pokémon answers).
  `SqlPokemonTypeLookup` is lazy + cached (`known_types` fetched once, on first real
  use) — matches the existing DB/credential-free-until-first-use policy so app startup
  and offline tests pay nothing for it.
- **Fix, never rewrite:** a mismatch appends a correction note
  (`"Correction: X is Y type, not Z."`) — the model's sentence is never spliced in
  place; text-surgery on LLM prose is what actually breaks grammar/meaning silently.
- **Graph:** new `validate` node, wired `finalize → validate → END` (linear for now —
  conditional reformulate/abstain routing is 5.5). No-ops entirely when
  `RagDeps.type_lookup` is `None`, so every existing test kept working unchanged.
  `ContextDocument` gained `pokemon_id` (was name-only) so validation can look up the
  DB by id instead of joining on a display string.
- **Contract:** `ResponseStatus.CORRECTED` already existed (unused since Phase 3);
  `ChatService` now reads `corrections_applied` from graph state instead of a
  hardcoded `0`.

## Why

"Never invent stats, types, evolutions" is rule #3 of the system prompt (`prompts.py`)
— this is the safety net for when the model breaks that rule anyway despite correct
context, closing the loop the prompt alone can't guarantee.

## How it was tested

15 new tests: 7 in `test_validation.py` (match/no-match/ambiguous-multi-pokemon/
unknown-pokemon/empty-vocabulary + the hyphen regression below), 3 new graph-level
tests in `test_rag_graph.py` (`FakeLLM` producing a wrong claim → `status=corrected`,
`corrections_applied=1`, note appended; a correct claim → untouched; no `type_lookup`
configured → no-op, locking in backward compatibility). `apps/api`: 64 passed (was 54),
8 skipped, ruff clean.

**Live-caught bug, fixed same session:** restarted the real api and asked
`gemini-3.6-flash` about Bulbasaur — it answered *"Grass/Poison-**type**"* (hyphen,
no space before "type"). The original pattern only matched `\s+type\b` (space
required) and silently missed it — a false negative that would have suppressed a
real mismatch just as silently, the worst failure mode for a safety-net check. Fixed
to `[\s-]+type\b`; added a regression test with the exact live phrasing style. Then
re-verified live (Bulbasaur, Squirtle) with the fix: both correctly `answered`,
`corrections_applied=0`, no false positive.

## Cost

Two live `/chat` smoke calls (~$0.003 total, same order as the Phase-3 gate) — no
formal cost-estimate entry for a two-call smoke check on an already-approved model.

## Surprises / lessons

Same lesson as 5.3's nDCG bug, different subsystem: a regex written against *invented*
example sentences ("Bulbasaur is a grass and poison type Pokémon") missed the *real*
model's actual phrasing style on the very first live call. Two-for-two this session —
any parser/regex meant to interpret real LLM output needs at least one live call
before being trusted, no matter how reasonable the synthetic test cases looked.

## Next

5.5 — LLM judge (groundedness/citation-precision/hallucination) on a model different
from the generator; `FakeJudge` for tests; graph conditional edges (reformulate,
attempt<max=2; abstain) — the routing `validate` was deliberately left linear for.
