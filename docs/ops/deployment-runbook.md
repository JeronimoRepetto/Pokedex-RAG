# Deployment runbook — Cloud Run + managed Postgres (Phase 6.6)

Target: the `apps/api` image on Cloud Run, backed by a managed pgvector Postgres,
reachable only with an API key. Everything here is written to be re-runnable and
reversible; nothing in this file has been executed yet — it is the plan plus the
verification gates.

**Status: DEPLOYED (PAUSED) 2026-08-07.**
- Web: https://jeronimorepetto.github.io/Pokedex-RAG/ (GitHub Pages, build_type=workflow)
- API: https://pokedex-api-833646162998.europe-west1.run.app (Cloud Run, image `:d49287a`,
  `SERVICE_PAUSED=true`, `DAILY_LLM_CALL_LIMIT=250`, `PER_CALLER_DAILY_LIMIT=25`, no API_KEYS)
- DB: Neon eu-central-1 (PostgreSQL 18), corpus restored via pg_dump (151/730/1913 rows,
  alembic 0008), $0 — no re-embedding
- Switch: `make cloud-on` / `make cloud-off` / `make cloud-status`
- Sprites: GCS bucket `pokedex-rag-sprites-504617` mounted read-only at `/gcs-data`
  (Cloud Run gen2 volume), `DATA_DIR=/gcs-data` — zero code change, the same endpoint
  serves them. The image itself carries no sprite files (IP policy). **After any local
  sprite re-ingest, re-sync with:** `gcloud storage cp -r data/sprites
  gs://pokedex-rag-sprites-504617/`. Gotcha: run gcloud volume-mount commands from Git
  Bash with `MSYS_NO_PATHCONV=1` or `/gcs-data` gets mangled into a Windows path.
(The CORS gap the earlier draft listed was closed in Phase 7.) Executing this runbook creates billable resources and
requires Jeronimo's explicit go-ahead (see the cost estimate in `cost-log.md`).

## Preconditions

- [ ] `docker build -f apps/api/Dockerfile -t pokedex-api:local .` succeeds from the
      repo root (verified 2026-08-06 — the Dockerfile was missing `libs/embeddings` and
      `libs/llm-gateway` until this milestone fixed it; devlog 0034).
- [ ] Local run of that image passes: `/health` 200, gated route 401 without a key and
      200 with one (verified 2026-08-06 against the local database).
- [ ] Tests green and ruff clean in every component.
- [ ] `gcloud auth login` + the project set explicitly (`pokedex-rag-504617` — gcloud's
      default on this machine points elsewhere).
- [ ] Budget guard `pokedex-rag-cost-guard` still active (€30/month, alerts at 33/66/100%).

## 1. Database — Neon free tier

Neon is the choice because the free tier includes pgvector and needs no VPC connector
from Cloud Run; Cloud SQL would cost ~€8-10/month minimum for an always-on instance
plus a connector.

1. Create a Neon project, region closest to the Cloud Run region.
2. Enable pgvector: `CREATE EXTENSION IF NOT EXISTS vector;` (migration 0003 also runs
   this, but doing it once by hand confirms the tier allows it before anything else).
3. Copy the pooled connection string; convert to the SQLAlchemy form used by this repo:
   `postgresql+psycopg://<user>:<password>@<host>/<db>?sslmode=require`.
4. Apply migrations from the workstation (the pipeline image also works):

   ```bash
   cd apps/data-pipeline
   DATABASE_URL='postgresql+psycopg://...' poetry run pipeline db upgrade
   DATABASE_URL='postgresql+psycopg://...' poetry run pipeline db current   # expect 0006
   ```

5. Load data. The free tier's storage limit (~0.5 GB) comfortably fits Gen 1
   (579 documents, 1032 embeddings in the Gemini space). Options:
   - Re-run `ingest` + `build-docs` + `embed` against the remote URL — costs another
     full embedding pass (see the cost estimate; this is the expensive path), or
   - `pg_dump` the local database and restore into Neon — no API calls, no new cost.
     **Preferred.** Verify afterwards with `pipeline status` against the remote URL.
6. Decide which embedding spaces to ship. The EmbeddingGemma space (`space_id=2`) is
   only usable if the deployed image carries torch — it does NOT (the `local` group is
   excluded on purpose). Ship the Gemini space only, and leave
   `LOCAL_EMBEDDING_SPACE_LABEL` empty in the deployed configuration so the space is
   not even registered.

## 2. Secrets

Never as plain Cloud Run env vars: create them in Secret Manager and reference them.

```bash
PROJECT=pokedex-rag-504617
printf '%s' 'postgresql+psycopg://...' | gcloud secrets create pokedex-database-url \
  --project=$PROJECT --data-file=-
printf '%s' "$(openssl rand -hex 32)" | gcloud secrets create pokedex-api-key \
  --project=$PROJECT --data-file=-
printf '%s' '<ai-studio-key>' | gcloud secrets create pokedex-ai-studio-key \
  --project=$PROJECT --data-file=-
printf '%s' '<langfuse-secret>' | gcloud secrets create pokedex-langfuse-secret \
  --project=$PROJECT --data-file=-
```

