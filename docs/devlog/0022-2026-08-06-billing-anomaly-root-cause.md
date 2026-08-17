# 0022 — 2026-08-06 — Billing anomaly: root cause found, attribution unresolved

## What was done

Jeronimo pulled the full Cloud Billing CSV (`PersonalBillingAccount_Reports,
2026-08-01 — 2026-08-31.csv`), which the 3-of-8 SKU table in the console UI had been
hiding. It resolves devlog 0021's open question exactly:

| Product | Subtotal (€) |
|---|---|
| **Agent Platform Model Garden** | **4.53** |
| Vertex Embeddings API | 0.08 |
| Cloud DNS | 0.03 |
| Cloud Build / Firestore / Gemini on Agent Platform / Cloud Run | 0.00 |
| **Total** | **4.64** |

"Vertex Embeddings API" (€0.08) and "Gemini on Agent Platform" (€0.00) are exactly the
logged Phase 0–3 work. "Agent Platform Model Garden" — Google's product for
open/partner models (Gemma, Llama, Mistral, ...) served through Vertex — is new, and is
the entire unexplained amount.

Followed up on the two open leads from 0021:

- **No deployed resource, anywhere.** Extended the endpoint/model scan from
  `us-central1` alone to 13 regions (`us-central1/east1/east4/east5/west1/west4`,
  `europe-west1/2/3/4`, `asia-southeast1`, `asia-northeast1/3`): zero endpoints, zero
  models in every one. Rules out a Model Garden "Deploy" (dedicated GPU instance,
  bills per node-hour) left running anywhere reachable.
- **No control-plane action either.** Admin Activity audit logs (`cloudaudit.googleapis.com/activity`
  — always-on, cannot be disabled, unlike Data Access logs) for 2026-08-04 through
  2026-08-06 show zero `aiplatform.googleapis.com` entries of any kind — no
  `CreateEndpoint`, `DeployModel`, `UploadModel`. Only `serviceusage`/`cloudresourcemanager`/
  `cloudbilling` entries from project setup. A deploy via Console, `gcloud`, or the SDK
  would always hit this log; its absence is strong evidence no deploy ever happened.
- **The 0.6 spike (devlog 0006) is cleared.** Jeronimo asked whether this was an
  earlier Claude Code session. Re-read 0006 closely: `gemma-4-26b-a4b-it-maas` was only
  ever *listed* (a free catalog browse, explicitly called out as a distinct thing from
  invoking a model — "Listing alone is not verification" is literally the lesson
  recorded that day) — never called. That spike's cost is itemized and closed at
  < $0.01 (≈10 embed calls + 1 five-token generation), with nothing budgeted or logged
  for a Model Garden model.

## Conclusion

The charge is real Model Garden **usage** (a predict/generate call to a hosted
open/partner model), not idle infrastructure — but *which* call, made by what actor
(a Claude Code session, a manual API/`gcloud` test, anything else with access to this
GCP account), is **unattributable with what's available**: Data Access audit logs for
`aiplatform.googleapis.com` were never enabled on this project, so the one log stream
that would show individual predict calls doesn't exist for the period in question.
No devlog, cost-log entry, or script anywhere in this repo admits to invoking a Model
Garden model — so if an agent session did make this call, it did so without writing
the cost estimate this project's own guidelines require before any paid call. That
process gap is the actionable finding, independent of exact attribution.

## Recommended (both are account-setting changes)

1. Enable Data Access audit logs for `aiplatform.googleapis.com` on
   `pokedex-rag-504617`, so any future predict/generate call — by anyone or anything —
   leaves a trace. **Not done yet** — needs Jeronimo's go-ahead.
2. ~~A Cloud Billing budget alert on this project~~ **Done same day:** Cloud Billing
   budget `pokedex-rag-cost-guard`, €30/month, scoped to `projects/pokedex-rag-504617`
   only (not the rest of the billing account), threshold rules at 33/66/100% of current
   spend (~€10/€20/€30) — email to billing admins at each. This is notification only;
   an actual auto-reject at €30 needs a Pub/Sub + Cloud Function wired to disable
   billing on the project, proposed but not yet built (it would stop every GCP call the
   project makes, not just LLM ones — worth one more explicit confirmation given the
   blast radius).

## Cost

$0 (read-only `gcloud` investigation only).

## Surprises / lessons

- The billing console's default SKU table view (3-of-N, sorted) can hide the actual
  cost driver behind pagination — the CSV export from Reports was what actually
  resolved it. Pull the CSV first next time, don't trust the summary widget.
- Admin Activity logs (always-on) are enough to rule out *deploys*; ruling out *usage*
  needs Data Access logs, which are opt-in and were off here. The two log streams
  answer different questions — a real gap worth closing given the first go-round
  produced an unattributable charge.

## Next

Awaiting Jeronimo's decision on the two recommendations above and on how to proceed
with 4.2 (whether to still spike Vertex MaaS Gemma given this, or run AI-Studio-only
first).
