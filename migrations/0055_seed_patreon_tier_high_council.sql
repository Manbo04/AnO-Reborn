-- Migration: 0055 - Seed patreon_tiers ("The High Council")
-- Date: 2026-08-30
-- See 0053 for the pattern/rationale. Title must exactly match the tier's
-- live "Name" field on Patreon.

BEGIN;

INSERT INTO patreon_tiers (title, gems_per_month, is_active)
VALUES ('The High Council', 2500, TRUE)
ON CONFLICT (title) DO UPDATE SET gems_per_month = EXCLUDED.gems_per_month;

COMMIT;
