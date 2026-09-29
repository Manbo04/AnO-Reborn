-- 0084 added the sam_batteries unit to UNITS but never gave spyinfo a matching
-- column, so any unit spy op that uncovered SAMs 500'd on the UPDATE.
ALTER TABLE spyinfo ADD COLUMN IF NOT EXISTS sam_batteries BIGINT DEFAULT 0;