**After creating each secret, verify its shape (masked) before deploying on it** —
piping grep output through shell wrappers can smuggle header noise into the value
(it happened: a "1 matches in 1 files:" header ended up inside the AI Studio key):

```bash
V=$(gcloud secrets versions access latest --secret=NAME --project=$PROJECT)
echo "len=${#V} prefix=$(echo "$V" | cut -c1-4)"   # compare against the source's shape
```

Grant the runtime service account `roles/secretmanager.secretAccessor` on each. Use a
dedicated service account, not the default compute one:

```bash
gcloud iam service-accounts create pokedex-api --project=$PROJECT
# Vertex AI access for embeddings + generation:
gcloud projects add-iam-policy-binding $PROJECT \
  --member=serviceAccount:pokedex-api@$PROJECT.iam.gserviceaccount.com \
  --role=roles/aiplatform.user
```

## 3. Build and push

```bash
gcloud artifacts repositories create pokedex --repository-format=docker \
  --location=europe-west1 --project=$PROJECT
IMAGE=europe-west1-docker.pkg.dev/$PROJECT/pokedex/api:$(git rev-parse --short HEAD)
docker build -f apps/api/Dockerfile -t "$IMAGE" .
docker push "$IMAGE"
```

Tag with the git SHA, never `latest`: a rollback has to name an exact previously-working
image.

## 4. Deploy

```bash
gcloud run deploy pokedex-api \
  --project=$PROJECT --region=europe-west1 --image="$IMAGE" \
  --service-account=pokedex-api@$PROJECT.iam.gserviceaccount.com \
  --allow-unauthenticated \
  --min-instances=0 --max-instances=3 \
  --memory=1Gi --cpu=1 --timeout=120s --concurrency=20 \
  --set-env-vars=ENVIRONMENT=production,LOG_LEVEL=INFO,GCP_PROJECT_ID=$PROJECT,\
EMBEDDING_MODEL=gemini-embedding-2,EMBEDDING_LOCATION=global,EMBEDDING_DIMENSIONS=768,\
EMBEDDING_SPACE_LABEL=gemini-embedding-2-768-v1,GENERATION_MODEL=gemini-3.6-flash,\
GENERATION_LOCATION=global,LLM_PRIMARY=vertex-gemini,LLM_FALLBACK=ai-studio-gemini,\
JUDGE_PROVIDER=ai-studio-gemini,AI_STUDIO_MODEL=gemini-3.5-flash-lite \
  --set-secrets=DATABASE_URL=pokedex-database-url:latest,\
API_KEYS=pokedex-api-key:latest,\
AI_STUDIO_API_KEY=pokedex-ai-studio-key:latest,\
LANGFUSE_SECRET_KEY=pokedex-langfuse-secret:latest
```

Notes on the flags that matter:

- `--allow-unauthenticated` lets requests reach the container; the app's own API-key
  middleware is the access gate. IAM auth would also work but makes the demo unusable
  from a browser or `curl` without gcloud tokens.
- `--min-instances=0` means cold starts (a few seconds) and **zero cost when idle** —
  the whole point for a portfolio deployment.
- `--max-instances=3` is the blast-radius cap: it bounds how many concurrent LLM calls
  a runaway client (or a crawler) can trigger. This is the money guardrail, not a
  performance setting.
- `PORT` is injected by Cloud Run; the image honors it (`CMD` uses `${PORT:-8000}`).
- `EMBEDDING_LOCATION=global` — gemini-embedding-2 404s in any regional endpoint (ADR-0002).
- `LOCAL_EMBEDDING_*` deliberately unset: no torch in the image.

## 5. Verification gate

```bash
URL=$(gcloud run services describe pokedex-api --project=$PROJECT \
  --region=europe-west1 --format='value(status.url)')
KEY=$(gcloud secrets versions access latest --secret=pokedex-api-key --project=$PROJECT)

curl -s -o /dev/null -w '%{http_code}\n' "$URL/health"                    # expect 200
curl -s -o /dev/null -w '%{http_code}\n' "$URL/pokemon/1"                 # expect 401
curl -s -H "X-API-Key: $KEY" "$URL/pokemon/1" | head -c 120               # expect JSON
curl -s -H "X-API-Key: $KEY" -X POST "$URL/search/text" \
  -H 'Content-Type: application/json' -d '{"query":"grass starter"}'      # expect hits
curl -s -H "X-API-Key: $KEY" -X POST "$URL/chat" \
  -H 'Content-Type: application/json' \
  -d '{"question":"what type is bulbasaur?"}'                             # PAID: one call
```

The `/chat` check is the only paid step here. Do it once, then check Langfuse received
the trace and `rag_answers` got the row.

## 6. Rollback

```bash
gcloud run revisions list --service=pokedex-api --project=$PROJECT --region=europe-west1
gcloud run services update-traffic pokedex-api --project=$PROJECT \
  --region=europe-west1 --to-revisions=<previous-revision>=100
```

Database migrations are NOT rolled back by this. Migration 0006 has a working
`downgrade()`, but it deletes that space's embeddings — never run it against a
deployment holding data you want.

