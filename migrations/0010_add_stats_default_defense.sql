-- Migration 0010: Add default_defense column to stats table
-- This column was previously on the now-deleted military table.
-- Stores a comma-separated list of 3 unit names for auto-defense.

ALTER TABLE stats
    ADD COLUMN IF NOT EXISTS default_defense VARCHAR(200) NOT NULL DEFAULT 'soldiers,tanks,artillery';
