-- Migration: 0075 - Add stats.tutorial_step, backfilling a column that only
-- ever existed via an undocumented runtime ALTER TABLE call (removed in the
-- commit that adds this migration -- see app_core/tutorial/routes.py). A
-- fresh database had no code path left to create this column without this.
ALTER TABLE stats ADD COLUMN IF NOT EXISTS tutorial_step INTEGER DEFAULT 0;
