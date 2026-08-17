# Phase 7 — Next.js frontend

- **Goal:** Thin web UI over the public API: search, image drop-zone, cards, chat with citations, provider comparison.
- **Status:** done (2026-08-06) except 7.6, deferred with the 6.6 deployment decision

## Milestones

- [x] 7.1 apps/web scaffold (Next.js 16, App Router, static export, own package.json +
      pnpm-lock; no Dockerfile per guidelines) — oxlint + prettier + vitest from commit 1
      (devlog 0036)
- [x] 7.2 Search page: text box (mode + embedding-space selectors) + image drop-zone →
      /search endpoints (devlog 0036)
- [x] 7.3 Pokémon card + evolution chain views; one pre-rendered page per ingested id
      (devlog 0036)
- [x] 7.4 Chat view: citations, abstention, warnings, corrections indicator (devlog 0036)
- [x] 7.5 Provider comparison view (/compare) with judge verdicts, the self-graded
      caveat, shared-context proof and latency/token counts (devlog 0036)
- [ ] 7.6 Deploy with limited access; disclaimer in footer — **disclaimer done** (root
      layout, so no page can omit it); **deploy deferred** with the 6.6 decision:
      run it locally first, deploy only when a demo or portfolio moment calls for it

## API prerequisites landed this phase

- `CORS_ALLOWED_ORIGINS` allowlist (a literal `*` is stripped, never honored), registered
  outermost so a 401 still carries CORS headers.
- `GET /pokemon/{id}/sprite` — the UI's only image source, with a path-escape guard.

## Definition of done

- [x] Devlog per phase; READMEs current (root, apps/web); registered in CI, Makefile and
      the component map
- [x] UI consumes ONLY the public API (no direct DB or disk access — sprites included)
- [x] Tests green: 28 web (offline, fetch stubbed to throw) + 128 api; typecheck, lint,
      format clean; static export builds (156 pages)
- [x] Verified live in a real browser against the real stack: search, card + chain +
      sprite, chat with citation, comparison with judge verdicts, image search

## Open for Jeronimo

1. **Try it**: `make web-dev` with the API running — see `apps/web/README.md`.
2. **Deployment (7.6 + 6.6)**: still deferred by decision. The UI is a static export so
   hosting is near-free; what it needs is a reachable API, which is the 6.6 call.
   Note for that day: `NEXT_PUBLIC_API_KEY` ships to every browser and is NOT an access
   control — a real public deployment needs a different approach than the shared key.
