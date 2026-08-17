# Learning log

What this project actually taught, consolidated at Phase 6 from the "Surprises /
lessons" section of devlogs 0001–0034. Organised by theme rather than chronology,
because the same lesson kept arriving through different doors.

Chronological detail stays in the devlogs; this file is the distillation.

---

## 1. Verify against reality, never against documentation

The single most repeated lesson of the project, learned five separate times.

- **Listing ≠ availability.** `gemini-embedding-2` appears in the us-central1 model
  listing and returns 404 there; it serves only from `global` (devlog 0006, ADR-0002).
  A catalog entry is not a working endpoint.
- **The same vendor ships contradictory behaviors.** `gemini-embedding-2` returns
  L2-normalized vectors; `gemini-embedding-001` returns unnormalized truncated ones.
  Defensive re-normalization in `GeminiEmbedder` exists because both are real (0006).
- **One request, one embedding.** The endpoint returns a single embedding no matter how
  many `contents` are sent — request-level batching would have silently misaligned
  items with vectors. Found live, not in the docs (0017).
- **Prompt names are part of a model's contract.** EmbeddingGemma is asymmetric:
  queries and documents need different prompts. The names were verified live before
  building on them, and the config turned out to ship more variants than expected (6.1).
- **Regexes written against imagined text fail on real text.** A type-claim validator
  written against invented phrasing missed the actual model's style on the very first
  live call (0029). Same shape of bug as the nDCG one below. Twice in one session.
- **Real data breaks synthetic-only tests.** nDCG could exceed 1.0 whenever one Pokémon
  had several documents in the same result page — impossible to hit with the tidy
  synthetic fixtures, immediate against the real corpus (0028).

The pattern: **anything that parses, scores, or interprets external output must meet
real output before it is trusted.** Unit tests with fakes prove the plumbing; they
cannot prove the assumptions.

## 2. Cost discipline is an engineering feature, not paperwork

- An unattributed **€4.62 Vertex charge** appeared with no record of who or what caused
  it (devlogs 0021, 0022). Root cause was never provable: Data Access audit logs were
  off, so individual API calls left no trace. The permanent rule that came out of it —
  a written estimate plus explicit human go-ahead before any paid call — has governed
  every milestone since.
- **The billing console's summary widget hid the actual driver** behind pagination; the
  CSV export from Reports resolved it. Pull the CSV first (0022).
- **Read-only `gcloud list` sweeps are a free, fast way to rule out silently-billing
  infrastructure** before asking a human to dig through a billing UI (0021).
- Enabling **Data Access audit logs cost nothing and closed the blind spot** that made
  the incident unattributable in the first place (0025).
- Estimates land close when they are built from *measured* rates rather than guesses:
  the 5.6 baseline estimate ($0.036–0.08) versus actual (~$0.05). By 6.4 the report
  generator computes cost per answer from real token counts — and reports "unknown"
  for unpriced models rather than inventing a number.

## 3. Isolation boundaries have to be enforced by structure, not intention

- **Embedding spaces**: every vector is FK-bound to a space with its own partial HNSW
  index, every query resolves exactly one space, and startup fails fast if config and
  registry disagree. When EmbeddingGemma arrived in Phase 6.1 the second space slotted
  in with a migration and no redesign — the constraint written in Phase 2 paid out four
  phases later.
- **A model must not grade its own homework**: `judge_provider != llm_primary` is
  enforced at startup, not left to configuration discipline (5.5). Phase 6.2 hit the
  subtler version — a provider under comparison *can* also be the judge — and answered
  it by reporting the verdict with `independent: false` rather than hiding it.
- **Identical context by construction, not by copy-paste**: `/compare` and `/chat`
  share the same retrieval, prompt-building and finalize functions. Duplicating them
  would have meant the comparison silently measured two pipelines instead of two models
  (6.2).
- **Components never import each other.** The evals runner talks to the API over HTTP
  only, which is what made `--fake-api` possible: swapping one client class replaces the
  entire system under test.

## 4. Degrade explicitly, and make the degradation visible

- A broken judge **fails open** with a warning — a quality gate must never take down the
  thing it grades (5.5). `/compare` extends this: an unjudged candidate is reported as
  unjudged, and the summary averages groundedness over the judged subset only, so a
  broken judge cannot look like a bad provider.
- **Per-item failure isolation** beats whole-job retries for bulk work: one 502 on one
  PokéAPI resource shouldn't kill an hour-long ingest (0014). Same shape in `/compare`:
  one provider failing yields one failed candidate, not a failed comparison.
- **The 503 path got exercised for real** when a torch install silently no-op'd: the
  API answered with the designed, actionable message instead of a stack trace (6.1).
  The error path was right; discovering it accidentally was the useful part.

## 5. The environment is part of the system

- **A PostgreSQL inside WSL owns port 5432** and shadows Docker's published port,
  answering with a confusing auth error while the container logs nothing. Host port
  5433 ever since (0008).
