# 0038 — 2026-08-07 — Phase 9: pause switch, spend caps, GitHub Pages workflow

Plan-mode first. Commit `26b5db1` on `phase-9-deployment`, merged. **Nothing is deployed
yet** — this milestone builds the controls that make deploying safe.

## Why this came before the deployment

Jeronimo asked two questions that turned out to be one: "can I keep the RAG off until I
want it?" and "can someone abuse /chat from devtools?". Both are about who can spend his
money, and exploration measured the exposure precisely:

- `NEXT_PUBLIC_API_KEY` is compiled into the browser bundle — the gate is public by
  construction, and no amount of hiding fixes that.
- **One `/compare` request fans out to as many as 9 paid calls** (1 embedding + 4
  generations + 4 judge calls); `/chat` to 7. A bot needs no volume to be expensive.
- There was no rate limiting of any kind: only the API-key gate, CORS and field bounds.

## What was built

- **Pause switch** (`SERVICE_PAUSED`): every route except `/health` returns 503 with a
  bilingual body, so no handler runs and no model can be called whatever a caller sends.
  `/health` keeps answering and reports `paused: true` — which is what lets the UI tell
  "switched off on purpose" apart from "unreachable". Those deserve different messages
  and conflating them would make a working demo look dead.
- **Daily ceiling in the gateway** (ADR-0009): a `QuotaGateway` wraps every registered
  provider, so every paid call in the system is counted at the one place money is spent.
  Counters live in `api_usage` (migration 0008) because Cloud Run runs several instances
  and an in-memory counter would make the real limit (instances x limit).
- **Per-caller cap** on `/chat` and `/compare`, bucketed by a **hash** of the address.
- **429 with a bilingual body** at either limit, via an app-wide exception handler —
  the ceiling lives several layers below the router, so without it a spent allowance
  would surface as a 500.
- **GitHub Pages**: `basePath`/`assetPrefix` (absent until now — a project site is not
  served from the domain root), a `.nojekyll` file, and `deploy-web.yml` with a
  pre-publish assertion that both survived the build.
- **Runbook** rewritten around verified provider behaviour, plus the honest note that on
  a public deployment the API key is not a security control.

## Verified live

Pause: `/health` 200 with `paused:true` and the contact; `/pokemon/1` 503 with both
languages. Caps (limit 3): requests 1-3 passed the limiter, 4 and 5 got **429**; the
capped caller still got 200 from `/pokemon/1` and `/matchup`; a different address was
unaffected; `api_usage` holds only hashes (`ip:2ba3fd…`), no addresses. Static export
built with `NEXT_PUBLIC_BASE_PATH=/Pokedex-RAG` emits `/Pokedex-RAG/_next/…` and ships
`.nojekyll`.

The global ceiling's "no further paid call is made" is proven in a unit test that asserts
the inner gateway is never invoked past the limit — deliberately not re-verified live,
since doing so would mean paying for calls to watch them be refused.

## How it was tested

**248 offline tests** in the touched components (26 db, 206 api incl. 17 quota + 8
paused, 42 web incl. 3 paused-screen), api coverage 91.98%, ruff/oxlint/tsc/prettier
clean, 156-page export builds under a base path.

## Cost

$0 — every control is deterministic. No paid call was made this milestone.

## Surprises / lessons

- **The obvious counter was the wrong one.** `rag_answers` looked like a ready-made
  spend log; it misses judge calls, reformulate retries, `/intent` and every embedding,
  while adding rows where no model ran. Wrong in both directions — a counter that
  undercounts cannot bound a bill and one that overcounts blocks paying users early.
- **`.nojekyll` is a silent, total failure mode**: GitHub Pages' Jekyll step drops
  `_next/`, so the site would deploy "successfully" and load with no JavaScript at all.
  The workflow now asserts it before publishing rather than trusting it.
- Testing the per-caller limiter needed no database or provider: it runs ahead of the
  routers, so a deliberately invalid body exercises it in isolation — and documents a
  real decision, that malformed requests still count, so probing cannot dodge the cap.

## Next

Deployment itself, on Jeronimo's go-ahead: Neon + Cloud Run (deployed **paused**), then
GitHub Pages, then unpause and run the runbook's verification gate.

## Deployment executed (same day, go-ahead in chat)

Order mattered: Pages enabled by API (the first workflow run failed exactly as the
docs warn — configure-pages 404s until Pages exists), repo variables set with the
DETERMINISTIC Cloud Run URL before the service existed, web deployed and verified
(basePath assets 200, deep links 200, API URL found baked in a chunk). Then Neon
(Jeronimo created the account — the one step an agent cannot do), full pg_dump restore
(91 MB, zero errors, zero re-embedding), secrets piped from .env without ever printing
them, and `gcloud run deploy` with SERVICE_PAUSED=true.

Verified live end-to-end: /health 200 `paused:true` WITH Neon answering through a cold
start; /pokemon/1 503 bilingual; CORS header for the Pages origin; and the public site
showing "PAUSED · PAUSADO" with the bilingual notice. Total LLM spend of the whole
deployment: $0 — it has never been unpaused.

Also cleaned: a stray `_report_work/` scratch tree (57k lines incl. node_modules) had
been committed to the docs repo by a broad `git add -A`; untracked and ignored.

## Post-deploy fix: sprites (same day)

Jeronimo unpaused, browsed to Golem, and the card had no image. Correct diagnosis in
his own question: the images were never uploaded — `data/` is gitignored by IP policy,
so they are in neither the repo nor the Docker image, and `/pokemon/76/sprite` answered
404 "not on disk".

Fix with zero code change: the 453 sprites (23 MB) went to a private GCS bucket,
mounted read-only into Cloud Run as a gen2 volume at `/gcs-data`, with `DATA_DIR`
pointed there — the endpoint reads them exactly as it reads the local directory. IP
posture unchanged: files are not distributed, only served through our API. Verified:
sprite 200 image/png in production, 475x475 loads in the page. (A red herring during
verification: `loading="lazy"` images never fire in a hidden automation tab —
`document.visibilityState === 'hidden'` — which briefly looked like the bug persisting.)
Cost: ~23 MB of GCS, well under a cent per month.

## Post-deploy fix 2: corrupted secrets (same day)

Jeronimo hit "400 API key not valid" on everything ai-studio (judge + candidate). The
degradation ladder behaved exactly as designed — vertex answered, the judge failed OPEN
with a warning, the failed candidate was isolated in /compare — but the root cause was
an embarrassment worth recording: **the shell's grep wrapper prints a "1 matches in 1
files:" header on stdout**, and piping `grep .env | ... | gcloud secrets create
--data-file=-` swallowed that header INTO the secret (len 74 = 21-char header + 53-char
key, prefix "1 ma" — the arithmetic was the diagnosis). The database secret survived
because it happened to be built via command substitution, which captured clean output.

Fix: re-added both secrets from `$(...)` substitution, verified by MASKED shape
comparison (length + 4-char prefix + equality flag — never printing a secret), disabled
the corrupt versions, rolled a revision (env-var secrets resolve at instance start).
Verified with one /chat forced through ai-studio: answered, `warnings: []` — generation
AND judge on the fixed key, ~$0.0002.

Lesson for the runbook: after creating any secret, verify its SHAPE (masked) against
the source before deploying on top of it. "Created version [1]" only proves bytes
arrived, not which bytes.
