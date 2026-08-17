"""Budget cost guard: unlinks the billing account from pokedex-rag-504617 once Cloud
Billing reports current spend at or above the linked budget's amount.

Mirrors the existing `lumi-stop-billing` function on the Torylib project (same billing
account, same pattern) — Project Billing Manager scoped to this one project only, so
it can never touch billing for any other project on the shared billing account.

Triggered by every threshold crossing of the `pokedex-rag-cost-guard` budget (33/66/
100%) via Pub/Sub; no-ops below 100%, disables billing once spend reaches the amount.
"""

import base64
import json
import os

import functions_framework
from googleapiclient import discovery

PROJECT_ID = os.environ.get("GCP_PROJECT", "pokedex-rag-504617")


@functions_framework.cloud_event
def stop_billing_on_budget_exceeded(cloud_event) -> None:
    payload = json.loads(base64.b64decode(cloud_event.data["message"]["data"]).decode("utf-8"))
    print(f"Received budget alert: {payload}")

    cost_amount = payload.get("costAmount", 0)
    budget_amount = payload.get("budgetAmount", 0)
    print(f"Cost: {cost_amount}, Budget: {budget_amount}")

    if cost_amount < budget_amount:
        print(f"Budget not exceeded. Current cost: {cost_amount}, Budget: {budget_amount}")
        return

    print(
        f"Budget exceeded! Current cost: {cost_amount}, Budget: {budget_amount}. "
        f"Disabling billing for {PROJECT_ID}"
    )
    billing = discovery.build("cloudbilling", "v1", cache_discovery=False)
    billing.projects().updateBillingInfo(
        name=f"projects/{PROJECT_ID}", body={"billingAccountName": ""}
    ).execute()
    print(f"Billing disabled for {PROJECT_ID}")
