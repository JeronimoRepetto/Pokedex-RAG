# ADR-0008: Hybrid intent classification — deterministic rules first, LLM opt-in, fail-open

- **Status:** accepted
- **Date:** 2026-08-07

## Context

The Phase-8 device routes free text to one of three actions (card / question /
compare). `/intent` is hit on EVERY submission, so an LLM-first classifier would
quietly become the most-called paid endpoint in the product — and it would sit at the
entrance, where an outage takes down everything.

Measured findings (difflib ratios against the real 151-name roster) that shaped the
design:

| input | best match | ratio |
|---|---|---|
| pickachu | pikachu | **0.933** |
| charizrd | charizard | 0.941 |
| squirtel | squirtle | 0.875 |
| **para** (Spanish "for") | **paras** | **0.889** ← clears any usable cutoff |
| pero ("but") | spearow | 0.727 |
| about | kabuto | 0.727 |

The user writes Spanish. Without a stopword list, *"¿cuál es mejor para atacar?"*
resolves a phantom `paras` entity and mis-routes. **The stopword list is load-bearing,
not a nicety.**

## Decision

Four-layer resolver + rule classifier, all deterministic and free
(`api/intent/rules.py`): accent-fold → exact match (never fuzzy-checked, so `mew`
survives) → bilingual stopword filter → `difflib` fuzzy at cutoff 0.80 with a 4-char
minimum. Two resolved names = compare (before question cues, so *"¿Pikachu es más
fuerte que Gengar?"* compares). Bare name = card. Cues decide the rest.

Only ONE narrow band escalates (single entity + unrecognised content words + no cue),
and only when `INTENT_PROVIDER` is configured (empty = disabled, the project's standard
"empty disables it" semantics). The escalation follows `LLMJudge`'s structured-JSON
pattern, and the model **chooses a label only — any names it returns are re-resolved
against the roster and dropped if unknown**, so it cannot mint a Pokémon.

Every failure (provider error, unparseable JSON, unknown label, compare without two
entities) degrades to `question` with a warning, HTTP 200. The response's `method`
field (`deterministic` | `llm` | `fallback`) makes the escalation rate measurable
before anyone considers caching.

## Alternatives considered

- **LLM-first classification** — ~600 ms and ~$0.0002 added to every submission,
  including "gengar"; an outage kills the entrance. Rejected on both grounds.
- **Exact-match names only** — the user's own first example ("Pickachu") breaks it.
- **rapidfuzz** — better scorer, but a new dependency where stdlib difflib measurably
  clears every real case in the table above.
- **Client-side name table** — ships franchise data in the bundle and duplicates the
  roster; the API owns the names.

## Consequences

- The user's three real examples all take the free path (verified live 2026-08-07:
  `method=deterministic`, "pickachu"→pikachu fuzzy 0.933).
- The cutoff/length/stopword values live in settings/constants with the measurements
  recorded here; changing them without re-measuring is how `para`→`paras` comes back.
- `SqlPokemonNameLookup` caches the roster after one query (151 immutable rows).
