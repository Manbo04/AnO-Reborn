-- Migration: 0059 - Add joined_at to coalitions_legacy for member seniority sort
-- Date: 2026-09-01
-- Suggested by fikusmikus: sort the coalition members table by join time.
-- coalitions_legacy never tracked when a member joined, so this backfills
-- existing rows to the migration date (true history was never recorded --
-- honest "at least since" marker, not a real historical join date) and
-- defaults new joins to NOW() going forward with no code change needed at
-- the four INSERT sites in app_core/coalitions/routes.py.

BEGIN;

ALTER TABLE coalitions_legacy ADD COLUMN IF NOT EXISTS joined_at TIMESTAMPTZ DEFAULT NOW();

COMMIT;
