-- Migration: 20261010_1500_discord_visibility.sql
-- Description: Add show_discord setting and discord_username column to users table.

ALTER TABLE users ADD COLUMN IF NOT EXISTS show_discord BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS discord_username TEXT;
