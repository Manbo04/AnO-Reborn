-- Migration 0040: Discord analytics panel channel

BEGIN;

ALTER TABLE discord_guild_settings
    ADD COLUMN IF NOT EXISTS panel_analytics_channel_id VARCHAR(32);

COMMIT;
