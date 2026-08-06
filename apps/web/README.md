# web

Thin web UI over the Pokédex AI API: search (text + image), Pokémon cards with
evolution chains, RAG chat with citations, and side-by-side provider comparison.

Next.js App Router, **static export** — no server runtime, no Dockerfile (per project
guidelines, frontends deploy as static). The browser calls the API directly, so the API
must allowlist this origin in `CORS_ALLOWED_ORIGINS`.

It consumes ONLY the public API. There is no database access, no server-side proxy and
no direct file access — including sprites, which come from `GET /pokemon/{id}/sprite`.

## Run in dev

Needs the API running (which needs PostgreSQL + an ingested corpus):

```bash
# 1. API, with this origin allowed
cd apps/api
CORS_ALLOWED_ORIGINS=http://localhost:3000 poetry run uvicorn api.main:app --factory --port 8000

# 2. UI
cd apps/web
cp .env.example .env.local     # point NEXT_PUBLIC_API_BASE_URL at the API
pnpm install
pnpm dev                       # http://localhost:3000
```

## Configuration

All build-time and public (`NEXT_PUBLIC_*` values are inlined into the bundle):

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | API origin. Empty = same origin as the UI. |
| `NEXT_PUBLIC_POKEDEX_MAX_ID` | Highest ingested Pokémon id (default 151). One page is pre-rendered per id, so changing it requires a rebuild. |
| `NEXT_PUBLIC_API_KEY` | Sent as `X-API-Key` when the API's gate is on. **Not a security control** — it ships to every browser. Fine for local use or a shared demo. |

## Build

```bash
pnpm build      # static site in out/
```

`out/` can be served by any static host. The build makes no API calls: every page is a
shell that fetches its own data in the browser.

## Test

```bash
pnpm test        # vitest + testing-library, jsdom
pnpm typecheck   # tsc --noEmit
pnpm lint        # oxlint
pnpm format:check
```

Unit tests are offline by construction: the setup file replaces `fetch` with a stub that
throws, so any un-faked network call fails the test loudly rather than reaching out.

## Pages

| Route | What it does |
|---|---|
| `/` | Text search (hybrid/vector/lexical, selectable embedding space) and an image drop-zone |
| `/pokemon/{id}/` | Card, base stats, abilities, evolution chain — one static page per ingested id |
| `/chat/` | RAG chat showing citations, abstentions, warnings and applied corrections |
| `/compare/` | Same context to every provider, each answer judged, with latency and token counts |

## Notes

- **oxlint, not eslint-config-next**: that package's registry metadata is missing the
  `time` field, which the machine's `minimumReleaseAge` supply-chain policy needs. oxlint
  is an allowed alternative in the project guidelines and needs no plugin chain.
- **Plain `<img>`, not `next/image`**: a static export has no image optimizer to run.
- The IP disclaimer lives in the root layout, so no page can ship without it.
