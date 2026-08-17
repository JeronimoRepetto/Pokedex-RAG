# ADR-0007: Type-effectiveness uses the MODERN chart, not Generation I's

- **Status:** accepted
- **Date:** 2026-08-07

## Context

Phase 8 imports `damage_relations` from the PokéAPI type snapshots (on disk since the
Phase-1 ingest; `normalize_type` used to discard them). The snapshots also carry
`past_damage_relations` with the Generation-I chart — so for a Gen-1 Pokédex the
"authentic" chart was RIGHT THERE, and choosing not to use it needs justification.

Verified facts that decided it:

- The corpus already carries **modern typings**: Magnemite/Magneton are Steel,
  Clefairy/Jigglypuff/Mr. Mime are Fairy — types that did not exist in Gen I. That is
  also why `data/raw/pokeapi/type/` holds 17 snapshots including steel (9) and
  fairy (18): the backfill fetches types actually assigned to the roster.
- Abilities (in every card document) are modern too; they didn't exist in Gen I.
- A Gen-I chart would therefore have **holes for types the corpus's own Pokémon have**.
- Dark (17) has NO snapshot of its own (no Gen-1 Pokémon is Dark) but appears in other
  types' relations — which forced importing BOTH `*_to` and `*_from` directions, with
  `_stub_type` creating the missing row (the same FK discipline `normalize_pokemon`
  documents; invisible on SQLite, an FK violation on PostgreSQL).

## Decision

Import the current `damage_relations` only; ignore `past_damage_relations` (one comment
in `normalize_type` says so). Every generated matchup document ends with the literal
sentence *"Type matchups follow the current (Generation VI onward) type chart."* so any
model quoting it inherits the caveat, and `/matchup`'s disclaimer states it too.

Storage: only non-neutral pairs (2.0/0.5/0.0) are stored — 119 rows for 18 types;
a missing row means 1x, a rule that lives in exactly one place (`typechart.multiplier_for`).
`Float`, not `Numeric`: the values are exact binary fractions and their products
(0.25, 4.0) stay exact.

## Alternatives considered

- **Gen-I chart from `past_damage_relations`** — more "authentic" but inconsistent with
  the corpus's modern typings/abilities; Fairy-type Clefairy with no Fairy column is a
  worse lie than a labelled modern chart. A fan will notice Ghost-vs-Psychic differs
  from Gen I; the caveat sentence is the honest answer.
- **A `generation` column supporting both charts** — forces `WHERE generation = ...`
  into every read forever, for a second chart nothing consumes. Adding it later is one
  migration either way.
- **Seeding the chart in the migration DDL** — duplicates the snapshot as a source of
  truth; normalisation from the snapshots keeps one.

## Consequences

- `pipeline ingest` re-runs populate the chart with `fetched=0` (pure snapshot re-read).
- The `types` table gains a `dark` row, which as a side effect lets the Phase-5.4
  validator detect "X is a Dark type" claims (golden case rag_quality_015's topic).
- Verified live 2026-08-07: 119 rows, `dark->psychic = 2x` present (the pair that an
  offensive-only import would have silently lost).
