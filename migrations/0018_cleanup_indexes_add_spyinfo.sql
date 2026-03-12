-- 0018: Clean up duplicate indexes and add missing compound index for spyinfo
-- Context: Performance audit found duplicate indexes wasting write overhead
-- and a missing compound index needed by the intelligence page.

-- Drop duplicate index on provinces.userId (older provinces_userid_idx has 35K scans,
-- this one from migration 0017 has 0 scans — PG picks the older one)
DROP INDEX IF EXISTS idx_provinces_userid;

-- Drop duplicate indexes on resource_dictionary.name
-- resource_dictionary_name_key (UNIQUE constraint) is the one PG uses;
-- resource_dictionary_name_unique is also constraint-backed (cannot drop index only)
-- idx_resource_dictionary_name is the redundant standalone copy
DROP INDEX IF EXISTS idx_resource_dictionary_name;

-- Drop unused indexes from migration 0017 (tables too small for PG to use them)
DROP INDEX IF EXISTS idx_coalitions_userid;
DROP INDEX IF EXISTS idx_wars_attacker;

-- Add compound index for intelligence page: WHERE spyer=%s ORDER BY date ASC
CREATE INDEX IF NOT EXISTS idx_spyinfo_spyer_date
    ON spyinfo (spyer, date);

-- Add index for purchase_audit lookups by user_id (used by cleanup scripts)
CREATE INDEX IF NOT EXISTS idx_purchase_audit_user_id
    ON purchase_audit (user_id);
