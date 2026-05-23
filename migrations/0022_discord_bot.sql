-- Migration 0022: Discord bot link codes, guild settings (Phase 2), unique discord_id

BEGIN;

CREATE TABLE IF NOT EXISTS discord_link_codes (
    code VARCHAR(16) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_discord_link_codes_user_id
    ON discord_link_codes (user_id);

CREATE TABLE IF NOT EXISTS discord_guild_settings (
    guild_id VARCHAR(32) PRIMARY KEY,
    coalition_id INTEGER REFERENCES colNames(id) ON DELETE SET NULL,
    registered_role_id VARCHAR(32),
    bank_alert_channel_id VARCHAR(32),
    war_alert_channel_id VARCHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS discord_role_aliases (
    guild_id VARCHAR(32) NOT NULL,
    alias VARCHAR(64) NOT NULL,
    discord_role_id VARCHAR(32) NOT NULL,
    PRIMARY KEY (guild_id, alias)
);

-- Deduplicate discord_id before unique index (keep lowest user id per discord_id)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'users'
          AND column_name = 'discord_id'
    ) THEN
        UPDATE users u
        SET discord_id = NULL
        FROM (
            SELECT discord_id, MIN(id) AS keep_id
            FROM users
            WHERE discord_id IS NOT NULL AND discord_id <> ''
            GROUP BY discord_id
            HAVING COUNT(*) > 1
        ) dups
        WHERE u.discord_id = dups.discord_id
          AND u.id <> dups.keep_id;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_discord_id_unique
    ON users (discord_id)
    WHERE discord_id IS NOT NULL AND discord_id <> '';

COMMIT;
