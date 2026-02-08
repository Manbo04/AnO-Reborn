# Metrics & Auditing (new)

This project now includes lightweight metrics and audit hooks to help monitor task performance and trades.

What was added:

- `helpers.record_task_metric(task_name, duration_seconds)` — records task duration to DB (`task_metrics` table) and emits a Prometheus histogram if `prometheus_client` is available.
- `helpers.record_trade_event(offer_id, offerer, offeree, resource, amount, price, trade_type)` — records trade events to DB (`trade_events` table) and increments a Prometheus counter when available.
- Migration script: `scripts/add_metrics_tables.py` — creates `trade_events` and `task_metrics` tables when run.
- Instrumentation:
  - `market.accept_trade` now calls `record_trade_event(...)` after successful trades.
  - Long-running tasks like `tax_income` and `generate_province_revenue` call `record_task_metric(...)` after completing.

How to enable Prometheus metrics (optional):

1. Install the Python client:

   pip install prometheus_client

2. Expose an HTTP endpoint for the Prometheus metrics exposition format. For a simple approach, you can add an endpoint in your WSGI app like:

   from prometheus_client import generate_latest

   @app.route('/metrics')
   def metrics():
       return generate_latest()

3. Configure your Prometheus server to scrape `<your_app>/metrics`.

Notes & recommendations:

- The helpers are best-effort; DB write/Prometheus errors are swallowed to avoid impacting gameplay flows.
- Recommended: run `python scripts/add_metrics_tables.py` as part of the deployment/migration process to create the new tables.
- The `task_metrics` table stores raw duration values; we recommend a nightly job to aggregate percentiles and store them in a monitoring system if you need long-term retention.

If you'd like, I can:
- Add a `/metrics` endpoint to the Flask app and update the deployment docs (Prometheus config snippet) ✅
- Add a background aggregator job to compute and store percentiles of task durations (e.g., 95th/99th) ✨
- Add a small admin page showing recent trade events for manual inspection 🔍

Which of the above would you like next?
