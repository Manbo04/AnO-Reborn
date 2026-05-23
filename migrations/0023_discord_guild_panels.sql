-- Migration 0023: Discord guild panel channels + persisted panel message IDs

BEGIN;

ALTER TABLE discord_guild_settings
    ADD COLUMN IF NOT EXISTS panel_readme_channel_id VARCHAR(32),
    ADD COLUMN IF NOT EXISTS panel_leaderboard_channel_id VARCHAR(32),
    ADD COLUMN IF NOT EXISTS panel_war_feed_channel_id VARCHAR(32),
    ADD COLUMN IF NOT EXISTS panel_inspector_channel_id VARCHAR(32),
    ADD COLUMN IF NOT EXISTS panel_world_channel_id VARCHAR(32),
    ADD COLUMN IF NOT EXISTS panel_alerts_channel_id VARCHAR(32),
    ADD COLUMN IF NOT EXISTS panels_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS panels_refresh_minutes INTEGER NOT NULL DEFAULT 15;

CREATE TABLE IF NOT EXISTS discord_panel_messages (
    guild_id VARCHAR(32) NOT NULL,
    panel_key VARCHAR(32) NOT NULL,
    channel_id VARCHAR(32) NOT NULL,
    message_id VARCHAR(32) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, panel_key)
);

COMMIT;