- **`bash` from PowerShell is WSL, not Git Bash** — different HOME, no poetry (0004).
- **`gcloud --format=json > file` truncated silently** mid-JSON, surfacing much later as
  a decode error (0025).
- **`poetry add ../../libs/x` writes an absolute `file:///` path** that breaks in any
  other checkout or git worktree; it also silently broke all three Dockerfiles, which
  were missing lib copies and could not build at all until Phase 6.6 caught it.
- **Restart a server after installing heavy deps into its venv.** A retried lazy import
  lands on poisoned half-imported modules — 500 instead of the designed 503 (6.1).
- `str(sqlalchemy_url)` masks the password as `***`; use
  `render_as_string(hide_password=False)`. Cost a real debugging session.

## 6. Evaluation only teaches you something if it can fail

- The retrieval suite scored **1.000 on everything** from its first run — a perfect
  score that told us nothing, because the cases were unambiguous single-entity lookups
  by design (0028). It stayed uninformative until Phase 6.1, when exactly **one** case
  separated two embedding models (Raichu outranking Pikachu). One discriminating case
  out of thirty is a signal that the suite, not the system, needs work.
- **Hallucination bait is hard to write.** An early `must_not_contain` banned a word
  that a complete, correct answer would legitimately use (0031). A bad golden case
  punishes correct behavior — worse than no case.
- **CI's pipeline-integrity job deliberately uses hash-derived fake responses**, not
  echoed expectations: a fake that returns what the case expects would let a scorer
  stubbed to `return 1.0` pass CI forever (6.3).
- **Every real bug becomes a permanent case.** `rag_answers` was built in Phase 3
  explicitly as regression-mining ground; Phase 5.7 mined it, promoting the project's
  very first live `/chat` call into a golden case.

## 7. Things that paid for themselves later

- **Provider portability** (Phase 4) was built for fallback. It then supplied the judge
  (5.5), the reformulate loop's independent grader, and the entire `/compare` endpoint
  (6.2) at zero additional infrastructure cost.
- **`rag_answers`** was built for traceability. It became the regression mine (5.7) and
  then the source of latency percentiles and cost-per-answer in the report generator
  (6.4).
- **Alembic autogenerate + review** was materially faster than handwriting 13 tables and
  got the FKs, uniques and indexes right first try (0011).
- **`Vector.with_variant(JSON, "sqlite")`** keeps the whole model suite runnable on
  SQLite, so unit tests stay offline while pg-only features (tsvector, HNSW) live in
  migrations that integration tests cover (0016).

## 8. Dependency and toolchain hygiene (Phase 7)

Adding the first Node component surfaced a cluster of lessons the Python side never did:

- **Never pin a version from memory.** Three of the versions in the first
  `package.json` were invented (`eslint@9.42.0` and `typescript@5.9.4` do not exist).
  Query the registry; the install failure is the cheap outcome, a silently-wrong pin is
  the expensive one.
- **A failing supply-chain check is a signal, not an obstacle.** The machine's
  `minimumReleaseAge=1440` policy failed closed because pnpm's cached *abbreviated*
  registry metadata omits the `time` field. The fix was to clear that cache so pnpm
  refetches full documents and the age check actually **runs** — not to disable the
  setting, and not to reach for the `resolution-mode=highest` escape the error text
  suggests. When a security control blocks you, make it work; don't turn it off.
- **Prefer the boring allowed alternative over fighting a dependency.**
  `eslint-config-next` couldn't be installed under that policy; the guidelines already
  permit oxlint, which needs no plugin chain and found four real issues (three a11y) on
  its first run — including a `role="button"` div that became a shorter, more accessible
  real `<button>`.
- **Prettier reads `.editorconfig`.** One source of truth for indentation beat a second
  competing setting in `.prettierrc`.
- **Testing-library mirrors real browser behaviour, including the awkward parts.**
  `user.upload` honours an input's `accept`, so a "rejects wrong file type" test never
  fired — which correctly pointed out that the validation matters for **drag-and-drop**,
  the path that genuinely bypasses `accept`. The test was wrong, not the code.

## 9. Deferred, with the reasoning recorded

- **Bulk ingestion for multi-generation scale** (0005-era analysis): `PokeAPI/api-data`
  ships pre-generated static JSON matching the REST schema — one clone, no throttling,
  provenance by commit SHA. Keep the Gen-1 REST ingest; if we scale past Gen 1 (~10k
  resources ≈ 1h at 3 req/s), add `pipeline ingest --source <clone>` feeding the same
  SnapshotStore so nothing downstream changes. Write an ADR at that point.
- **Matryoshka-truncated EmbeddingGemma** (512/256 dims) would be a third space, not a
  variant of the second — deferred with the native 768 baseline in place (ADR-0006).
- **Rate limiting per API key** — `--max-instances` bounds the blast radius, but a valid
  key can still loop. Needed before the deployment URL is shared beyond a demo.
