-- Period-gated ticks (app_core/celery_schedule.py TASK_PERIODS): record the
-- calendar period (UTC) each tick last claimed, so a tick runs at most once
-- per hour/day no matter when it fires (delays, watchdog nudges, deploys).
ALTER TABLE task_runs ADD COLUMN IF NOT EXISTS last_period TIMESTAMPTZ;

-- Backfill from last_run so the deploy itself cannot re-run a period that
-- already ran under the old elapsed-time gate. Only fills NULLs (re-runnable).
UPDATE task_runs
SET last_period = date_trunc('hour', last_run AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
WHERE last_period IS NULL
  AND last_run IS NOT NULL
  AND task_name IN (
    'tax_income', 'generate_province_revenue', 'population_growth',
    'produce_unit_stockpiles', 'military_maintenance', 'war_supply_regen',
    'natural_disasters', 'loan_interest'
  );

UPDATE task_runs
SET last_period = date_trunc('day', last_run AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
WHERE last_period IS NULL
  AND last_run IS NOT NULL
  AND task_name = 'bond_tick';
