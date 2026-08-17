# 0023 — 2026-08-06 — Budget cost guard: auto-disable billing at €30

## What was done

Following the billing anomaly (0021, 0022), Jeronimo asked for a hard spending cap on
`pokedex-rag-504617`: email alert at €10, automatic reject of further spend at €30.
Built and deployed:

- **Cloud Billing budget** `pokedex-rag-cost-guard`: €30/month, filtered to
  `projects/pokedex-rag-504617` only (doesn't touch the billing account's other
  project). Threshold rules at 33/66/100% of current spend (~€10/€20/€30) — default
  email notification to billing admins at each.
- **Pub/Sub topic** `billing-cost-guard-alerts` wired as the budget's notification
  channel.
- **Cloud Function** `budget-cost-guard` (gen2, Python 3.12, `us-central1`), triggered
  by that topic. Below the budget amount: logs and returns. At or above it: calls
  `cloudbilling.projects.updateBillingInfo` to unlink the billing account, which stops
  every paid GCP call the project can make.
- **Dedicated service account** `budget-cost-guard-sa`, scoped to exactly two roles on
  the project (not the billing account): `roles/billing.projectManager` (can
  assign/disable *this project's* billing link only) and
  `roles/serviceusage.serviceUsageConsumer`. It cannot touch any other project's
  billing, including Torylib/LumiTales on the same billing account.

Source + a redeploy runbook committed at `docs/ops/budget-cost-guard/` (local docs
repo — this is personal cost-guard infra, not part of the product).

## Why

Mirrors an existing, working pattern: Jeronimo already runs `lumi-stop-billing` on the
Torylib project against the same billing account (Project Billing Manager scoped to
that one project, same Pub/Sub-triggered-function shape). Copying a proven pattern
beat designing a new one — the first attempt here used a narrower
`serviceusage.serviceUsageAdmin` role to disable just `aiplatform.googleapis.com`
instead of unlinking billing; switched to match Jeronimo's existing precedent once he
showed it (consistency, and it's the same mechanism already validated in production
on another of his projects).

## How it was tested

Full pipeline exercised live with a synthetic Pub/Sub message
(`{"budgetDisplayName": "pokedex-rag-cost-guard", "costAmount": 4.64, "budgetAmount": 30}`)
— matches actual current spend, well under budget:

- First attempt failed: Eventarc's Pub/Sub push subscription lacked `roles/run.invoker`
  on the underlying Cloud Run service for `budget-cost-guard-sa` — `gcloud functions
  deploy` did not grant this automatically. Fixed with one
  `run services add-iam-policy-binding`.
- Second attempt failed: `TypeError` — the function needed the
  `@functions_framework.cloud_event` decorator for gen2's CloudEvent signature; without
  it, the framework tried the legacy 2-arg `(data, context)` signature. Fixed and
  redeployed.
- Third attempt: **HTTP 200**, function logged the no-op path, and
  `aiplatform.googleapis.com` was confirmed still enabled afterward — the safe branch
  works end-to-end.

The billing-disable branch itself was **not** exercised live (would have actually cut
billing on the real project just to prove a code path) — the `updateBillingInfo` call
is the same one already proven live by `lumi-stop-billing`, and the IAM grant needed
for it was independently confirmed present.

## Cost

$0 — budget/topic/function/IAM operations aren't billed; the two test Pub/Sub messages
are within any project's free tier.

## Surprises / lessons

- `gcloud functions deploy --gen2 --trigger-topic=...` does **not** automatically grant
  the trigger's service account `run.invoker` on the resulting Cloud Run service when a
  custom `--service-account` is specified — worth checking explicitly after any gen2
  Pub/Sub-triggered deploy, not just this one.
- Gen2 Cloud Functions require the `functions_framework.cloud_event` decorator to get
  the CloudEvent signature; omitting it silently falls back to the legacy background-
  function signature and fails at the first real invocation, not at deploy time.
- Reusing an already-proven pattern from Jeronimo's other project (LumiTales/Torylib)
  was faster and lower-risk than the from-scratch design in 0021 — ask about existing
  precedent before designing new ops infrastructure.

## Next

Awaiting Jeronimo's decision on the Data Access audit logging recommendation from
0022. Once the cost-guard is trusted, resume 4.2 (LIVE SPIKE + ADR-0004) with a written
cost estimate first.
