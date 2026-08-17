# 0025 — 2026-08-06 — Data Access audit logs enabled for aiplatform.googleapis.com

## What was done

Closed the last open recommendation from the billing-anomaly investigation (devlog
0022): enabled **Data Access audit logs** (`DATA_READ` + `DATA_WRITE`) for
`aiplatform.googleapis.com` on `pokedex-rag-504617`. Any future predict/generate call
— by anyone or anything with access to this project — now leaves a queryable trace in
Cloud Logging. This is the log stream that was missing during the Model Garden
incident; Admin Activity logs (always-on) only cover control-plane actions like
deploys, never actual usage.

Applied via a read-modify-write of the project's IAM policy (`auditConfigs` is part of
the same policy object as `bindings`, set together via `setIamPolicy`):

```python
policy["auditConfigs"] = [{
    "service": "aiplatform.googleapis.com",
    "auditLogConfigs": [{"logType": "DATA_READ"}, {"logType": "DATA_WRITE"}],
}]
```

Verified afterward: `gcloud projects get-iam-policy ... --format="value(auditConfigs)"`
shows the new config; `bindings.role` still lists all 13 pre-existing roles untouched.

## Why

Directly closes the gap devlog 0022 flagged: the €4.62 charge was unattributable
specifically because this log stream didn't exist. Now it will, for next time.

## How it was tested

Read-only verification only (`get-iam-policy` before/after) — no live API call made to
prove the log stream works end-to-end (would cost a fraction of a cent and add noise
without changing the config's correctness, which is confirmed by the applied policy
itself).

## Cost

$0 — IAM policy operations aren't billed.

## Surprises / lessons

`gcloud ... --format=json > file` truncated silently mid-JSON in this environment
(cut off well before the actual policy content ended, producing invalid JSON with no
error at write time — only surfaced later as a `JSONDecodeError` when re-reading it).
Piping through a Python `subprocess.run(..., capture_output=True)` instead of a shell
redirect avoided it entirely. Worth remembering for any future large `gcloud
... --format=json` capture in this environment: don't trust `>` redirects for big
output, capture in-process instead.

## Next

Both billing-incident recommendations from 0022 are now closed (budget guard: 0023;
audit logging: this entry). Phase 4 is done. Starting Phase 5 (evals + self-correction).
