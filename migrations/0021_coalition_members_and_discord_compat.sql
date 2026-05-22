-- Migration 0021: Coalition membership table + Discord link column
-- Production may still have the flat ``coalitions`` table while application
-- code expects ``coalitions_legacy``. Discord OAuth expects users.discord_id.

BEGIN;

DO $$
BEGIN
    IF to_regclass('public.coalitions_legacy') IS NULL
       AND to_regclass('public.coalitions') IS NOT NULL THEN
        ALTER TABLE public.coalitions RENAME TO coalitions_legacy;
    END IF;
END $$;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS discord_id VARCHAR(255);

COMMIT;