## 7. Teardown (stop all charges)

```bash
gcloud run services delete pokedex-api --project=$PROJECT --region=europe-west1
gcloud artifacts repositories delete pokedex --project=$PROJECT --location=europe-west1
# Neon: delete the project from its console.
```

Secrets can stay (they cost fractions of a cent) but rotate the API key if the
deployment URL was ever shared.

## 8. Pause and resume (Phase 9)

Verified against the providers' own documentation, not assumed:

| Layer | Idle behaviour | Source |
|---|---|---|
| Cloud Run `--min-instances=0` | *"you are not billed when instances are idle"* | Cloud Run docs, min-instances |
| Neon free plan | *"automatically scales to zero after 5 minutes"*, resumes *"within a few hundred milliseconds"*; cannot be disabled on Free | Neon docs, scale-to-zero |
| Cloud SQL (rejected) | Stoppable, but *"charges for storage and IP addresses continue to apply"* | Cloud SQL docs, start/stop |

So **there is nothing to pause for cost**: with no traffic the stack idles at zero by
itself. What the pause switch buys is different — it stops a *bot* from making the
service spend, and it gives visitors an honest message instead of a broken page.

```bash
# off — every route except /health answers 503 with a bilingual message
gcloud run services update pokedex-api --region=europe-west1 --update-env-vars SERVICE_PAUSED=true
# on
gcloud run services update pokedex-api --region=europe-west1 --update-env-vars SERVICE_PAUSED=false
```

Either takes about fifteen seconds (it creates a new revision). `/health` keeps
answering while paused and reports `"paused": true` — that is how the web tells
"switched off on purpose" apart from "unreachable", which get different messages.

**Long absences.** Deleting the service is the only provably-zero state. Cloud Run also
publishes a *deterministic* URL (`SERVICE-PROJECTNUMBER.REGION.run.app`) alongside the
hash one; **build the web against the deterministic URL** and delete/recreate keeps
working. Recreating is one `gcloud run deploy` from the same Artifact Registry image.

## 9. Spend controls (Phase 9)

Three independent layers, none of which relies on the browser keeping a secret:

1. **Daily ceiling inside the LLM gateway** (`DAILY_LLM_CALL_LIMIT`). Counted where the
   money is spent, not per request — one `/compare` can fan out to nine paid calls, so
   counting requests would undercount by ~9x. The counter lives in PostgreSQL because
   Cloud Run runs several instances and an in-memory counter would make the real limit
   (instances x limit). Recommended: **250** (~$0.30/day at the measured $0.0012/answer).
2. **Per-caller daily cap** (`PER_CALLER_DAILY_LIMIT`) on `/chat` and `/compare`, so one
   abuser cannot eat the global allowance alone. Callers are bucketed by a **hash** of
   their address; the address itself is never stored (guideline 7).
3. **`--max-instances=3`** bounds concurrency, and the already-deployed
   `budget-cost-guard` function hard-disables billing at EUR 30/month.

At either limit the API answers **429** with a bilingual body, and the free endpoints
(cards, search, `/matchup`, deterministic `/intent`) keep working — a public demo should
degrade, not die.

**On the API key, honestly:** `NEXT_PUBLIC_API_KEY` is compiled into the browser bundle
and readable by anyone. It is not a security control. For a public deployment prefer
leaving `API_KEYS` **unset** rather than shipping false assurance — the quota, the
per-caller cap and the pause switch are the real controls.

## 10. Web on GitHub Pages (Phase 9)

The site is a static export, so hosting is free and always on regardless of whether the
API is running.

- Repository -> Settings -> Pages -> Source: **GitHub Actions**.
- Set repository **variables** (not secrets — `NEXT_PUBLIC_*` values ship to every
  browser, so storing them as secrets would only pretend they are private):
  `NEXT_PUBLIC_API_BASE_URL` (the Cloud Run deterministic URL) and optionally
  `NEXT_PUBLIC_API_KEY`.
- `.github/workflows/deploy-web.yml` builds and publishes on push to `main` and on
  `workflow_dispatch` — the manual trigger matters because the API URL is baked in at
  build time, so changing it requires a rebuild, not just a redeploy of the API.
- Two Pages-specific requirements the workflow asserts before publishing:
  `basePath=/<repo>` (a project site is not served from the domain root) and
  **`.nojekyll`** (Jekyll silently drops `_next/`, which would ship the site with no
  JavaScript at all).
- Then add the Pages origin to `CORS_ALLOWED_ORIGINS` on the API and redeploy it.

## Known gaps to close before calling this production

- `/health` does not check Vertex AI or Langfuse reachability, only the database — a
  provider outage surfaces as failing `/chat` calls, not as a degraded health status.
- No anti-bot challenge. The quota bounds the money, not the request volume; if a bot
  ever burns the daily allowance for real visitors, add Cloudflare Turnstile in front of
  the paid routes.
- The per-caller cap keys on `X-Forwarded-For`, which a determined abuser can rotate.
  It raises the cost of abuse; the global ceiling is what actually bounds it.
