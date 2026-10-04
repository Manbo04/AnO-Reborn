-- Migration 0105: spy reports can reveal a nation's total Iron Domes.
-- NULL (not 0) so un-spied reports show "?".
ALTER TABLE spyinfo ADD COLUMN IF NOT EXISTS iron_domes BIGINT;
