Log Alerts: UniqueViolation & Worker Timeout

This repository includes a scheduled GitHub Action `.github/workflows/log-alert.yml` that scans production logs for the following patterns:

- psycopg2.errors.UniqueViolation / "duplicate key value"
- WORKER TIMEOUT / CRITICAL WORKER TIMEOUT
- StringDataRightTruncation

When any matching lines are found in either the `web` or `celery-worker` service logs, the workflow will create a GitHub issue with the most recent matches for triage.

Setup / required secrets

- `RAILWAY_TOKEN`: A Railway API token with permission to read logs for the project. Add this to repository Secrets (Settings → Secrets → Actions).

Notes

- The workflow runs every 15 minutes by default and will create an issue when matches are detected. If you prefer a different cadence, edit the cron schedule in `.github/workflows/log-alert.yml`.
- The action requires the `railway` CLI and `jq` which are installed at runtime in the workflow.
- The created issue is labeled `logs`, `prod-alert`, and `triage` to help with routing.
