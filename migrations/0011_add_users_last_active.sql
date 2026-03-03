-- Migration 0011: Add last_active timestamp to users table
-- Tracks when a player was last active (login or page request).
-- Used for alliance management and public profile display.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS last_active TIMESTAMP WITH TIME ZONE DEFAULT NULL;

-- Index for efficient sorting/filtering by last_active (e.g. coalition member lists)
CREATE INDEX IF NOT EXISTS idx_users_last_active ON users (last_active);
