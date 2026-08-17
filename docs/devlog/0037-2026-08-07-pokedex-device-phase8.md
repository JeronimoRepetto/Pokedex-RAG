# 0037 — 2026-08-07 — Phase 8: the Pokédex device; type knowledge; intent routing; matchup

Whole phase in one session, plan-mode first (the plan's falsifiable prediction is the
headline below). Commits `97546f6` + `1a55a7d` on `phase-8-pokedex-device`, merged.

## The capability gap the UI redesign exposed

Jeronimo's ask was visual (black stage, red Pokédex chassis, everything inside it, an
AI deciding card/question/comparison). Working out what "comparar" must do exposed that
the system COULDN'T: `/compare` compares LLM providers, nothing compares Pokémon, and
the corpus had no type-effectiveness knowledge — the 6.2 judge had already flagged
"grass beats water" as ungrounded-though-true.

**Key finding:** the type data was on disk all along. `data/raw/pokeapi/type/` holds 17
snapshots with full `damage_relations`; `normalize_type` was two lines and discarded
them. Zero new PokéAPI calls — `pipeline ingest` re-ran with `fetched=0, reused=1103`.

## What was built

- **libs/db:** migration 0007 (`type_effectiveness`, sparse: absence = 1x; ADR-0007
  records choosing the MODERN chart over the available Gen-I one) + `typechart.py` —
  pure matchup maths (dual-type products, immunity zeroing, defensive profiles,
  both-direction head-to-heads) shared by pipeline and API so documents and endpoint
  can never disagree. Both relation directions are imported because **Dark has no
  snapshot** (no Gen-1 Pokémon is Dark) yet appears in others' `*_from` lists — an
  offensive-only import would silently claim Dark↛Psychic. `_stub_type` + flush handles
  the FK (invisible on SQLite, violation on PG — the known bug class).
- **data-pipeline:** `normalize_type` keeps the relations; `DocumentBuilder._matchups`
  emits a 5th per-Pokémon document (defensive buckets incl. 4x/immunities, offensive
  lists per own type, and the literal Gen-VI-chart caveat IN the document so a quoting
  model inherits it). +151 documents, both spaces embedded (~$0.006 paid).
- **api:** `POST /intent` (ADR-0008: deterministic bilingual rules + difflib fuzzy
  names + measured stopword list; opt-in LLM escalation following LLMJudge's pattern;
  every failure → `question`, HTTP 200) and `POST /matchup` (fully deterministic;
  **no winner field, enforced by a test** — stats + a chart is not a battle simulator).
- **web:** the device. Original-CSS chassis (cqw ornament / rem content, shading not
  perspective), pure two-axis state machine (`screen` vs `activity`; a failure never
  blanks the screen; provider-A/B panel is DERIVED from the verdict's origin so it
  can't exist for card/image lookups), seq-guarded async, intent dispatch with a free
  numeric fast path, camera input + client-side downscale (fixes HEIC and >5MB phone
  photos), mobile one-panel mode with hinge tabs, deep links preserved (156 static
  pages). `/chat/` and `/compare/` are aliases (a static export cannot redirect).

## The falsifiable prediction — PASSED

Planned in advance: once matchup documents exist, `regression_000001`'s grass-beats-
water claim must become citable. Live result: the answer now cites **both** matchup
documents as [1][2], `warnings: []` (the 6.2 run had flagged exactly this claim), and
both suites held: text_retrieval 1.000×4 (id=9), rag_quality 16/16 (id=10), plus 3 new
matchup golden cases 3/3 (id=11) — questions that previously could only abstain.

## Verified live in the browser (real stack)

*"Pickachu es mas fuerte que Gengar?"* (misspelled, Spanish) → fuzzy-resolved compare →
versus screen with correct chart maths (electric↔ghost/poison is neutral both ways,
totals 320/500) + a cited Spanish narrative. *"Dime todo sobre Gengar"* → card. `25` →
card with zero /intent calls. *"what is Gengar weak to?"* with A/B on → ONE /compare;
in-screen primary answer citing `Gengar (#94) — type matchups`; full judged grid below
(vertex 3556ms/200tok vs flash-lite 557ms/23tok, self-graded caveat rendered). Mobile
(≈708px): hinge tabs, one panel at a time, auto-switch to DISPLAY on results.
`/pokemon/25/` deep-links. Zero console errors.

## How it was tested

**409 offline tests** across six components (26 db incl. 24 typechart, 56 pipeline,
177 api incl. 29 intent + 18 matchup/endpoint, 112 evals, 38 web incl. the machine's
invariants), coverage floors met, ruff/oxlint/tsc/prettier clean, 156-page export
builds.

## Cost

~$0.06 actual vs ~$0.05 estimated (two extra A/B browser verifications); cost-log
updated. Everything else — chart, documents, intent rules, matchup endpoint, local
embed — is free by construction.

## Surprises / lessons

- **React StrictMode broke the seq guard, found live only.** Double-mounted effects
  dispatch two BEGINs before any render; both callers derived the same seq from
  pre-dispatch state, so every response was dropped as stale and the deep link hung on
  "Cargando…" forever. 38 offline tests passed happily. Fix: the CALLER allocates seq
  from a synchronous ref and BEGIN carries it. Lesson: async-race guards need the
  double-invoke environment, not just unit tests.
- **The test data was wrong, not the code:** asserted poison resists flying (it
  doesn't); the matchup maths was right and the "failure" was my seed chart. Encoding
  real-world rules means the fixtures need the same fact-checking as the code.
- **"25" is a valid query but shorter than the 3-char minimum** — the numeric fast
  path had to move BEFORE the length guard. A test caught it before the browser did.
- The three real user examples all resolve deterministically — the LLM classifier
  ships disabled and nothing was lost. Measure before paying.

## Next

Try it: `make web-dev` + API on 8000/8002 (see apps/web/README.md). Deployment stays
deferred by the standing decision. Debt worth a session: harder golden cases (suite
saturation, from 6.1) and enabling INTENT_PROVIDER if the logged `method` rates ever
show a real ambiguous band.

## UI feedback round (2026-08-07, same session)

Jeronimo reviewed the device live and asked for three changes, all applied and
re-verified in the browser:

1. **Fixed screen with internal scrolling** — the screen used to grow with tall
   content (a versus stretched the whole chassis, "se ve cutre"). Now `.screen` has a
   fixed clamp height and content scrolls inside; the d-pad gained REAL up/down
   buttons that page the screen content (smooth-scroll only under
   prefers-reduced-motion: no-preference).
2. **The floating "N"** was Next.js dev-tools indicator (dev-only, never in builds) —
   disabled via `devIndicators: false` anyway.
3. **Stage title** — "Pokédex-RAG" above the chassis, franchise-EVOKING styling in
   plain CSS (yellow fill, blue stroke, italic 900) with no logo/font asset, same IP
   line as the chassis.
4. **Versus alignment** — the two fighters were independent cards, so Gengar's extra
   type badge shifted his stats out of line ("cutrisimo", fair). Rebuilt as ONE shared
   grid: fighters in the head row, then one row per stat (value | label | value) with
   the higher value highlighted — aligned by construction, and more readable.
