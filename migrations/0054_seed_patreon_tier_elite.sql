-- Migration: 0054 - Seed patreon_tiers ("Order's Elite")
-- Date: 2026-08-30
-- See 0053 for the pattern/rationale. Title must exactly match the tier's
-- live "Name" field on Patreon.

BEGIN;

INSERT INTO patreon_tiers (title, gems_per_month, is_active)
VALUES ('Order''s Elite', 1000, TRUE)
ON CONFLICT (title) DO UPDATE SET gems_per_month = EXCLUDED.gems_per_month;

COMMIT;
