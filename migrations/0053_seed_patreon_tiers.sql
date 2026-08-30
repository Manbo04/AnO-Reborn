-- Migration: 0053 - Seed patreon_tiers (first real tier)
-- Date: 2026-08-30
-- Seeds the Gems/month bonus for the first confirmed Patreon tier. Title
-- must exactly match the tier's live "Name" field on Patreon (see
-- app_core/patreon/ -- matching is by exact title string). Add a row here
-- any time a new tier is created or renamed; the monthly grant task and
-- /patreon both read from this table.

BEGIN;

INSERT INTO patreon_tiers (title, gems_per_month, is_active)
VALUES ('Just to show your love!', 600, TRUE)
ON CONFLICT (title) DO UPDATE SET gems_per_month = EXCLUDED.gems_per_month;

COMMIT;
