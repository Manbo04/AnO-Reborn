-- Migration 0099: Backfill users.discord_id for accounts registered via Discord OAuth
-- Prior to this fix, discord_register() set hash to the Discord user ID snowflake
-- and auth_type to 'discord', but omitted populating users.discord_id.
BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS discord_id VARCHAR(255);

UPDATE users
SET discord_id = hash
WHERE COALESCE(auth_type, '') = 'discord'
  AND (discord_id IS NULL OR discord_id = '')
  AND hash ~ '^[0-9]{17,20}$';

COMMIT;
