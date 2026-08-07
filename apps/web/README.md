# web

The Pokédex device: a single-screen UI where everything happens inside a red dual-panel
Pokédex rendered in **original CSS** over a black stage (no franchise art asset — see
the IP policy). Next.js App Router, **static export**, pnpm, oxlint.

Type in the right panel; the device classifies what you want (via `POST /intent`) and
the left screen answers:

| You type | It shows |
| --------------------------------------- | ------------------------------------------------------------- |
| `Gengar`, `25`, "Dime todo sobre Gengar" | that Pokémon's card |
| "¿de qué tipo es Bulbasaur?" | a grounded RAG answer with citations |
| "¿Pickachu es más fuerte que Gengar?" | the deterministic versus table + a cited narrative analysis |
| an image (picker or phone camera) | a browsable carousel of matching Pokémon (d-pad to step) |

Misspellings are fine — name resolution is fuzzy. Camera photos are downscaled to a
small JPEG client-side, which also converts iPhone HEIC.

The **provider A/B toggle** applies only to LLM-generated answers: one `/compare` call
feeds both the in-screen answer (labelled with its provider) and the full judged
comparison rendered **below** the chassis.

## Run in dev

Needs the API running (which needs PostgreSQL + an ingested corpus + migration 0007):

```bash
cd apps/api
CORS_ALLOWED_ORIGINS=http://localhost:3000 poetry run uvicorn api.main:app --factory --port 8000

cd apps/web
cp .env.example .env.local     # point NEXT_PUBLIC_API_BASE_URL at the API
pnpm install
pnpm dev                       # http://localhost:3000
```

## Configuration

All build-time and public (`NEXT_PUBLIC_*` values are inlined into the bundle):

| Variable | Purpose |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_API_BASE_URL` | API origin. Empty = same origin as the UI. |
| `NEXT_PUBLIC_POKEDEX_MAX_ID` | Highest ingested Pokémon id (default 151). One page is pre-rendered per id, so changing it requires a rebuild. |
| `NEXT_PUBLIC_API_KEY` | Sent as `X-API-Key` when the API's gate is on. **Not a security control** — it ships to every browser. |

## Routes

| Route | What it is |
| ---------------- | ------------------------------------------------------------------------ |
| `/` | the device |
| `/pokemon/{id}/` | the device, deep-linked to that card (151 pre-rendered static pages) |
| `/chat/`, `/compare/` | aliases of `/` kept for old bookmarks (a static export cannot redirect) |

## Build & test

```bash
pnpm build       # static site in out/ (156 pages; the build makes no API calls)
pnpm test        # 38 offline tests: state machine, intent dispatch, device behaviour
pnpm typecheck   # tsc --noEmit
pnpm lint        # oxlint (incl. jsx-a11y)
pnpm format:check
```

The state machine (`src/lib/pokedexMachine.ts`) is pure and owns the invariants worth
knowing: a failure never blanks the screen; stale async responses are dropped by a
sequence counter allocated synchronously (StrictMode-safe); the provider-comparison
panel is *derived* from the answer's origin, so it structurally cannot appear for a
card or image lookup. `src/lib/usePokedex.ts` is the only file that awaits API calls.

## Notes

- **oxlint, not eslint-config-next** (that package trips the machine's
  `minimumReleaseAge` supply-chain policy); plain `<img>`, not `next/image` (static
  export has no optimizer); no webfont (the LCD look is `ui-monospace`).
- Mobile: one panel at a time, switched by the tabs in the hinge; results auto-switch
  to the display panel.
- The IP disclaimer lives in the root layout, so no page can ship without it.
