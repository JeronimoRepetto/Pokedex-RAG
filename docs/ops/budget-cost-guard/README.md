# budget-cost-guard

Auto-disables billing for `pokedex-rag-504617` when spend hits the linked budget's
amount. Same pattern as the existing `lumi-stop-billing` function on Torylib (same
billing account) — Project Billing Manager scoped to **this project only**, so it can
never touch billing on any other project sharing the account.

Deployed 2026-08-06. Not tracked by CI/CD — redeploy manually with the command below
when `main.py` changes.

## Topology

```
Cloud Billing budget "pokedex-rag-cost-guard" (€30/month, scoped to pokedex-rag-504617)
  -> thresholds 33% / 66% / 100% of CURRENT_SPEND
  -> Pub/Sub topic projects/pokedex-rag-504617/topics/billing-cost-guard-alerts
  -> Cloud Function (gen2) budget-cost-guard, us-central1
  -> runs as budget-cost-guard-sa@pokedex-rag-504617.iam.gserviceaccount.com
     (roles: billing.projectManager, serviceusage.serviceUsageConsumer — nothing else)
  -> if cost >= budget: cloudbilling.projects.updateBillingInfo(billingAccountName="")
```

Below 100% of the budget the function only logs and returns — it never acts before
the actual limit is reached, even though it's invoked at every threshold.

## View / edit

Console: https://console.cloud.google.com/functions/details/us-central1/budget-cost-guard?project=pokedex-rag-504617

Logs:
```bash
gcloud functions logs read budget-cost-guard --project=pokedex-rag-504617 --region=us-central1 --gen2 --limit=20
```

## Redeploy after editing `main.py`

```bash
cd docs/ops/budget-cost-guard
gcloud functions deploy budget-cost-guard \
  --project=pokedex-rag-504617 \
  --gen2 \
  --runtime=python312 \
  --region=us-central1 \
  --source=. \
  --entry-point=stop_billing_on_budget_exceeded \
  --trigger-topic=billing-cost-guard-alerts \
  --service-account=budget-cost-guard-sa@pokedex-rag-504617.iam.gserviceaccount.com \
  --set-env-vars=GCP_PROJECT=pokedex-rag-504617 \
  --no-allow-unauthenticated \
  --memory=256Mi \
  --timeout=60s
```

The Eventarc-managed Pub/Sub push subscription needs `roles/run.invoker` on the
underlying Cloud Run service for `budget-cost-guard-sa` — `gcloud functions deploy`
did **not** grant this automatically the first time (a genuine gap hit while building
this); if a fresh deploy ever silently stops triggering, check this first:

```bash
gcloud run services get-iam-policy budget-cost-guard --project=pokedex-rag-504617 --region=us-central1
# if empty, re-grant:
gcloud run services add-iam-policy-binding budget-cost-guard \
  --project=pokedex-rag-504617 --region=us-central1 \
  --member="serviceAccount:budget-cost-guard-sa@pokedex-rag-504617.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

## To undo (re-enable billing after it trips)

Console → Billing → link a billing account to `pokedex-rag-504617` again (manual,
by design — this is a hard stop, not a pause).

## Verified 2026-08-06

Live end-to-end smoke test with a synthetic under-budget Pub/Sub message
(`costAmount: 4.64, budgetAmount: 30`) → function returned HTTP 200, logged
"Budget not exceeded", took no action (confirmed `aiplatform.googleapis.com` stayed
enabled). The actual billing-disable branch was **not** live-tested — deliberately, to
avoid actually cutting billing on the real project just to prove the code path — the
Cloud Billing API call is the same one already proven working by `lumi-stop-billing`.
